# IQ Data Manager: release notes

## Version 1.0.0 (2026-10-12)

The first release for the team. It replaces the logging scripts and hand-made copies
of recordings.

### What it does

- **Viewer.** Lists the catalogue, with filters for start date, site, project, band,
  centre frequency, archive state, RF chain and remarks. It shows each recording's
  channels, RF chain, details and transfer history, and finds the gaps in a recording
  folder.
- **Log recording.** Scans a recording folder, fills in the sample rate and the file
  duration from the files, checks the file sizes, and saves the recording with its
  channels, RF chain, site and project. Edit entry corrects a recording later.
- **Archive / copy.** Copies a recording, or a time range and some of its channels, to
  a PC. Archives a recording from a laptop to the NAS and points the catalogue at the
  NAS copy. Each transfer shows a preview first, checks the copy afterwards, can stop
  and resume, and never replaces a file.
- **Deleting the laptop copy** is a separate step. It is possible only after the
  archive passed its check and a later "Check before delete" read the NAS copy again
  from the NAS itself. It asks first.
- **Settings.** The database file, the NAS locations, the display time zone and the
  transfer settings, with a check of the database. A shared `defaults.toml` in the
  program folder gives new PCs their settings.
- **`IQDataManager-check.exe`** imports the legacy catalogue into a new database and
  runs the checks used in the NAS tests.

### Safety

- A copy or an archive never replaces or deletes a file. Each file is written under a
  temporary name and renamed only when it is complete.
- The destination must not be the source folder, lie inside it, or hold it. Since
  this release the app also notices one folder that is reached under two names, for
  example the NAS by host name and by IP address, and refuses it.
- If a recording changes while it is open in Edit entry, for example because it was
  archived, Save writes nothing and asks you to open the entry again.
- The app deletes only the laptop files listed for a checked archive, one by one,
  after checking that each NAS copy is still there with the right size.

### Before the team starts

The person who sets up the program:

1. Creates the shared catalogue with the legacy import (user guide, section 8), puts
   it on the NAS, and runs Check archive on each imported recording.
2. Fills in `defaults.toml` from `defaults.example.toml` with the database and the NAS
   locations, and the copy settings measured on the network (user guide, section 1).
3. Sets up a regular backup of the catalogue file outside the app, for example a NAS
   snapshot.
4. Tries one real recording first: archive it, run Check before delete, and delete its
   laptop copy while watching.

### Known limits

- **Older databases.** Databases made with test builds from before projects were
  added, such as the trial catalogue of the second NAS visit, show as an older version
  and cannot be opened. Make them again. The app has no "Upgrade database" button yet;
  it comes with the first change to the database format.
- **Many small files copy slowly to the NAS**, about 18 to 25 ms per 64 KB file. A day
  of one-second files takes about 26 minutes per channel.
- **Check before delete** needs a check that reads file contents ("Sizes and hashes"
  of a sample or of every file). It cannot run through a Windows share that the same
  PC serves to itself; use the real NAS.
- **Recordings cannot be removed from the catalogue** in the app. Correct a wrong
  entry with Edit entry.
- **Imported legacy recordings** are taken as one-second files of int16 samples,
  interleaved I then Q, with no header. They stay marked "archived, not verified"
  until Compare with laptop copy passes.
- **Times** come from each PC's clock. Set the clocks automatically (user guide,
  section 1).
- **Long paths** above 259 characters need the Windows long-path setting (user guide,
  section 1).
- Windows 10 and 11 only.
