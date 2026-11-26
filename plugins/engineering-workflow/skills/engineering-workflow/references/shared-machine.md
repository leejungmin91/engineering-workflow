# The shared machine

Several sessions on one computer share its disk, build caches, and devices. A change one session makes there (a cache moved to another disk, a tool upgraded, a phone unplugged) reaches the others only if they are told, and a full disk stops every build at once.

## Notices

`scripts/notices.py` keeps a list every session sees once, at its next prompt, including sessions started later. Messages to single sessions miss the ones that are closed and give no sign they were read.

```sh
python3 scripts/notices.py add "Build caches moved to /Volumes/SSD/dev-cache; keep the links, do not recreate the folders" --days 14
python3 scripts/notices.py add "idle-rpg: game/Builds is now a link to the SSD" --project ~/Documents/idle-rpg
python3 scripts/notices.py list
python3 scripts/notices.py remove <id>
```

- A notice lasts `--days` (14 by default). `--project` shows it only to sessions working inside that folder.
- The `notices` hook adds unseen notices to the prompt, at most five at a time, labelled as information from other sessions and not the user's instructions. It remembers what each session has seen in `~/.cache/engineering-workflow/notices/seen/` (`HARNESS_NOTICES` moves the folder).
- Write notices for facts about the machine. Product questions and requests still go to the user.

## Disk space

- The same hook warns, at most once an hour per session, when free space on `/` (`HARNESS_DISK_PATH`) is below `HARNESS_DISK_MIN_GB` gigabytes (10 by default).
- `python3 scripts/artifacts.py space --min-gb 10` exits 1 below the floor; a build script can call it first.

## Moving old check folders

`scripts/artifacts.py` moves check output that nobody uses any more to another disk and leaves a link at the old path, so records that name the path still open while the disk is mounted.

```sh
python3 scripts/artifacts.py old ~/Documents/app --days 2
python3 scripts/artifacts.py archive ~/Documents/app --to /Volumes/SSD/archive --dry-run
python3 scripts/artifacts.py archive ~/Documents/app --to /Volumes/SSD/archive
```

- It considers folders in `.harness/` (`--folder`) named `*_checks*` or `*_work` (`--glob`, repeatable), and skips links, folders with any file changed in the last `--days`, folders whose name appears in `WORKING.md`, and folders with files tracked by Git (and every folder when the project is not a Git repository).
- For each folder it checks that no process has a file open in it (`lsof`), copies it, and compares the copy byte for byte. If anything differs, it removes the copy and leaves the folder alone. Then it renames the original to `<name>.moving` and puts the link in its place; writes from then on go to the archive. It never copies the original over the archive again, so an update made through the link is kept. If the original changed after the comparison (a process held a file open), it stays as `<name>.moving` and the command exits 1; otherwise it is removed.
- A folder with a relative link that points outside it is skipped, because the link would point somewhere else from the archive.
- If the link cannot be made, the original is renamed back and the copy removed.
- Limit: a process that opens a file in the folder in the last moment before the original is removed (after the final `lsof` check) can still lose that write. Only folders unchanged for `--days` are moved, which keeps this rare; do not lower `--days` for folders a running job uses.
- It stops with exit 2 when the archive folder is missing (the disk is not mounted).
- Folders a build refills in place (`rsync ... "$DIR/"`, `rm -rf "$DIR/sub"`) keep working through a link; a folder the build deletes and recreates whole drops the link and lands on the internal disk again.
