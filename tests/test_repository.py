"""Tests for iqdm.db.repository. Every database lives in tmp_path."""

import pytest

from iqdm.db import repository as repo
from iqdm.db.connection import open_db, write_transaction
from iqdm.models import (
    ArchiveState,
    Channel,
    HashMode,
    Operation,
    Param,
    Recording,
    SampleType,
    TransferEntry,
    Verification,
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
    old = recording(
        site_id, "old", channels=[channel(0, start=T0 - 100, end=T0 - 90)], params=[]
    )
    new = recording(
        site_id,
        "new",
        channels=[channel(0), channel(1, n_files=9, fc=200e6)],
        params=[],
    )
    unknown = recording(
        site_id, "unknown", channels=[channel(0, start=T0 - 50, end=T0 - 40, n_files=None)],
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
        conn, rid, storage_root="//nas/recordings", rel_path="2026/rec1",
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
            rid, channels=(2, 0, 2), hash_mode=HashMode.SAMPLE,
            range_start_unix=T0, range_end_unix=T0 + 5,
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
        conn, tid, finished_at="2026-10-02T01:10:00Z", verification=Verification.PASS,
        n_files=20, total_bytes=80000,
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


def test_transfers_listed_oldest_first(conn, site_id):
    rid = repo.insert_recording(conn, recording(site_id))
    repo.insert_transfer(conn, transfer(rid, started_at="2026-10-02T05:00:00Z"))
    repo.insert_transfer(conn, transfer(rid, started_at="2026-10-02T01:00:00Z"))
    starts = [t.started_at for t in repo.list_transfers(conn, rid)]
    assert starts == ["2026-10-02T01:00:00Z", "2026-10-02T05:00:00Z"]


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
