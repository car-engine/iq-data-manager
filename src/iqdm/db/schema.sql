-- IQ Data Manager: SQLite schema (draft for review)
-- All timestamps are ISO 8601 UTC text, e.g. '2026-09-30T08:15:00Z'.
-- Run on every connection:  PRAGMA foreign_keys = ON;
-- Journal mode: keep default rollback journal (no WAL) since the DB lives on an SMB share.

PRAGMA user_version = 1;   -- schema version, bumped on each migration


-- ------------------------------------------------------------------
-- Sites: selectable list in the GUI, users can add new ones
-- ------------------------------------------------------------------
CREATE TABLE sites (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- 'LocationA' and 'locationa' count as duplicates
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);


-- ------------------------------------------------------------------
-- Recordings: one row per capture session (single or multi-channel)
-- ------------------------------------------------------------------
CREATE TABLE recordings (
    id                  INTEGER PRIMARY KEY,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    logged_by           TEXT NOT NULL,                      -- pre-filled with Windows login, editable

    -- Timing
    -- start_unix / end_unix are the envelope across all channels:
    -- earliest channel start, latest channel end. end is exclusive
    -- (last file's timestamp + file_duration_s), so span = end - start.
    date                TEXT NOT NULL,                      -- ISO 8601 UTC of recording start
    start_unix          REAL NOT NULL,
    end_unix            REAL NOT NULL,
    file_duration_s     REAL NOT NULL DEFAULT 1.0 CHECK (file_duration_s > 0),

    site_id             INTEGER NOT NULL REFERENCES sites(id),

    -- File format (shared by all channels)
    dtype               TEXT NOT NULL DEFAULT 'int16',
    iq_layout           TEXT NOT NULL DEFAULT 'interleaved_iq'
                            CHECK (iq_layout IN (
                                'interleaved_iq',   -- I0 Q0 I1 Q1 ... (standard)
                                'interleaved_qi',   -- Q0 I0 Q1 I1 ... (swapped; reading as IQ mirrors the spectrum)
                                'planar_iq'         -- all I samples, then all Q samples
                            )),
    endianness          TEXT NOT NULL DEFAULT 'little'
                            CHECK (endianness IN ('little', 'big')),
    header_bytes        INTEGER NOT NULL DEFAULT 0 CHECK (header_bytes >= 0),

    -- Location: storage_root is a UNC root (e.g. \\192.168.1.50\recordings)
    -- or the laptop path while archive_state = 'local'
    storage_root        TEXT NOT NULL,
    rel_path            TEXT NOT NULL,
    archive_state       TEXT NOT NULL DEFAULT 'local'
                            CHECK (archive_state IN ('local', 'archived')),
    archived_at         TEXT,                               -- set when state becomes 'archived'

    recording_plan_ref  TEXT,                               -- path or ID of the recording plan
    remarks             TEXT,

    CHECK (end_unix >= start_unix),
    UNIQUE (storage_root, rel_path)                         -- same folder can't be logged twice
);

CREATE INDEX idx_recordings_start ON recordings(start_unix);
CREATE INDEX idx_recordings_site  ON recordings(site_id);

CREATE TRIGGER trg_recordings_updated_at
AFTER UPDATE ON recordings
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE recordings
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE id = NEW.id;
END;


-- ------------------------------------------------------------------
-- Channels: one row per channel (single-channel recordings have one row, index 0)
-- ------------------------------------------------------------------
CREATE TABLE channels (
    id              INTEGER PRIMARY KEY,
    recording_id    INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    channel_index   INTEGER NOT NULL CHECK (channel_index >= 0),
    sub_path        TEXT NOT NULL DEFAULT '',               -- '0', '1', or '' if files sit in the recording folder
    band            TEXT,                                   -- e.g. 'VHF', 'UHF'
    fc_hz           REAL NOT NULL,
    fs_hz           REAL NOT NULL CHECK (fs_hz > 0),
    start_unix      REAL NOT NULL,                          -- first file timestamp
    end_unix        REAL NOT NULL,                          -- exclusive: last file timestamp + file_duration_s
    n_files         INTEGER CHECK (n_files >= 0),           -- seconds of data present = n_files * file_duration_s
    total_bytes     INTEGER CHECK (total_bytes >= 0),

    CHECK (end_unix >= start_unix),
    UNIQUE (recording_id, channel_index)
);

CREATE INDEX idx_channels_recording ON channels(recording_id);


-- ------------------------------------------------------------------
-- Recording params: flexible RF chain details
-- channel_id NULL  -> applies to the whole recording (e.g. SDR = X310)
-- channel_id set   -> applies to one channel (e.g. Antenna on channel 1)
-- App logic must ensure channel_id belongs to the same recording_id.
-- ------------------------------------------------------------------
CREATE TABLE recording_params (
    id              INTEGER PRIMARY KEY,
    recording_id    INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    channel_id      INTEGER REFERENCES channels(id) ON DELETE CASCADE,
    param           TEXT NOT NULL COLLATE NOCASE,           -- e.g. 'SDR', 'Antenna', 'LNA gain'
    value           TEXT NOT NULL,
    unit            TEXT                                    -- e.g. 'dB'
);

CREATE INDEX idx_params_recording ON recording_params(recording_id);
CREATE INDEX idx_params_param     ON recording_params(param);


-- ------------------------------------------------------------------
-- Transfer log: history of moves, copies and archive checks
-- No ON DELETE CASCADE: a recording with transfer history cannot be
-- deleted by accident; its log must be handled explicitly first.
-- ------------------------------------------------------------------
CREATE TABLE transfer_log (
    id                  INTEGER PRIMARY KEY,
    recording_id        INTEGER NOT NULL REFERENCES recordings(id),
    operation           TEXT NOT NULL CHECK (operation IN ('move', 'copy', 'check')),
    source              TEXT NOT NULL,
    destination         TEXT,                               -- NULL for 'check'
    range_start_unix    REAL,                               -- NULL = whole recording
    range_end_unix      REAL,
    started_at          TEXT NOT NULL,
    finished_at         TEXT,                               -- NULL = interrupted / never completed
    n_files             INTEGER,
    total_bytes         INTEGER,
    verification        TEXT NOT NULL DEFAULT 'skipped'
                            CHECK (verification IN ('pass', 'fail', 'skipped')),
    performed_by        TEXT NOT NULL,
    notes               TEXT,

    CHECK (range_end_unix IS NULL OR range_start_unix IS NULL OR range_end_unix >= range_start_unix)
);

CREATE INDEX idx_transfer_recording ON transfer_log(recording_id);
