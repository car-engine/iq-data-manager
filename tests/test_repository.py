"""Tests for iqdm.db.repository. Every database lives in tmp_path."""

import sqlite3

import pytest

from iqdm.db import repository as repo
from iqdm.db.connection import open_db, write_transaction
from iqdm.models import (
    IN_PLACE_NOTE,
    ArchiveState,
    Channel,
    HashMode,
    Operation,
    Param,
    Recording,
    RecordingFilter,
    SameStart,
    SampleType,
    TransferEntry,
    Verification,
    same_capture,
)

T0 = 1790733600.0  # 2026-09-30T02:00:00Z


@pytest.fixture
def conn(db_path):
    with open_db(db_path) as c:
        yield c


@pytest.fixture
def site_id(conn) -> int:
    site = repo.add_site(conn, "SiteA")
    assert site.id is not None
    return site.id


def channel(index: int, *, start=T0, end=T0 + 10, n_files=10, fc=100e6) -> Channel:
    return Channel(
        channel_index=index,
        sub_path=str(index),
        band="VHF",
        fc_hz=fc,
        fs_hz=1000.0,
        start_unix=start,
        end_unix=end,
        n_files=n_files,
        total_bytes=None if n_files is None else n_files * 4000,
    )


def recording(
    site_id: int,
    rel_path="rec1",
    channels=None,
    params=None,
    storage_root="C:/captures",
    **kw,
) -> Recording:
    return Recording(
        logged_by="tester",
        site_id=site_id,
        storage_root=storage_root,
        rel_path=rel_path,
        channels=channels if channels is not None else [channel(0), channel(1, fc=200e6)],
        params=params
        if params is not None
        else [
            Param(param="SDR", value="X310"),
            Param(param="Antenna", value="Discone", channel_index=1),
        ],
        **kw,
    )


def count(conn, table) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------


def test_add_site(conn):
    site = repo.add_site(conn, "  LocationA ")
    assert site.name == "LocationA"
    assert site.id is not None
    assert site.created_at is not None
    assert site.created_at.endswith("Z")


def test_add_site_rejects_empty(conn):
    with pytest.raises(ValueError, match="empty"):
        repo.add_site(conn, "   ")


def test_add_site_duplicate_ignoring_case(conn):
    repo.add_site(conn, "LocationA")
    with pytest.raises(repo.DuplicateSiteError):
        repo.add_site(conn, "locationa")


def test_list_and_find_sites(conn):
    for name in ["beta", "Alpha", "gamma"]:
        repo.add_site(conn, name)
    assert [s.name for s in repo.list_sites(conn)] == ["Alpha", "beta", "gamma"]
    found = repo.find_site(conn, "ALPHA")
    assert found is not None
    assert found.name == "Alpha"
    assert repo.find_site(conn, "delta") is None
    assert repo.get_site(conn, found.id).name == "Alpha"
    with pytest.raises(repo.NotFoundError):
        repo.get_site(conn, 999)


# ---------------------------------------------------------------------------
# Insert and read
# ---------------------------------------------------------------------------


def test_insert_and_get_round_trip(conn, site_id):
    rec = recording(
        site_id, dtype=SampleType.FLOAT32, header_bytes=64, remarks="test", recording_plan_ref="P1"
    )
    rid = repo.insert_recording(conn, rec)
    got = repo.get_recording(conn, rid)

    assert got.id == rid
    assert got.dtype is SampleType.FLOAT32
    assert got.header_bytes == 64
    assert got.remarks == "test"
    assert got.recording_plan_ref == "P1"
    assert got.archive_state is ArchiveState.LOCAL
    assert got.created_at is not None
    assert [c.channel_index for c in got.channels] == [0, 1]
    assert all(c.id is not None for c in got.channels)
    assert got.channels[1].fc_hz == 200e6
    assert [(p.param, p.value, p.channel_index) for p in got.params] == [
        ("SDR", "X310", None),
        ("Antenna", "Discone", 1),
    ]


def test_envelope_and_date_are_derived(conn, site_id):
    rec = recording(
        site_id,
        channels=[channel(0, start=T0 + 2, end=T0 + 8), channel(1, start=T0, end=T0 + 6)],
        start_unix=0.0,  # ignored
        end_unix=1.0,  # ignored
        date="ignored",
    )
    got = repo.get_recording(conn, repo.insert_recording(conn, rec))
    assert (got.start_unix, got.end_unix) == (T0, T0 + 8)
    assert got.date == "2026-09-30T02:00:00Z"


@pytest.mark.parametrize(
    ("channels", "params", "message"),
    [
        ([], [], "at least one channel"),
        ([channel(0), channel(0)], [], "duplicate channel"),
        ([channel(0)], [Param(param="Antenna", value="x", channel_index=3)], "missing channel"),
    ],
)
def test_invalid_recordings_write_nothing(conn, site_id, channels, params, message):
    with pytest.raises(ValueError, match=message):
        repo.insert_recording(conn, recording(site_id, channels=channels, params=params))
    assert count(conn, "recordings") == 0


def test_duplicate_location(conn, site_id):
    repo.insert_recording(conn, recording(site_id))
    with pytest.raises(repo.DuplicateLocationError, match="already logged"):
        repo.insert_recording(conn, recording(site_id))


def test_find_by_location(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    assert repo.find_recording_by_location(conn, "C:/captures", "rec1") == rid
    assert repo.find_recording_by_location(conn, "C:/captures", "rec2") is None


def test_get_missing_recording(conn):
    with pytest.raises(repo.NotFoundError):
        repo.get_recording(conn, 999)


def test_list_recordings(conn, site_id):
    old = recording(site_id, "old", channels=[channel(0, start=T0 - 100, end=T0 - 90)], params=[])
    new = recording(
        site_id,
        "new",
        channels=[channel(0), channel(1, n_files=9, fc=200e6)],
        params=[],
    )
    unknown = recording(
        site_id,
        "unknown",
        channels=[channel(0, start=T0 - 50, end=T0 - 40, n_files=None)],
        params=[],
    )
    for rec in (old, new, unknown):
        repo.insert_recording(conn, rec)

    summaries = repo.list_recordings(conn)
    assert [s.channel_count for s in summaries] == [2, 1, 1]  # newest first
    first = summaries[0]
    assert first.site_name == "SiteA"
    assert first.fc_hz == (100e6, 200e6)
    assert first.total_bytes == 19 * 4000
    assert first.coverage == 0.9
    assert first.archive_state is ArchiveState.LOCAL
    assert summaries[1].total_bytes is None
    assert summaries[1].coverage is None


# ---------------------------------------------------------------------------
# Viewer filters (Milestone 4)
# ---------------------------------------------------------------------------

ARCHIVED_AT = "2026-10-01T00:00:00Z"


def band_channel(index: int, band: str | None, fc: float, start: float = T0) -> Channel:
    ch = channel(index, start=start, end=start + 10, fc=fc)
    ch.band = band
    return ch


@pytest.fixture
def filter_set(conn, site_id) -> dict[str, int]:
    """Four recordings that differ in every filtered field. Returns their ids by name."""
    other_site = repo.add_site(conn, "SiteB").id
    recs = {
        "vhf": recording(
            site_id,
            "vhf",
            channels=[band_channel(0, "VHF", 145.8e6, start=T0)],
            params=[Param(param="SDR", value="X310")],
            remarks="Baseline 100% run",
        ),
        "uhf": recording(
            other_site,
            "uhf",
            channels=[
                band_channel(0, "VHF", 145.0e6, T0 + 86400),
                band_channel(1, "UHF", 435e6, T0 + 86400),
            ],
            params=[Param(param="LNA gain", value="20", unit="dB", channel_index=1)],
            remarks="second_run",
            archive_state=ArchiveState.ARCHIVED,
            archived_at=ARCHIVED_AT,
        ),
        "none": recording(
            site_id,
            "none",
            channels=[band_channel(0, None, 868.3e6, T0 + 2 * 86400)],
            params=[],
            remarks=None,
        ),
        "later": recording(
            other_site,
            "later",
            channels=[band_channel(0, "uhf", 433.92e6, T0 + 3 * 86400)],
            params=[Param(param="Antenna", value="Monopole B")],
            remarks="BASELINE check",
        ),
    }
    return {name: repo.insert_recording(conn, rec) for name, rec in recs.items()}


def ids(conn, flt: RecordingFilter | None, names: dict[str, int]) -> list[str]:
    by_id = {v: k for k, v in names.items()}
    return [by_id[s.id] for s in repo.list_recordings(conn, flt)]


def test_no_filter_lists_everything_newest_first(conn, filter_set):
    assert ids(conn, None, filter_set) == ["later", "none", "uhf", "vhf"]
    assert ids(conn, RecordingFilter(), filter_set) == ["later", "none", "uhf", "vhf"]


def test_filter_by_start_bounds(conn, filter_set):
    flt = RecordingFilter(start_from_unix=T0 + 86400, start_before_unix=T0 + 3 * 86400)
    assert ids(conn, flt, filter_set) == ["none", "uhf"]  # from inclusive, before exclusive


def test_filter_by_site(conn, filter_set):
    site = repo.find_site(conn, "SiteB")
    assert ids(conn, RecordingFilter(site_id=site.id), filter_set) == ["later", "uhf"]


def test_filter_by_band_ignores_case(conn, filter_set):
    assert ids(conn, RecordingFilter(band="UHF"), filter_set) == ["later", "uhf"]


def test_filter_by_fc_range_matches_any_channel(conn, filter_set):
    flt = RecordingFilter(fc_min_hz=430e6, fc_max_hz=440e6)
    assert ids(conn, flt, filter_set) == ["later", "uhf"]


def test_fc_range_bounds_are_inclusive(conn, filter_set):
    assert ids(conn, RecordingFilter(fc_min_hz=868.3e6), filter_set) == ["none"]
    assert ids(conn, RecordingFilter(fc_max_hz=145.0e6), filter_set) == ["uhf"]


def test_band_and_fc_range_must_match_on_one_channel(conn, filter_set):
    # "uhf" has a VHF channel at 145 MHz and a UHF channel at 435 MHz.
    flt = RecordingFilter(band="UHF", fc_min_hz=140e6, fc_max_hz=150e6)
    assert ids(conn, flt, filter_set) == []


def test_filter_by_archive_state(conn, filter_set):
    assert ids(conn, RecordingFilter(archive_state=ArchiveState.ARCHIVED), filter_set) == ["uhf"]
    local = ids(conn, RecordingFilter(archive_state=ArchiveState.LOCAL), filter_set)
    assert local == ["later", "none", "vhf"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("x310", ["vhf"]),  # value, any letter case
        ("lna", ["uhf"]),  # parameter name
        ("dB", ["uhf"]),  # unit
        ("mono", ["later"]),
        ("nothing", []),
    ],
)
def test_filter_by_rf_chain_text(conn, filter_set, text, expected):
    assert ids(conn, RecordingFilter(rf_chain_text=text), filter_set) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("baseline", ["later", "vhf"]),
        ("100%", ["vhf"]),  # % is literal
        ("%", ["vhf"]),
        ("_", ["uhf"]),  # _ is literal
        ("d_run", ["uhf"]),
        ("e_r", []),  # _ would match any letter as a wildcard
    ],
)
def test_filter_by_remarks_text_takes_wildcards_literally(conn, filter_set, text, expected):
    assert ids(conn, RecordingFilter(remarks_text=text), filter_set) == expected


def test_like_pattern_escapes_the_escape_character():
    assert repo.like_pattern(r"a\b%c_d") == r"%a\\b\%c\_d%"


def test_filters_combine(conn, filter_set):
    flt = RecordingFilter(band="uhf", remarks_text="baseline", rf_chain_text="antenna")
    assert ids(conn, flt, filter_set) == ["later"]


def test_filtered_list_has_the_channels_of_its_recordings_only(conn, filter_set):
    summaries = repo.list_recordings(
        conn, RecordingFilter(site_id=repo.find_site(conn, "SiteB").id)
    )
    assert [s.fc_hz for s in summaries] == [(433.92e6,), (145.0e6, 435e6)]
    assert [s.channel_count for s in summaries] == [1, 2]


def in_place_entry(recording_id: int, notes: str = IN_PLACE_NOTE) -> TransferEntry:
    return TransferEntry(
        recording_id=recording_id,
        operation=Operation.CHECK,
        source=r"\\nas\recordings\uhf",
        started_at=ARCHIVED_AT,
        finished_at=ARCHIVED_AT,
        performed_by="tester",
        verification=Verification.SKIPPED,
        notes=notes,
    )


def test_recording_logged_in_place_is_unverified(conn, filter_set):
    repo.insert_transfer(conn, in_place_entry(filter_set["uhf"]))
    flags = {s.id: s.unverified for s in repo.list_recordings(conn)}
    assert flags[filter_set["uhf"]] is True
    assert sum(flags.values()) == 1


def test_other_check_rows_do_not_mark_unverified(conn, filter_set):
    repo.insert_transfer(conn, in_place_entry(filter_set["uhf"], notes="something else"))
    passed = in_place_entry(filter_set["uhf"])
    passed.verification = Verification.PASS
    repo.insert_transfer(conn, passed)
    assert not any(s.unverified for s in repo.list_recordings(conn))


def test_a_local_recording_is_never_unverified(conn, filter_set):
    repo.insert_transfer(conn, in_place_entry(filter_set["vhf"]))
    assert not any(s.unverified for s in repo.list_recordings(conn))


def test_many_recordings_keep_their_own_channels(db_path):
    """5,000 recordings with 1 to 3 channels each (O16: the expected catalogue size)."""

    def fill(conn):
        site = repo.add_site(conn, "Bulk").id
        for i in range(5000):
            n = i % 3 + 1
            chans = [
                channel(k, start=T0 + i * 100, end=T0 + i * 100 + 10, fc=(i * 10 + k) * 1e3)
                for k in range(n)
            ]
            repo.insert_recording(conn, recording(site, f"r{i}", channels=chans, params=[]))

    write_transaction(db_path, fill)
    with open_db(db_path, readonly=True) as c:
        summaries = repo.list_recordings(c)
        assert len(summaries) == 5000
        for s in summaries:
            i = round((s.start_unix - T0) / 100)
            assert s.channel_count == i % 3 + 1
            assert s.fc_hz == tuple((i * 10 + k) * 1e3 for k in range(i % 3 + 1))
        some = repo.list_recordings(c, RecordingFilter(fc_min_hz=12_340e3, fc_max_hz=12_342e3))
        assert [s.fc_hz[0] for s in some] == [12_340e3]


def test_list_param_names(conn, site_id):
    repo.insert_recording(conn, recording(site_id, "a"))
    params = [Param(param="sdr", value="B210"), Param(param="LNA gain", value="20")]
    repo.insert_recording(conn, recording(site_id, "b", params=params))
    names = repo.list_param_names(conn)
    assert [n.lower() for n in names] == ["antenna", "lna gain", "sdr"]


def test_list_bands_is_distinct_sorted_and_skips_empty(conn, site_id):
    bands = ["VHF", "uhf", None, "", "vhf", "L"]
    for i, band in enumerate(bands):
        ch = channel(0)
        ch.band = band
        repo.insert_recording(conn, recording(site_id, f"r{i}", channels=[ch], params=[]))
    result = repo.list_bands(conn)
    assert [b.lower() for b in result] == ["l", "uhf", "vhf"]
    assert result[0] == "L"


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_update_keeps_channel_ids_and_replaces_params(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    before = repo.get_recording(conn, rid)
    conn.execute("UPDATE recordings SET updated_at = '2000-01-01T00:00:00Z' WHERE id = ?", (rid,))

    edited = repo.get_recording(conn, rid)
    edited.remarks = "edited"
    edited.channels[1].fc_hz = 250e6
    edited.channels.append(channel(2, start=T0 - 5, end=T0 + 20))
    edited.params = [
        Param(param="SDR", value="X310"),
        Param(param="Antenna", value="Yagi", channel_index=1),
        Param(param="Antenna", value="Dipole", channel_index=2),
    ]
    repo.update_recording(conn, edited)

    after = repo.get_recording(conn, rid)
    assert after.remarks == "edited"
    assert [c.id for c in after.channels[:2]] == [c.id for c in before.channels]
    assert after.channels[1].fc_hz == 250e6
    assert after.channels[2].channel_index == 2
    assert (after.start_unix, after.end_unix) == (T0 - 5, T0 + 20)
    assert after.date == "2026-09-30T01:59:55Z"
    assert [(p.value, p.channel_index) for p in after.params] == [
        ("X310", None),
        ("Yagi", 1),
        ("Dipole", 2),
    ]
    assert after.updated_at != "2000-01-01T00:00:00Z"


def test_update_refuses_channel_removal_without_flag(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    edited = repo.get_recording(conn, rid)
    edited.channels = edited.channels[:1]
    edited.params = [Param(param="SDR", value="changed")]
    with pytest.raises(repo.ChannelRemovalError, match=r"\[1\]"):
        repo.update_recording(conn, edited)
    unchanged = repo.get_recording(conn, rid)
    assert len(unchanged.channels) == 2
    assert unchanged.params[0].value == "X310"


def test_update_removes_channel_and_its_params_with_flag(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    edited = repo.get_recording(conn, rid)
    edited.channels = edited.channels[:1]
    edited.params = [p for p in edited.params if p.channel_index != 1]
    repo.update_recording(conn, edited, allow_channel_removal=True)
    after = repo.get_recording(conn, rid)
    assert [c.channel_index for c in after.channels] == [0]
    assert count(conn, "channels") == 1
    assert [p.param for p in after.params] == ["SDR"]


def test_update_to_taken_location(conn, site_id):
    repo.insert_recording(conn, recording(site_id, "a"))
    rid = repo.insert_recording(conn, recording(site_id, "b"))
    edited = repo.get_recording(conn, rid)
    edited.rel_path = "a"
    with pytest.raises(repo.DuplicateLocationError):
        repo.update_recording(conn, edited)


def test_update_needs_existing_id(conn, site_id):
    with pytest.raises(ValueError, match=r"rec\.id"):
        repo.update_recording(conn, recording(site_id))
    missing = recording(site_id)
    missing.id = 999
    with pytest.raises(repo.NotFoundError):
        repo.update_recording(conn, missing)


def test_update_archive_location(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    repo.update_archive_location(
        conn,
        rid,
        storage_root="//nas/recordings",
        rel_path="2026/rec1",
        archived_at="2026-10-02T00:00:00Z",
    )
    got = repo.get_recording(conn, rid)
    assert got.archive_state is ArchiveState.ARCHIVED
    assert (got.storage_root, got.rel_path) == ("//nas/recordings", "2026/rec1")
    assert got.archived_at == "2026-10-02T00:00:00Z"
    with pytest.raises(repo.NotFoundError):
        repo.update_archive_location(
            conn, 999, storage_root="x", rel_path="y", archived_at="2026-10-02T00:00:00Z"
        )


def test_update_channel_counts(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    repo.update_channel_counts(conn, rid, {0: (7, 28000), 1: (8, 32000)})
    got = repo.get_recording(conn, rid)
    assert [(c.n_files, c.total_bytes) for c in got.channels] == [(7, 28000), (8, 32000)]
    with pytest.raises(repo.NotFoundError, match="no channel 5"):
        repo.update_channel_counts(conn, rid, {5: (1, 1)})


# ---------------------------------------------------------------------------
# Delete (catalogue rows only)
# ---------------------------------------------------------------------------


def test_delete_recording_cascades(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    repo.delete_recording(conn, rid)
    assert count(conn, "recordings") == 0
    assert count(conn, "channels") == 0
    assert count(conn, "recording_params") == 0
    with pytest.raises(repo.NotFoundError):
        repo.delete_recording(conn, rid)


def test_delete_refused_with_transfer_history(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    repo.insert_transfer(conn, transfer(rid))
    with pytest.raises(repo.HasTransferHistoryError):
        repo.delete_recording(conn, rid)
    assert count(conn, "recordings") == 1


# ---------------------------------------------------------------------------
# Transfer log
# ---------------------------------------------------------------------------


def transfer(rid: int, **kw) -> TransferEntry:
    values = {
        "recording_id": rid,
        "operation": Operation.COPY,
        "source": "//nas/recordings/rec1",
        "destination": "D:/work/rec1",
        "started_at": "2026-10-02T01:00:00Z",
        "performed_by": "tester",
    } | kw
    return TransferEntry(**values)


def test_transfer_round_trip(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    tid = repo.insert_transfer(
        conn,
        transfer(
            rid,
            channels=(2, 0, 2),
            hash_mode=HashMode.SAMPLE,
            range_start_unix=T0,
            range_end_unix=T0 + 5,
        ),
    )
    (got,) = repo.list_transfers(conn, rid)
    assert got.id == tid
    assert got.channels == (0, 2)
    assert got.hash_mode is HashMode.SAMPLE
    assert got.operation is Operation.COPY
    assert got.verification is Verification.SKIPPED
    assert (got.range_start_unix, got.range_end_unix) == (T0, T0 + 5)
    assert got.finished_at is None
    stored = conn.execute("SELECT channels FROM transfer_log").fetchone()[0]
    assert stored == "0,2"


def test_transfer_all_channels_is_null(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    repo.insert_transfer(conn, transfer(rid))
    assert conn.execute("SELECT channels FROM transfer_log").fetchone()[0] is None
    assert repo.list_transfers(conn, rid)[0].channels is None


@pytest.mark.parametrize("bad", [(), (-1, 0)])
def test_encode_channels_rejects_bad_subsets(bad):
    with pytest.raises(ValueError, match="channel"):
        repo.encode_channels(bad)


def test_finish_transfer(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    tid = repo.insert_transfer(conn, transfer(rid, notes="started"))
    repo.finish_transfer(
        conn,
        tid,
        finished_at="2026-10-02T01:10:00Z",
        verification=Verification.PASS,
        n_files=20,
        total_bytes=80000,
    )
    (got,) = repo.list_transfers(conn, rid)
    assert got.finished_at == "2026-10-02T01:10:00Z"
    assert got.verification is Verification.PASS
    assert (got.n_files, got.total_bytes) == (20, 80000)
    assert got.notes == "started"
    with pytest.raises(repo.RepositoryError, match="already finished"):
        repo.finish_transfer(
            conn, tid, finished_at="2026-10-02T02:00:00Z", verification=Verification.FAIL
        )
    with pytest.raises(repo.NotFoundError):
        repo.finish_transfer(
            conn, 999, finished_at="2026-10-02T02:00:00Z", verification=Verification.FAIL
        )


def test_get_transfer(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    tid = repo.insert_transfer(conn, transfer(rid, notes="started"))
    got = repo.get_transfer(conn, tid)
    assert (got.id, got.recording_id, got.notes) == (tid, rid, "started")
    assert (got.parent_id, got.manifest_path, got.manifest_sha256) == (None, None, None)
    with pytest.raises(repo.NotFoundError):
        repo.get_transfer(conn, 999)


@pytest.mark.parametrize(
    ("stored", "new", "expected"),
    [
        (None, None, None),
        (None, "Cancelled.", "Cancelled."),
        ("Resumed.", None, "Resumed."),
        ("Resumed.", "Cancelled.", "Resumed. Cancelled."),
        ("", "Cancelled.", "Cancelled."),
    ],
)
def test_finish_transfer_appends_its_note(conn, site_id, stored, new, expected):
    """D62: a note is added after the stored text."""
    rid = repo.insert_recording(conn, recording(site_id))
    tid = repo.insert_transfer(conn, transfer(rid, notes=stored))
    repo.finish_transfer(
        conn, tid, finished_at="2026-10-02T01:10:00Z", verification=Verification.SKIPPED, notes=new
    )
    assert repo.get_transfer(conn, tid).notes == expected


def test_finish_transfer_records_the_manifest(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    tid = repo.insert_transfer(conn, transfer(rid))
    digest = "ab" * 32
    repo.finish_transfer(
        conn,
        tid,
        finished_at="2026-10-02T01:10:00Z",
        verification=Verification.PASS,
        manifest_path="C:/app/manifests/transfer-1.json",
        manifest_sha256=digest,
    )
    got = repo.get_transfer(conn, tid)
    assert (got.manifest_path, got.manifest_sha256) == ("C:/app/manifests/transfer-1.json", digest)


def start_archive(conn, rid) -> int:
    return repo.insert_transfer(
        conn, transfer(rid, operation=Operation.ARCHIVE, source="C:/captures/rec1")
    )


def test_finish_archive_points_the_recording_at_the_nas(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    tid = start_archive(conn, rid)
    repo.finish_archive(
        conn,
        tid,
        finished_at="2026-10-02T01:30:00Z",
        n_files=20,
        total_bytes=80000,
        manifest_path="C:/app/manifests/transfer-1.json",
        manifest_sha256="cd" * 32,
        storage_root="//nas/recordings",
        rel_path="2026/rec1",
    )
    archive = repo.get_transfer(conn, tid)
    assert archive.verification is Verification.PASS
    assert (archive.n_files, archive.total_bytes) == (20, 80000)
    assert archive.manifest_sha256 == "cd" * 32
    rec = repo.get_recording(conn, rid)
    assert rec.archive_state is ArchiveState.ARCHIVED
    assert (rec.storage_root, rec.rel_path) == ("//nas/recordings", "2026/rec1")
    assert rec.archived_at == "2026-10-02T01:30:00Z"


def test_finish_archive_refuses_another_operation(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    tid = repo.insert_transfer(conn, transfer(rid))
    with pytest.raises(repo.RepositoryError, match="not an archive"):
        repo.finish_archive(
            conn,
            tid,
            finished_at="2026-10-02T01:30:00Z",
            n_files=1,
            total_bytes=1,
            manifest_path="m.json",
            manifest_sha256="cd" * 32,
            storage_root="//nas/recordings",
            rel_path="rec1",
        )
    assert repo.get_recording(conn, rid).archive_state is ArchiveState.LOCAL


def test_finish_archive_refuses_a_recording_archived_meanwhile(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    first, second = start_archive(conn, rid), start_archive(conn, rid)
    values = {
        "finished_at": "2026-10-02T01:30:00Z",
        "n_files": 20,
        "total_bytes": 80000,
        "manifest_path": "m.json",
        "manifest_sha256": "cd" * 32,
        "storage_root": "//nas/recordings",
    }
    repo.finish_archive(conn, first, rel_path="first", **values)
    with pytest.raises(repo.AlreadyArchivedError):
        repo.finish_archive(conn, second, rel_path="second", **values)
    assert repo.get_recording(conn, rid).rel_path == "first"
    assert repo.get_transfer(conn, second).finished_at is None


def test_finish_archive_is_atomic(db_path):
    with open_db(db_path) as c:
        site = repo.add_site(c, "SiteA").id
        rid = repo.insert_recording(c, recording(site))
        repo.insert_recording(c, recording(site, rel_path="taken", storage_root="//nas/rec"))
        tid = start_archive(c, rid)

    def finish(c):
        repo.finish_archive(
            c,
            tid,
            finished_at="2026-10-02T01:30:00Z",
            n_files=20,
            total_bytes=80000,
            manifest_path="m.json",
            manifest_sha256="cd" * 32,
            storage_root="//nas/rec",
            rel_path="taken",  # another recording uses this location
        )

    with pytest.raises(repo.DuplicateLocationError):
        write_transaction(db_path, finish)
    with open_db(db_path, readonly=True) as c:
        assert repo.get_transfer(c, tid).finished_at is None
        assert repo.get_recording(c, rid).archive_state is ArchiveState.LOCAL


def test_delete_row_round_trip(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    archive = start_archive(conn, rid)
    repo.finish_transfer(
        conn, archive, finished_at="2026-10-02T01:30:00Z", verification=Verification.PASS
    )
    tid = repo.insert_transfer(
        conn,
        transfer(
            rid,
            operation=Operation.DELETE,
            parent_id=archive,
            destination=None,
            verification=Verification.PASS,
            finished_at="2026-10-02T02:00:00Z",
        ),
    )
    got = repo.get_transfer(conn, tid)
    assert got.operation is Operation.DELETE
    assert got.parent_id == archive


def test_delete_row_needs_a_passed_archive(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    archive = start_archive(conn, rid)  # not finished: verification is still 'skipped'
    with pytest.raises(sqlite3.IntegrityError, match="passed archive"):
        repo.insert_transfer(
            conn, transfer(rid, operation=Operation.DELETE, parent_id=archive, destination=None)
        )


def test_transfers_listed_oldest_first(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    repo.insert_transfer(conn, transfer(rid, started_at="2026-10-02T05:00:00Z"))
    repo.insert_transfer(conn, transfer(rid, started_at="2026-10-02T01:00:00Z"))
    starts = [t.started_at for t in repo.list_transfers(conn, rid)]
    assert starts == ["2026-10-02T01:00:00Z", "2026-10-02T05:00:00Z"]


# ---------------------------------------------------------------------------
# One capture logged twice (D61)
# ---------------------------------------------------------------------------


def test_recordings_starting_at_list_their_end_and_channels(conn, site_id):
    first = repo.insert_recording(conn, recording(site_id, rel_path="a"))
    second = repo.insert_recording(
        conn, recording(site_id, rel_path="b", channels=[channel(2), channel(0)], params=[])
    )
    repo.insert_recording(
        conn,
        recording(site_id, rel_path="later", channels=[channel(0, start=T0 + 1)], params=[]),
    )
    found = repo.recordings_starting_at(conn, T0)
    assert [(s.recording_id, s.channel_indices) for s in found] == [
        (first, (0, 1)),
        (second, (0, 2)),
    ]
    assert all(s.archive_state is ArchiveState.LOCAL for s in found)


def test_same_capture_needs_the_end_and_the_channels():
    local = ArchiveState.LOCAL
    cands = [
        SameStart(recording_id=1, end_unix=10.0, channel_indices=(0, 1), archive_state=local),
        SameStart(recording_id=2, end_unix=11.0, channel_indices=(0, 1), archive_state=local),
        SameStart(recording_id=3, end_unix=10.0, channel_indices=(0,), archive_state=local),
    ]
    assert [c.recording_id for c in same_capture(cands, 10.0, [1, 0])] == [1]
    assert same_capture(cands, 10.0, [0, 1], exclude=1) == []


# ---------------------------------------------------------------------------
# Unfinished transfers and "Forget"
# ---------------------------------------------------------------------------


def finished(conn, tid, verification, at="2026-10-02T02:00:00Z") -> int:
    repo.finish_transfer(conn, tid, finished_at=at, verification=verification)
    return tid


def unfinished_ids(conn, **kw) -> list[int]:
    return [t.id for t in repo.list_unfinished_transfers(conn, **kw)]


def start(conn, rid, **kw) -> int:
    return repo.insert_transfer(conn, transfer(rid, **kw))


def test_stopped_failed_and_interrupted_transfers_are_unfinished(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    stopped = finished(conn, start(conn, rid, destination="D:/a"), Verification.SKIPPED)
    failed = finished(conn, start(conn, rid, destination="D:/b"), Verification.FAIL)
    interrupted = start(conn, rid, destination="D:/c")
    finished(conn, start(conn, rid, destination="D:/d"), Verification.PASS)
    assert sorted(unfinished_ids(conn)) == sorted([stopped, failed, interrupted])


def test_a_later_run_of_the_same_selection_replaces_the_earlier(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    first = finished(conn, repo.insert_transfer(conn, transfer(rid)), Verification.SKIPPED)
    second = finished(conn, repo.insert_transfer(conn, transfer(rid)), Verification.SKIPPED)
    assert unfinished_ids(conn) == [second]
    finished(conn, repo.insert_transfer(conn, transfer(rid)), Verification.PASS)
    assert unfinished_ids(conn) == []
    assert first not in unfinished_ids(conn)


@pytest.mark.parametrize(
    "change",
    [
        {"destination": "D:/elsewhere"},
        {"channels": (0,)},
        {"range_start_unix": T0},
        {"range_end_unix": T0 + 5},
    ],
)
def test_a_run_of_another_selection_does_not_replace(conn, site_id, change):
    rid = repo.insert_recording(conn, recording(site_id))
    stopped = finished(conn, repo.insert_transfer(conn, transfer(rid)), Verification.SKIPPED)
    finished(conn, repo.insert_transfer(conn, transfer(rid, **change)), Verification.PASS)
    assert unfinished_ids(conn) == [stopped]


def test_an_archive_drops_out_once_the_recording_is_archived(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    tid = start(conn, rid, operation=Operation.ARCHIVE, destination="//nas/a")
    stopped = finished(conn, tid, Verification.SKIPPED)
    assert unfinished_ids(conn) == [stopped]
    repo.update_archive_location(
        conn, rid, storage_root="//nas/recordings", rel_path="b", archived_at="2026-10-02T03:00:00Z"
    )
    assert unfinished_ids(conn) == []


def test_unfinished_newest_first_and_by_user(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    old = repo.insert_transfer(
        conn, transfer(rid, destination="D:/a", started_at="2026-10-01T00:00:00Z")
    )
    new = repo.insert_transfer(
        conn,
        transfer(rid, destination="D:/b", started_at="2026-10-02T00:00:00Z", performed_by="userB"),
    )
    assert unfinished_ids(conn) == [new, old]
    assert unfinished_ids(conn, performed_by="userB") == [new]
    assert unfinished_ids(conn, performed_by="nobody") == []


def test_forget_hides_a_row_and_keeps_it(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    tid = finished(conn, repo.insert_transfer(conn, transfer(rid)), Verification.SKIPPED)
    repo.dismiss_transfer(conn, tid, dismissed_at="2026-10-03T08:00:00Z")
    assert unfinished_ids(conn) == []
    assert repo.get_transfer(conn, tid).dismissed_at == "2026-10-03T08:00:00Z"
    with pytest.raises(repo.RepositoryError, match="already forgotten"):
        repo.dismiss_transfer(conn, tid, dismissed_at="2026-10-03T09:00:00Z")


def test_forget_refuses_a_passed_transfer_and_other_operations(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    passed = finished(conn, repo.insert_transfer(conn, transfer(rid)), Verification.PASS)
    with pytest.raises(repo.RepositoryError, match="nothing to forget"):
        repo.dismiss_transfer(conn, passed, dismissed_at="2026-10-03T08:00:00Z")
    check = repo.insert_transfer(
        conn, transfer(rid, operation=Operation.CHECK, destination=None)
    )
    with pytest.raises(repo.RepositoryError, match="is a check"):
        repo.dismiss_transfer(conn, check, dismissed_at="2026-10-03T08:00:00Z")
    with pytest.raises(repo.NotFoundError):
        repo.dismiss_transfer(conn, 999, dismissed_at="2026-10-03T08:00:00Z")


# ---------------------------------------------------------------------------
# Logging in place on the NAS (DECISIONS.md D2): recording and log row in one transaction
# ---------------------------------------------------------------------------


def log_in_place(conn, site_id: int) -> int:
    rec = recording(
        site_id,
        storage_root="//nas/recordings",
        archive_state=ArchiveState.ARCHIVED,
        archived_at="2026-10-02T00:00:00Z",
    )
    rid = repo.insert_recording(conn, rec)
    repo.insert_transfer(
        conn,
        TransferEntry(
            recording_id=rid,
            operation=Operation.CHECK,
            source="//nas/recordings/rec1",
            started_at="2026-10-02T00:00:00Z",
            finished_at="2026-10-02T00:00:00Z",
            performed_by="tester",
            notes="logged in place, not verified against a source",
        ),
    )
    return rid


def test_log_in_place_writes_both_rows(db_path):
    with open_db(db_path) as c:
        site_id = repo.add_site(c, "SiteA").id
    rid = write_transaction(db_path, lambda c: log_in_place(c, site_id))
    with open_db(db_path, readonly=True) as c:
        assert repo.get_recording(c, rid).archive_state is ArchiveState.ARCHIVED
        (entry,) = repo.list_transfers(c, rid)
        assert entry.operation is Operation.CHECK
        assert entry.verification is Verification.SKIPPED


def test_log_in_place_is_atomic(db_path):
    with open_db(db_path) as c:
        site_id = repo.add_site(c, "SiteA").id

    def fails_after_insert(c):
        log_in_place(c, site_id)
        raise RuntimeError("crash before commit")

    with pytest.raises(RuntimeError):
        write_transaction(db_path, fails_after_insert)
    with open_db(db_path, readonly=True) as c:
        assert count(c, "recordings") == 0
        assert count(c, "transfer_log") == 0
