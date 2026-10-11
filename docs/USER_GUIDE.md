# IQ Data Manager: user guide

IQ Data Manager keeps a catalogue of RF IQ recordings in a shared database. It logs a
recording folder into the catalogue, shows the catalogue, archives recordings from a
laptop to the NAS, and copies recordings or time ranges to a PC.

The app has four tabs: Viewer, Log recording, Archive / copy and Settings.

## 1. Setting up the program

This section is for the person who prepares the program for the team.

### The program folder

The program is a folder named `IQDataManager`. Copy the whole folder to each PC, for
example as a zip file, and keep its contents together. It holds:

- `IQDataManager.exe`, the app;
- `IQDataManager-check.exe`, a console program for checks and the legacy import
  (section 8);
- `USER_GUIDE.md`, this guide;
- `RELEASE_NOTES.md`, what this version does and its known limits;
- `defaults.example.toml`, a template for the shared settings.

### Shared settings for new PCs

Each PC keeps its own settings file, `%APPDATA%\IQDataManager\config.toml`. A new PC
has none, so the app starts without a database.

To give new PCs the shared database and the NAS locations:

1. Open `defaults.example.toml` in a text editor.
2. Replace the example values with the real database path and NAS locations.
3. Save the file as `defaults.toml` in the program folder, next to
   `IQDataManager.exe`.

The app reads `defaults.toml` only while the PC has no settings file. The first Save
in the Settings tab writes the values to the PC's own settings file. From then on,
that PC ignores `defaults.toml`. A later change to `defaults.toml` does not reach a PC
that already has a settings file. On such a PC, change the setting in the Settings
tab.

### Long paths

Windows limits a path to 259 characters, unless long paths are enabled. The app
refuses a copy or an archive whose paths are too long for the PC. To allow longer
paths, an administrator sets the registry value `LongPathsEnabled` to 1 under
`HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem`, then restarts the
PC. The same setting is in the Group Policy editor as "Enable Win32 long paths".

### Clocks

The app records when each recording was logged and when each transfer ran, by the
clock of the PC that did it. A PC whose clock is wrong shows wrong times in the
history. Copies, archives, checks and deletes work correctly regardless.

- On a PC with internet access, turn on Settings > Time & language > Date & time >
  "Set time automatically".
- On a network without internet, an administrator can make the NAS the time server:
  turn on its time service (often called NTP service), then on each PC run
  `w32tm /config /manualpeerlist:<NAS address> /syncfromflags:manual /update` as
  administrator.

### Copy speed settings

Two settings in the Transfers section depend on the network:

- **Files copied at once.** Copying several files at once fills a fast link better.
  The best number depends mostly on the link and on the file size:

  | Link and files | Files at once |
  | --- | --- |
  | 10 GbE, large files | 8 or more |
  | Gigabit Ethernet | 2 to 4 |
  | Wi-Fi | 1 or 2 |
  | Many small files | 4 to 8; it makes little difference |

- **Network speed.** The app uses it only for time estimates. Set it to the speed the
  copy check measures.

To measure, run the copy check on a typical laptop. Use a local copy of a real
recording as the source and a scratch folder on the NAS as the destination:

```
IQDataManager-check.exe copy-check \\server\share\scratch\cc --source D:\some-recording --workers 1 4 8 16 --fsync on
```

Choose the number of files with the shortest copy time, and take its MB/s as the
network speed. Put both in `defaults.toml` for the team. Remove the scratch folder
afterwards.

## 2. Settings

Open the Settings tab first on a new PC.

- **Database file.** The catalogue database. Use **Browse...** to choose a file,
  or **New database...** to create an empty one (section 7). The line below the field
  shows whether the app can use the database:
  - green ✓: ready to use;
  - amber ○: no database chosen, or a check in progress;
  - amber ⓘ: a database from a newer version of the app, which this version can only
    read;
  - red ✗: the file is missing, cannot be opened, is not an IQ Data Manager database,
    or comes from an older version.

  **Check connection** checks the file again.
- **NAS locations.** Network locations written as `\\server\share` or
  `\\server\share\folder`. A recording folder under one of them counts as already on
  the NAS.
- **Display.** The UTC offset for every time on screen, and the coverage below which
  the Viewer marks a recording. The database always stores UTC.
- **Transfers.** The default folder for a copy to a PC, the network speed for time
  estimates, the default check after a copy, the share of files a sample check hashes,
  the free space kept on a destination, and the number of files copied at once.

Click **Save** to write the settings. They apply at once. The previous settings are
kept as `config.toml.bak` in the same folder. **Open folder** shows that folder.

While a change is not saved, the tab's title reads "Settings (not saved)". If you
leave the tab or close the window first, the app asks whether to save the changes,
drop them, or stay on the tab.

Amber lines marked ⓘ say where the values come from when it is not the PC's own
settings file: the shared defaults file, or a file or database given when the app
was started.

The status bar at the bottom of the window always names the database in use.

## 3. Log recording

The Log recording tab adds a recording folder to the catalogue.

1. **Source folder.** Click **Browse...** and choose the recording folder. A folder
   with channel folders `0`, `1` and so on is one recording with several channels.
   Click **Scan folder**.
2. **Recording.** Start and end come from the scan. Check the file duration, choose
   the site (or **Add site**), and fill in the plan reference and remarks. Choose the
   project the recording belongs to, or **Add project**. A project is optional; leave
   "No project" if none applies.
3. **File format.** Sample type, IQ layout, endianness and header bytes. The defaults
   are `int16`, `interleaved_iq` (I then Q for each sample), `little` (little-endian)
   and 0 header bytes.
4. **Channels.** For each channel, enter the band, the centre frequency in MHz and the
   sample rate. The app fills in the sample rate from the file sizes; check it.
5. **RF chain.** Rows such as SDR, antenna or LNA, for the whole recording or for one
   channel.

The **Before saving** checklist shows what is still to do and what is wrong. **Save
entry** is possible when the checklist shows no error and nothing to do.

A folder that is already logged shows **Edit existing entry**. In edit mode, a change
to the sample rate, sample type, header or file duration needs a new scan first. The
site, the project, the remarks and the RF chain change without a scan.

A folder under a NAS location is logged as archived. The Viewer shows it as "archived,
not verified" until a comparison with the laptop copy passes (section 5).

## 4. Viewer

The Viewer lists the catalogue.

- **Filters.** Start date, site, project, band, frequency range, archive state, RF
  chain text and remarks. Click **Apply**, or press Enter. The project filter can
  also show the recordings that have no project.
- **Recordings and channels.** Select a recording to see its channels and details,
  including the RF chain and the transfer history. Select a channel to narrow the
  details to it.
- **Marks.** Amber marks a coverage below the threshold set in Settings. It also
  marks a recording logged on the NAS that was never compared with its laptop copy:
  "archived, not verified".
- **Scan for gaps** reads the folder and shows the missing seconds per channel. It
  changes nothing.
- **Edit entry** opens the recording in the Log recording tab.
- **Archive / copy** opens the recording in the Archive / copy tab.
- **Open folder** opens the recording folder.

## 5. Archive / copy

The tab works on recordings that are already logged. Load one with **Pick in Viewer**,
or with the Viewer's **Archive / copy** button.

### Copy to a PC

A copy leaves the catalogue entry unchanged.

1. Choose **Copy to a PC**.
2. Choose **Whole recording** or **Time range**, and the channels. Times use the
   display offset; Unix seconds are shown next to them.
3. Check the destination. It starts as the default copy folder plus the recording's
   own folder path.
4. Choose the check after the copy.
5. Click **Preview**. The preview shows the files, the size, the missing seconds, the
   estimated time and any problem with the destination.
6. Click **Run copy**.

### Archive to the NAS

An archive copies a whole laptop recording to the NAS, checks the copy, and points the
catalogue entry at the NAS copy. The laptop copy stays until you delete it.

1. Choose **Archive to the NAS** and a new folder under a NAS location.
2. Click **Preview**, then **Run archive**.
3. Click **Check before delete**. It reads the NAS files again from the NAS itself,
   past the PC's memory, and compares their hashes with the hashes taken during the
   archive. Choose a check that includes hashes; "Sizes only" is refused.
4. When the check passes, **Delete laptop copy...** becomes available. It asks
   first, names the folder, the number of files and the size, and defaults to No.

### Other checks

- **Check archive** compares a NAS folder with its catalogue entry: channels, file
  counts and sizes.
- **Compare with laptop copy...** compares a recording that was logged on the NAS
  with a laptop folder you choose. A passed comparison removes the "not verified"
  mark. It does not allow deleting the laptop copy.

### Stopping and resuming

**Stop** asks first. Files already copied stay. A stopped copy or archive appears
under **Unfinished transfers**. Select it and click **Resume** to fill in the form
again; the preview then names the files already in place, which are not copied again.
**Forget...** removes a row from the list and leaves the files.

## 6. When something goes wrong

- **"Database file not found."** Check the path in the Settings tab and the network
  connection.
- **"The database is in use by someone else."** Another PC is writing. Try again in
  a minute.
- **A line about an older or newer version.** The database and the app come from
  different versions. Ask the person who set up the program.
- **The settings file has a wrong value.** The Settings tab marks the field. Correct
  it and click Save.

## 7. A private database

A project may keep its recordings in a database of its own.

1. In the Settings tab, click **New database...** and choose a new file name.
2. The app asks before it creates the file. Click **Yes**.
3. Click **Save** to use the new database.

Recordings saved in a private database do not appear in the shared catalogue. Other
people see them only if they choose the same file. To go back, choose the shared
database file in the Settings tab and click Save.

## 8. The console program

`IQDataManager-check.exe` runs in a Command Prompt window. Run it without options to
list its commands, and with `COMMAND --help` for the options of one command.

- `db-check` creates a scratch database, or checks opening, writing and locking.
  Use it on a scratch database only.
- `copy-check` measures copy speed to a folder.
- `make-test-set` writes synthetic recordings for a test.
- `migrate-legacy` imports the legacy catalogue (below).

### Importing the legacy catalogue

This is for the administrator, once, when the shared catalogue is created.

1. Make a copy of the legacy database file. Work on the copy.
2. Run a dry run first:

   ```
   IQDataManager-check.exe migrate-legacy legacy-copy.db catalog.db --nas-root \\server\share\folder --dry-run
   ```

   Give one `--nas-root` for each NAS location. If `data_dir` values use a mapped
   drive letter, add `--drive Z:=\\server\share` for each letter.
3. Read the report. It lists the rows that cannot be imported, with the reason, and
   warnings for rows that were imported.
4. Run the same command without `--dry-run`. It writes `catalog.db` and the report
   `catalog.db.report.txt`. The new file must not exist yet.
5. Put the new database on the NAS and set it as the database file on each PC, or in
   `defaults.toml`.
6. Run **Check archive** once on each imported recording, in the Archive / copy tab.
7. Set the project of each imported recording with **Edit entry**. The legacy table
   has no projects, so imported recordings start with none.

The legacy table holds only the day of each recording. Until Check archive runs, an
imported recording starts at midnight of its day, and its file counts and sizes are
unknown. Check archive reads the recording's folder on the NAS and takes the counts,
the sizes and the real start and end of each channel from its files. If the files
are spaced differently from one second, the check says so. Correct the file duration
in the Log tab's edit mode.

Every imported recording stays marked "archived, not verified" until a comparison with
another copy passes. The import assumes one-second files of int16 samples,
interleaved I then Q, with no header.
