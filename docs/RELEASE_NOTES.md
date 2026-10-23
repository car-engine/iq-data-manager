# IQ Data Manager: release notes

## Version 1.2.1 (2026-10-23)

Fixes from the team's feedback on version 1.2. It uses the same catalogue; nothing
needs to be upgraded. Install it in a new program folder, and copy `defaults.toml`
across.

### What changed

- **The mouse wheel no longer changes fields.** Turning the wheel over a dropdown or
  a number field scrolls the page and leaves the field as it was, in every tab. To
  change a field, click it and pick from its list, or use its arrows or the arrow
  keys. An open list still scrolls with the wheel.
- **Logged by is your name.** The field starts empty, and you type your name; before,
  it held the Windows login, which on a shared laptop names the laptop. Your name
  stays for the next folder until you click **Clear form** or close the app.
- **Fields to fill in are marked.** In the Log recording tab, a field you still have
  to fill in has an amber frame and reads "Required" while it is empty. A field with
  a wrong value has a red frame; point at it to see why. The **Before saving**
  checklist lists the same items, and the **Save** button's tooltip says what to do
  while it is disabled.
- **Several folders shows each folder's recorder values.** Below the RF chain, a
  table lists the rows the selected folder takes from its recorder's log, such as
  the USRP gain, the clock reference and the USRP. These rows were saved before too,
  but were not shown. A line under the table names any row typed above that they
  replace for that folder. To change one of these values for one folder, untick the
  folder and log it with **One folder**.

### Known limits

- Transfers, checks and deletes still record the Windows login under "By", as
  before.
- The limits of version 1.2.0 below still apply.

## Version 1.2.0 (2026-10-23)

Three additions to the Log recording tab. It uses the same catalogue as version 1.1;
nothing needs to be upgraded. Install it in a new program folder, and copy
`defaults.toml` across.

### What is new

- **The band from the centre frequency.** When you enter or change a centre
  frequency, the band fills in from this table: HF 3–30 MHz, VHF 30–300 MHz, UHF
  300 MHz–1 GHz, L 1–2 GHz, S 2–4 GHz, C 4–8 GHz, X 8–12 GHz, Ku 12–18 GHz, K
  18–27 GHz, Ka 27–40 GHz. A band filled in this way shows in italics and follows the
  frequency, also when the recorder's log of the next folder sets it. A band you type
  or pick yourself stays; if the frequency lies outside it, the checklist says so.
  The centre frequency is the frequency on air: for a recording made through a
  down-converter, type it over the frequency the recorder tuned to.
- **Deleting an entry added by mistake.** Open the entry with **Edit entry** and click
  **Delete entry...**. A window asks first. Only the catalogue entry goes; the files
  in the folder stay where they are. A copy of the entry is saved in the folder
  `deleted-entries` next to the settings file. An entry that was archived or copied
  cannot be deleted, nor one waiting in the Archive / copy queue.
- **Several recordings with one set-up.** Choose **Several folders** at the top of the
  Log recording tab, then **Add folders...** and the folder that holds the recordings,
  for example those of one day. Each folder is scanned and takes its times, channels,
  frequencies and recorder's values from its own scan and log. You fill in the fields
  they share once, or with a template. The table shows each folder's state, and the
  checklist names what still stops a save. Click a folder to fix it, for example to
  type a frequency where a folder has no recorder log. **Save** saves each folder as
  its own entry; a folder that cannot be saved says why, and the others are saved.

### Known limits

- **A deleted entry's number can be used again.** If you delete the newest entry, the
  next entry anyone logs gets its number. A queue item or a preview made for the
  deleted entry then does not run, and says why.
- **The folder list of Several folders is not kept** when the app closes; the app
  asks first while folders are not saved.
- **In Several folders mode, each folder takes its file duration from its file
  names.** A folder with a single file per channel gets 1 s; log such a folder in One
  folder mode.
- The limits of the earlier versions below still apply, except that entries can now
  be deleted.

## Version 1.1.1 (2026-10-22)

Fixes for version 1.1.0. It uses the same catalogue; nothing needs to be upgraded.
Install it in a new program folder, and copy `defaults.toml` across.

### What changed

- **USRP gain.** Values from the recorder's log fill the RF chain row "USRP gain",
  spelled as in the catalogue. The checklist no longer reports on every scan that the
  spelling will change.
- **A template after the scan.** If you import a template after scanning a recorder
  folder, and the template holds other values than the log filled in, a window lists
  both. **Keep the log's values** fills in the rest of the template. **Use the
  template's values** fills in all of it. **Cancel** changes nothing. Before, the
  template replaced the log's values without a word, and they still showed as from
  the log.
- **Resume in the queue.** While a queue item is paused, the **Start** button reads
  **Resume**. A transfer that is waiting or paused in the queue runs only from the
  queue: in the form, **Run** stays off, and a line says why. Before, Run could finish
  a paused archive, and the queue then marked it "Not started".
- **Open in form.** The button under **Unfinished transfers** that loads a stopped
  transfer into the form is now called **Open in form**, so it is not confused with
  the queue's Resume.
- **A busy catalogue after an archive.** If the catalogue is in use by someone else
  when the queue runs Check before delete after an archive, the item shows "ⓘ
  Archived, check needed". Before, it showed "✗ Failed", although the archive had
  passed.
- **Smaller fixes.** The Pause question says what a pause during Check before delete
  does. An item taken out of the queue with Edit and then dropped no longer keeps its
  place for the next item. "The recorder restarted 1 time." Template export refuses to
  overwrite a file named like `<name>.toml.new` that someone else left in the folder.
  A USRP row kept from a channel the next folder lacks no longer stops the log's USRP
  row.

## Version 1.1.0 (2026-10-22)

Faster logging of many folders, and archives of many recordings in one go. It uses the
same catalogue as version 1.0.0; nothing needs to be upgraded. Install it over 1.0.0
in a new program folder, and copy `defaults.toml` across.

### What is new

- **Logging several folders.** When you choose the next folder, the Log recording tab
  keeps what you typed for the last one: the recording fields, the file format, the
  band and centre frequency of each channel, and the RF chain. The scan fills in the
  times, the sample rate and the file duration again. A note above the checklist
  names what was kept, so you can check it for the new folder. **Clear form** starts
  again from empty fields.
- **Values from the recorder's log.** For a folder made by the recording task, the scan
  reads the recorder's log files. It fills in the centre frequency and sample rate of
  each channel, the sample type, and the RF chain rows USRP Gain and Clock reference.
  It fills in USRP only when the form has none. These values show in italics. The
  checklist warns when the times came from the PC clock, GPS was not locked, or the
  folder holds fewer files than the recorder wrote.
- **Templates.** **Export template...** saves the fields you choose to a file, for
  example a USRP and its antennas. **Import template...** fills them in again. Keep
  shared templates in a common folder.
- **Viewer filters with several choices.** Site, project and band are lists with a tick
  box per entry. Tick two sites to see the recordings of either.
- **A queue in the Archive / copy tab.** Select several recordings in the Viewer and
  click **Add to queue**, or set one up in the form and add it in place of running it.
  **Start** runs them one after another; **Pause** stops the running one, and Start
  continues it without copying its files again. After each archive the queue can run
  Check before delete. **Check archive** can be queued for many recordings at once,
  for example the imported legacy ones.
- **The recorder's log files travel with the recording.** Every copy and archive also
  takes the `.txt` and `.log` files in the recording folder, and Delete laptop copy
  deletes them with the data.
- **Clearer messages.** The line under the Log tab's buttons shows ✓ for done, ⓘ for
  done with something to check, and ✗ for not done. In the queue, an archive whose
  Check before delete did not pass shows "ⓘ Archived, check needed", not "Failed":
  the recording is on the NAS, and only the check is still to do.

### Known limits

- **The queue is not kept** when the app closes. A paused copy or archive stays under
  "Unfinished transfers".
- **The recorder's log cannot tell a USRP-2954 from an X310 with UBX boards.** Keep a
  template that sets USRP to the right unit.
- **Recordings archived with version 1.0.0** keep their log files on the laptop after
  Delete laptop copy.
- **Check before delete through a Windows share that the same PC serves to itself**
  fails for files whose size is not a multiple of 512 bytes. The real NAS does not
  have this limit.
- The limits of version 1.0.0 below still apply, except where this section says
  otherwise.

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
