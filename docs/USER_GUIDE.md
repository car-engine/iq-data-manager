# IQ Data Manager: user guide

IQ Data Manager keeps a catalogue of RF IQ recordings in a shared database. It logs a
recording folder into the catalogue, shows the catalogue, archives recordings from a
laptop to the NAS, and copies recordings or time ranges to a PC.

The app has four tabs: Viewer, Log recording, Archive / copy and Settings.

The mouse wheel scrolls the page and never changes a dropdown or a number field. To
change one, click it and pick from its list, or use its arrows or the arrow keys.

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
2. **Recording.** Start and end come from the scan. Check the file duration, type
   your name in **Logged by**, choose the site (or **Add site**), and fill in the plan
   reference and remarks. Your name stays for the next folder until you click
   **Clear form** or close the app. Choose the
   project the recording belongs to, or **Add project**. A project is optional; leave
   "No project" if none applies.
3. **File format.** Sample type, IQ layout, endianness and header bytes. The defaults
   are `int16`, `interleaved_iq` (I then Q for each sample), `little` (little-endian)
   and 0 header bytes.
4. **Channels.** For each channel, enter the centre frequency in MHz, the band and the
   sample rate. The app fills in the band from the centre frequency, and the sample
   rate from the file sizes; check both. The centre frequency is the frequency on air.
   For a recording made through a down-converter, type the frequency on air over the
   frequency the recorder tuned to.
5. **RF chain.** Rows such as SDR, antenna or LNA, for the whole recording or for one
   channel.

**Band.** When you enter or change a centre frequency, the band follows it, by this
table. Each band starts at its lower edge and ends just below its upper edge, so
300 MHz is UHF.

| Band | From | Up to |
| --- | --- | --- |
| HF | 3 MHz | 30 MHz |
| VHF | 30 MHz | 300 MHz |
| UHF | 300 MHz | 1 GHz |
| L | 1 GHz | 2 GHz |
| S | 2 GHz | 4 GHz |
| C | 4 GHz | 8 GHz |
| X | 8 GHz | 12 GHz |
| Ku | 12 GHz | 18 GHz |
| K | 18 GHz | 27 GHz |
| Ka | 27 GHz | 40 GHz |

A band filled in this way shows in italics. A band you type or pick yourself stays when
the frequency changes. If the frequency then lies outside that band, the checklist says
so; this does not stop you saving. A frequency outside the table clears a band that was
filled in from the frequency.
The list also offers the other bands already in the catalogue.

The **Before saving** checklist shows what is still to do and what is wrong. **Save
entry** is possible when the checklist shows no error and nothing to do. The fields
show the same: a field you still have to fill in has an amber frame and reads
**Required** while it is empty; a field with a wrong value has a red frame, and
pointing at it shows why. The line under
the buttons shows the result of what you did last, with the same marks: ✓ done, ⓘ
done with something to check, ✗ not done.

**The next folder.** When you choose the next folder, the form keeps what you
typed for the last one: the recording fields, the file format, the band and centre
frequency of each channel, and the RF chain. The scan fills in the start and end, the
sample rate and the file duration again. A note above the checklist names what was
kept; check it for the new folder. If the new folder lacks a channel, the values of
that channel are removed, and the line under the buttons says which. **Clear form**
starts again from empty fields.

**Recorder logs.** A folder made by the recording task holds the recorder's log
files. The scan reads them and fills in the centre frequency and sample rate of each
channel, the sample type, and the RF chain rows USRP gain and Clock reference. It
fills in USRP only when the form has no USRP row, because the log cannot tell a
USRP-2954 from an X310 with UBX boards. These values show in italics; type over any
of them to change it. Lines in the checklist name what was filled in, and warn when
the times came from the PC clock, GPS was not locked, or the folder holds fewer files
than the recorder wrote. These lines do not stop you saving.

**Several recordings with one set-up.** Choose **Several folders** at the top of the
tab.

1. Click **Add folders...** and choose the folder that holds the recordings, for
   example the folder of one day. The recording folders inside it are listed and
   scanned, one after another. If the folder you chose is itself a recording, click
   **Add it as one recording**.
2. Fill in the fields that are the same for all of them once: logged by, site,
   project, plan reference, remarks, the file format and the RF chain. A template
   fills these too.
3. Each folder takes its times, channels, centre frequencies, sample rates, band and
   the recorder's values from its own scan and log. The table lists them, with a
   state for each folder. Under the RF chain, a second table shows the rows the
   selected folder takes from its recorder's log, such as the USRP gain, the clock
   reference and the USRP. These rows are saved with that folder, in place of any
   row of the same name typed above, and the line under the table names such a row.
   To change one of these values for one folder, untick the folder and log it with
   **One folder**.
4. The checklist names what still stops a save, once for all folders where it is the
   same. Click a folder to see its own checklist and its channels; type a missing
   centre frequency there, for example for a folder without a recorder log.
5. Untick a folder to leave it out. A folder that is already logged starts unticked.
6. Click **Save N entries**. Each folder is saved as its own entry. If one cannot be
   saved, the table says why, and the others are saved. Saved folders stay in the
   list, marked with their recording number; the save button then saves only the
   folders left.

Edit mode and **Delete entry...** work in **One folder** mode only. The list is not
kept when you close the app; the app asks first while folders are not saved.

**Templates.** A template file holds fields you use often, such as the USRP, the
antennas and the band and frequency of each channel.

- **Export template...** asks which fields to save; empty fields start unticked.
  Then choose a file name. Keep shared templates in a common folder.
- **Import template...** fills in the fields the file holds and leaves the others.
  The sample rate, the times and the file duration always come from the scan.
- If you import a template after the scan, and it holds other values than the ones
  the recorder's log filled in, a window lists both. **Keep the log's values** fills
  in the rest of the template; the log describes this recording. **Use the
  template's values** fills in all of it. **Cancel** changes nothing.
- A site or project that is not in the catalogue is named under the buttons and not
  chosen. Choose it, or add it with **Add site** or **Add project**.

A folder that is already logged shows **Edit existing entry**. In edit mode, a change
to the sample rate, sample type, header or file duration needs a new scan first. The
site, the project, the remarks and the RF chain change without a scan.

**Deleting an entry added by mistake.** Open the entry with **Edit entry** in the
Viewer, or **Edit existing entry** here, and click **Delete entry...**. A window names
the recording, its folder and its files, and asks first; **Cancel** is the default.
The delete removes the entry from the catalogue only. The files in the folder stay
where they are. Before the delete, the app saves a copy of the entry in the folder
`deleted-entries` next to the settings file, and the line under the buttons names the
file. Check results of the entry are deleted with it. An entry that was archived or
copied cannot be deleted; correct it with **Save entry** instead. Remove a recording
from the Archive / copy queue before you delete it. If you delete the newest entry,
the next entry anyone logs gets its number. A queue item made for the deleted entry
then does not run, and says why.

A folder under a NAS location is logged as archived. The Viewer shows it as "archived,
not verified" until a comparison with the laptop copy passes (section 5).

## 4. Viewer

The Viewer lists the catalogue.

- **Filters.** Start date, site, project, band, frequency range, archive state, RF
  chain text and remarks. Click **Apply**, or press Enter.
- **Several sites, projects or bands.** Open the list and tick each one you want.
  Nothing ticked shows all. Two ticked sites show the recordings of either site. In
  the project list, **No project** shows the recordings that have no project, and
  it can be ticked together with projects. **Clear** unticks everything.
- **Recordings and channels.** Select a recording to see its channels and details,
  including the RF chain and the transfer history. Select a channel to narrow the
  details to it.
- **Marks.** Amber marks a coverage below the threshold set in Settings. It also
  marks a recording logged on the NAS that was never compared with its laptop copy:
  "archived, not verified".
- **Scan for gaps** reads the folder and shows the missing seconds per channel. It
  changes nothing.
- **Edit entry** opens the recording in the Log recording tab.
- **Archive / copy** opens the recording in the Archive / copy tab, on the page that
  suits it (section 5).
- **Add to queue** adds every selected recording to the queue in the Archive / copy
  tab (section 5). Select several with Ctrl or Shift. Choose **Archive or copy** or
  **Check archive**. The other buttons work on one selected recording.
- **Open folder** opens the recording folder.

## 5. Archive / copy

The tab works on recordings that are already logged. Load one with the Viewer's
**Archive / copy** button, with **Pick in Viewer**, or by its ID and **Load**.

The tab has three pages under the recording: **Archive**, **Check** and **Copy**. The
page you choose sets what **Preview** and **Run** do. The preview is on the right. The
queue and the unfinished transfers are two tabs at the bottom; drag the bar above
them to give them more room. While an operation runs, the pages are locked.

The Viewer's **Archive / copy** button opens the Archive page for a recording on the
laptop, and for an archived recording whose laptop copy is still to be checked or
deleted. It opens the Copy page for any other recording. **Load** keeps the page you
are on.

### Archive to the NAS

An archive copies a whole laptop recording to the NAS, checks the copy, and points the
catalogue entry at the NAS copy. The laptop copy stays until you delete it.

1. On the **Archive** page, choose the **NAS folder for archives**. The destination
   becomes that folder plus the recording's own folder name. You can change it.
2. Choose **Compare**: hashes of a sample of the files, or of every file.
3. Click **Preview**, then **Run archive**.
4. When the copy has passed its check, **Check before delete** runs straight away. It
   reads the NAS files again from the NAS itself, past the PC's memory, and compares
   their hashes with the hashes taken during the archive. The preview's estimated time
   does not include it.
5. When it passes, the result line says so, and **Delete laptop copy...** under
   **Laptop copy** becomes available. It asks first, names the folder, the number of
   files and the size, and defaults to No.

If Check before delete does not pass, the archive still stands: the recording points
at the NAS copy, and the laptop copy stays. The result line is amber and says why.
Click **Check before delete** to run it again. **Stop** during the check stops only
the check.

The Archive page has no "Sizes only", because Check before delete reads the content of
the files.

### Copy to a PC

A copy leaves the catalogue entry unchanged.

1. On the **Copy** page, choose **Whole recording** or **Time range**, and the
   channels. Times use the display offset; Unix seconds are shown next to them.
2. Check the **Folder for copies**. It starts as the default copy folder in Settings.
   A change here lasts until the app closes and does not change Settings. The
   destination becomes that folder plus the recording's folder path. You can change
   it.
3. Choose **Compare**, the check after the copy. "Sizes only" compares the file sizes
   and reads no content.
4. Click **Preview**. The preview shows the files, the size, the missing seconds, the
   estimated time and any problem with the destination.
5. Click **Run copy**.

### Check

- **Check archive** compares a NAS folder with its catalogue entry: channels, file
  counts and sizes.
- **Compare with laptop copy...** shows for a recording that was logged on the NAS and
  never compared with its laptop copy. It compares the NAS folder with a laptop folder
  you choose, with the **Compare** choice under it. A passed comparison removes the
  "not verified" mark. It does not allow deleting the laptop copy.

### Log files

Every copy and archive also takes the `.txt` and `.log` files in the recording folder
itself, such as the recorder's logs, even when it copies only some channels or a time
range. The preview names them. Delete laptop copy deletes them with the data. A
recording archived before version 1.1 keeps its log files on the laptop.

### Queue

The queue runs several archives, copies and Check archive runs one after another.
Each archive in the queue is followed by its Check before delete, as from the Archive
page.

1. Add recordings:
   - In the Viewer, select them and click **Add to queue**, then **Archive or copy**
     or **Check archive**. Laptop recordings are archived into the **NAS folder for
     archives** on the Archive page, with that page's Compare choice. Archived
     recordings are copied into the **Folder for copies** on the Copy page, with that
     page's Compare choice. Each recording goes into a folder of its own name.
   - Or set up one transfer on the Archive or Copy page, click **Preview**, then **Add
     to queue** in place of Run. Use this for a copy of some channels or a time range.
2. If that folder is not chosen yet, the items join the queue as **○ Needs a NAS
   folder** or **○ Needs a copy folder**. The tab opens the page with the folder, and
   the field has an amber frame. Type the folder and press Enter, or click
   **Browse...**. The waiting items then get their destinations. **Start** stays off
   while that folder is empty, and a line under the queue says which folder.
3. To change an item, select it and click **Edit**. It goes back to its page, Archive
   or Copy. Change it, click **Preview**, then **Add to queue** puts it back in its
   place. Use this to archive a recording to another NAS folder.
4. Click **Start**. The items run one after another. Each is checked again just
   before it starts; an item that cannot start is marked and the queue goes on.
5. **Pause** stops the running item. Files already copied stay. The **Start** button
   then reads **Resume**: it continues with that item and does not copy them again.
   A pause during Check before delete stops the check; the item is then marked
   **ⓘ Archived, check needed** (below).
6. A transfer that is waiting or paused in the queue runs only from the queue. If you
   set it up on its page, **Run** stays off, and a line under the buttons says so. To
   run it from the page instead, select it in the queue and click **Remove**.

You can add recordings while the queue runs. The two folder fields stay usable, so
items that wait for a folder can get it; the running queue then runs them in their
turn.

Delete each laptop copy afterwards on the Archive page with **Delete laptop copy...**,
one recording at a time.

An item marked **ⓘ Archived, check needed** was archived: the recording points at
the NAS copy. Only its Check before delete did not pass, so its laptop copy cannot be
deleted yet. Select the item to read why, then load the recording and click **Check
before delete** on the Archive page. **Clear finished** leaves these items in the
queue; **Remove** takes one out.

The queue is not kept when the app closes. A paused copy or archive stays under
**Unfinished transfers**.

The queue's **Resume** and **Open in form** under Unfinished transfers do different
things. **Resume** runs the queue again: the paused item, then every waiting item.
**Open in form** loads one stopped transfer onto its page, where **Run** continues it
on its own. While the queue still holds that transfer, use **Resume**.

### Stopping and resuming

**Stop** asks first. Files already copied stay. A stopped copy or archive appears
under **Unfinished transfers**. Select it and click **Open in form** to fill in its
page again; the preview then names the files already in place, which are not copied
again. Click **Run** to continue it.
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
