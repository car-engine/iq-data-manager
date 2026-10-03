-- IQ Data Manager: SQLite schema, version 1
-- Edited in place until the first real database exists (docs/DECISIONS.md D4).
-- After that, every change is a numbered migration in migrations.py.
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
    -- The repository derives date, start_unix and end_unix from the channel rows.
    date                TEXT NOT NULL,                      -- ISO 8601 UTC of recording start
    start_unix          REAL NOT NULL,
    end_unix            REAL NOT NULL,
    file_duration_s     REAL NOT NULL DEFAULT 1.0 CHECK (file_duration_s > 0),

    site_id             INTEGER NOT NULL REFERENCES sites(id),

    -- File format (shared by all channels). Samples are always complex IQ.
    dtype               TEXT NOT NULL DEFAULT 'int16'
                            CHECK (dtype IN ('int8', 'int16', 'float32')),  -- DECISIONS.md D1
    iq_layout           TEXT NOT NULL DEFAULT 'interleaved_iq'
                            CHECK (iq_layout IN (
                                'interleaved_iq',   -- I0 Q0 I1 Q1 ... (standard)
                                'interleaved_qi',   -- Q0 I0 Q1 I1 ... (swapped; reading as IQ mirrors the spectrum)
                                'planar_iq'         -- all I samples, then all Q samples
                            )),
    endianness          TEXT NOT NULL DEFAULT 'little'
                            CHECK (endianness IN ('little', 'big')),
    header_bytes        INTEGER NOT NULL DEFAULT 0 CHECK (header_bytes >= 0),  -- at the start of every file

    -- Location: storage_root is a UNC root (e.g. \\192.168.1.50\recordings)
    -- or the laptop path while archive_state = 'local'
    storage_root        TEXT NOT NULL,
    rel_path            TEXT NOT NULL,
    archive_state       TEXT NOT NULL DEFAULT 'local'
                            CHECK (archive_state IN ('local', 'archived')),
    archived_at         TEXT,                               -- set exactly when state is 'archived'

    recording_plan_ref  TEXT,                               -- path or ID of the recording plan
    remarks             TEXT,

    CHECK (end_unix >= start_unix),
    CHECK ((archive_state = 'archived') = (archived_at IS NOT NULL)),
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
-- The triggers below reject a channel_id from a different recording.
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

CREATE TRIGGER trg_params_channel_insert
BEFORE INSERT ON recording_params
FOR EACH ROW
WHEN NEW.channel_id IS NOT NULL
 AND NEW.recording_id IS NOT (SELECT recording_id FROM channels WHERE id = NEW.channel_id)
BEGIN
    SELECT RAISE(ABORT, 'recording_params.channel_id belongs to a different recording');
END;

CREATE TRIGGER trg_params_channel_update
BEFORE UPDATE OF recording_id, channel_id ON recording_params
FOR EACH ROW
WHEN NEW.channel_id IS NOT NULL
 AND NEW.recording_id IS NOT (SELECT recording_id FROM channels WHERE id = NEW.channel_id)
BEGIN
    SELECT RAISE(ABORT, 'recording_params.channel_id belongs to a different recording');
END;


-- ------------------------------------------------------------------
-- Transfer log: history of archives, copies, archive checks and deletions
-- of laptop copies (DECISIONS.md D52)
-- No ON DELETE CASCADE: a recording with transfer history cannot be
-- deleted by accident; its log must be handled explicitly first.
-- ------------------------------------------------------------------
CREATE TABLE transfer_log (
    id                  INTEGER PRIMARY KEY,
    recording_id        INTEGER NOT NULL REFERENCES recordings(id),
    operation           TEXT NOT NULL CHECK (operation IN ('archive', 'copy', 'check', 'delete')),
    parent_id           INTEGER REFERENCES transfer_log(id),  -- the passed archive a 'delete',
                                                              -- or a check before delete, follows
    source              TEXT NOT NULL,
    destination         TEXT,                               -- NULL for 'check' and 'delete'
    range_start_unix    REAL,                               -- NULL = whole recording
    range_end_unix      REAL,
    channels            TEXT                                -- NULL = all channels, else sorted indices e.g. '0,2'
                            CHECK (channels IS NULL OR (channels <> '' AND channels NOT GLOB '*[^0-9,]*')),
    hash_mode           TEXT                                -- NULL when no verification ran
                            CHECK (hash_mode IN ('none', 'sample', 'all')),
    started_at          TEXT NOT NULL,
    finished_at         TEXT,                               -- NULL = interrupted / never completed
    n_files             INTEGER,
    total_bytes         INTEGER,
    verification        TEXT NOT NULL DEFAULT 'skipped'
                            CHECK (verification IN ('pass', 'fail', 'skipped')),
    performed_by        TEXT NOT NULL,
    notes               TEXT,
    manifest_path       TEXT,                               -- per-file manifest of a copy or archive
    manifest_sha256     TEXT                                -- SHA-256 of the manifest file, lower-case hex
                            CHECK (manifest_sha256 IS NULL OR (length(manifest_sha256) = 64
                                   AND manifest_sha256 NOT GLOB '*[^0-9a-f]*')),
    dismissed_at        TEXT,                               -- "Forget" on an unfinished copy or archive

    CHECK (range_end_unix IS NULL OR range_start_unix IS NULL OR range_end_unix >= range_start_unix),
    -- parent_id: required on a 'delete', allowed on a 'check' (check before delete, D55)
    CHECK (CASE operation WHEN 'delete' THEN parent_id IS NOT NULL
                          WHEN 'check' THEN 1
                          ELSE parent_id IS NULL END),
    CHECK (dismissed_at IS NULL OR operation IN ('copy', 'archive'))
);

CREATE INDEX idx_transfer_recording ON transfer_log(recording_id);

-- A row with parent_id (a 'delete', or a check before delete, D55) must follow an
-- archive of the same recording that passed verification. A delete row without
-- parent_id fails the CHECK above.
CREATE TRIGGER trg_transfer_delete_insert
BEFORE INSERT ON transfer_log
FOR EACH ROW
WHEN NEW.parent_id IS NOT NULL
 AND NOT EXISTS (SELECT 1 FROM transfer_log p
                 WHERE p.id = NEW.parent_id AND p.operation = 'archive'
                   AND p.verification = 'pass' AND p.recording_id = NEW.recording_id)
BEGIN
    SELECT RAISE(ABORT, 'a delete or its check must follow a passed archive of the same recording');
END;

CREATE TRIGGER trg_transfer_delete_update
BEFORE UPDATE OF operation, parent_id, recording_id ON transfer_log
FOR EACH ROW
WHEN NEW.parent_id IS NOT NULL
 AND NOT EXISTS (SELECT 1 FROM transfer_log p
                 WHERE p.id = NEW.parent_id AND p.operation = 'archive'
                   AND p.verification = 'pass' AND p.recording_id = NEW.recording_id)
BEGIN
    SELECT RAISE(ABORT, 'a delete or its check must follow a passed archive of the same recording');
END;
