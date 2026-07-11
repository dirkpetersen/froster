# Froster Core Workflow Behavioral Specification

Extracted from `froster/froster.py` (v0.22.0, 8513 lines) by static analysis on
2026-07-10. This is the source of truth for implementing `go/internal/archive`,
`go/internal/restore`, and workflow wiring. All line numbers refer to that file.
All user-facing strings are emitted via `log()` (line 8347), which is
`print(..., flush=True)` plus append to `~/.local/share/froster/froster.log`
**only when** env `DEBUG=1`.

---

## 0. Shared constants, config, and helpers

### 0.1 Filenames and thresholds (Archiver.__init__, lines 3579–3615)

```python
self.thresholdKB = int(cfg.max_small_file_size_kib) if set else 1024   # line 3586-3587
self.smallfiles_tar_filename       = 'Froster.smallfiles.tar'          # 3599
self.allfiles_csv_filename         = 'Froster.allfiles.csv'            # 3600
self.md5sum_filename               = '.froster.md5sum'                 # 3601
self.md5sum_restored_filename      = '.froster-restored.md5sum'        # 3602
self.where_did_the_files_go_filename = 'Where-did-the-files-go.txt'    # 3603
self.dirmetafiles = [allfiles_csv, md5sum, md5sum_restored, where_did] # 3605-3608
```

Note `dirmetafiles` does **not** include `Froster.smallfiles.tar`.
`cfg.max_small_file_size_kib` is hardcoded to `1024` in ConfigManager (line
199) — it is not read from config.ini, so the effective tar threshold is always
1024 KiB unless the class default changes.

`self.output_disable = not sys.stdin.isatty()` (3613–3615) suppresses tqdm
progress bars when not a TTY.

### 0.2 froster-archives.json location (ConfigManager, lines 144–241)

- Default: `$XDG_DATA_HOME/froster/froster-archives.json`, falling back to
  `~/.local/share/froster/froster-archives.json` (lines 158–185).
- If `[SHARED] is_shared = True` in `config.ini`:
  `<shared_dir>/froster-archives.json` and
  `hotspots_dir = <shared_dir>/hotspots` (lines 229–238).
- Per-profile keys from `config.ini` section `self.profile`: `provider`,
  `credentials`, `bucket_name`, `archive_dir` (prefix inside the bucket, config
  default prompt fallback `'froster'`, line 1318), `storage_class`;
  `region`/`endpoint` come from the AWS credentials/config files (261–286).

### 0.3 DB read/write primitives

**`_archive_json_add_entry(key, value)` (5480–5511):** read whole JSON (dict)
if file exists (corrupt file → log `'Error in Archiver._archive_json_add_entry():'`
/ `'Cannot read {path}, file corrupt?'` and return without writing);
`data[key] = value`; `os.makedirs(dirname, exist_ok=True, mode=0o775)`; rewrite
whole file with `json.dump(data, file, indent=4)`. Plain overwrite — no
locking, no temp-file rename.

**`froster_archives_get_entry(folder)` (5565–5598):** returns `data[folder]`
on exact match; otherwise walks `pathlib.Path(folder).parents` and returns the
first parent entry whose `archive_mode == 'Recursive'`; else `None`. This is
how subfolders of a recursive archive resolve.

**`archive_get_bucket_info(folder)` (5518–5563):** from the entry:
`bucket, prefix = archive_folder.split('/', 1)`;
`bucket = bucket.replace(':s3:', '')`;
`prefix = prefix.replace(local_folder, '') + folder + '/'` (so for a subfolder
of a recursive parent the prefix is re-derived);
`is_recursive = (archive_mode == "Recursive")`;
`is_glacier = s3_storage_class in ['DEEP_ARCHIVE', 'GLACIER']`. Returns
`(bucket, prefix, is_recursive, is_glacier, profile, user)`; on missing entry
logs `\nFolder {folder} is not registered as archived` and returns six `None`s.

### 0.4 `_walker(top)` (5641–5658)

`os.walk(top, topdown=True, followlinks=False, onerror=self._walkerr)` with:
skip dirs named `.snapshot`; directory symlinks are moved from `dirs` into
`files` (treated as files). `_walkerr` (5660) writes the OSError to stderr and
continues.

### 0.5 Rclone invocation (class Rclone, 6286–6586)

- Binary: `<froster_dir>/rclone` (dir of the real `froster` executable, 6295).
- Env (6298–6321): `RCLONE_S3_ENV_AUTH=true`,
  `RCLONE_S3_PROVIDER=<cfg.provider>`, `RCLONE_S3_ENDPOINT`,
  `RCLONE_S3_REGION`, `RCLONE_S3_LOCATION_CONSTRAINT=<region>`,
  `RCLONE_S3_STORAGE_CLASS=<cfg.storage_class>`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY` (from `~/.aws/credentials` profile
  `cfg.credentials`), `HOME`, `RCLONE_AWS_NO_CHECK_SSO=true`. Missing
  credentials → `'\nError: No credentials found for Rclone to use.'` +
  `sys.exit(1)`.
- `copy(src, dst, *args)` (6428): `rclone copy <args...> <src> <dst> -vvv`
  (+ `--s3-no-check-bucket` when provider == `Ceph`), `--use-json-log` always
  appended.
- `checksum(md5file, dst, *args)` (6447):
  `rclone checksum md5 <md5file> <dst> <args...> --use-json-log`.
  Success = exit code 0.
- `mount(src, dst)` (6462): requires `fusermount3` on PATH else
  `'Could not find "fusermount3". Please install the "fuse3" OS package'` +
  `sys.exit(1)`; runs `rclone mount --allow-non-empty --default-permissions
  --read-only --no-checksum <src> <dst>` in background (Popen, output to
  /dev/null); success = a PID exists.
- `unmount(mountpoint)` (6487): `fusermount3 -u <mountpoint>`; success = rc 0.
- On non-zero rc of foreground commands (6374–6423), prints to stderr:
  ```
  \n        Error: Rclone {command[1]} command failed
          Return code: {ret.returncode}
          Return code meaning: {exit_codes[rc]}\n
  ```
  then tries to extract `stats.lastError` from the JSON log lines and prints
  `        Error: {error_message}\n`.
- `get_mounts()` (6519): parse `/proc/mounts`, return mount points whose fs
  type starts with `fuse.rclone`.

### 0.6 Path cleaning (main, 8444–8446)

Every subcommand's `folders` args are normalized with `clean_path` (8176):
`os.path.realpath(os.path.expanduser(path).rstrip('/'))` — symlinks resolved,
trailing slash removed. `mountpoint` is cleaned inside `Archiver.mount` (4473).

### 0.7 Credentials gate (main, 8463–8477)

`archive`, `restore`, `delete`, `mount` require `aws.check_credentials()`
(1664: `s3_client.list_buckets()` must succeed). On failure:

```
\nError: Invalid credentials.
  Profile: {cfg.profile}
  Provider: {cfg.provider}
  Credentials: {cfg.credentials}
  Endpoint: {cfg.endpoint}\n      (only if a profile is set)

\nYou can configure the credentials using the command:
    froster config\n
```

then `sys.exit(1)`. `index`, `umount`, `test`, `config`, `credentials`,
`update` skip this gate (8448–8462).

Exit code: `main` exits 1 if the subcommand returned falsy (8497–8498), exits 1
on KeyboardInterrupt (message `"\nOperation cancelled by user. Exiting...\n"`)
or any exception; otherwise 0.

---

## 1. `froster archive`

### 1.1 Entry: `subcmd_archive` (7359–7383)

1. If `--older > 0` and `--newer > 0`:
   `'\nError: Cannot use both --older and --newer flags together.\n'` (stderr)
   → return False (exit 1).
2. If `--reset` (`-s`): for each folder run
   `arch.reset_folder(folder, args.recursive)` (§1.8) and return True.
   No S3 access.
3. No folder args → interactive `arch.archive_select_hotspots()` (§1.2); else
   `arch.archive(args.folders)`.

Flags (parser 7967–8024): `folders*`, `-f/--force`, `-l/--larger <GiB>`,
`-o/--older <days>`, `-w/--newer <days>`, `-n/--nih`, `-i/--nih-ref <ref>`,
`-m/--mtime`, `-r/--recursive`, `-s/--reset`, `-t/--no-tar`, `-d/--dry-run`
(**parsed but never used anywhere**). Globals: `-c/--cores` (default
`$SLURM_CPUS_ON_NODE` or 4), `-m/--mem` (default `$SLURM_MEM_PER_NODE//1024`
or 16 GB), `-n/--no-slurm`, `-p/--profile`, `-d/--debug`.

### 1.2 Hotspot selection path: `archive_select_hotspots` (3958–4075)

1. No hotspots dir → print:
   ```
   \nNo folders to archive in arguments and no Hotspots CSV files found.
   \nFor archive a specific folder run:
       froster archive "/your/folder/to/archive"
   \n For index a folder a find hotspots run:
       froster index "/your/folder/to/index"\n
   ```
   return True.
2. No `*.csv` files in hotspots dir → `'\nNo hotposts found. \n'` (sic) plus
   index/archive hints → return True.
3. Sort CSVs by mtime descending; TUI
   `TextualStringListSelector("Select a Hotspot file", ...)`; nothing selected
   → return False.
4. `get_hotspot_folders(selected)` (4608) →
   `_filter_hotspots_by_write_access` (4507): if the CSV has ≥ 5000 lines,
   filtering is skipped (`Skipping proactive write permission check for large
   file ({n} lines): {path}`) and the original file is displayed; otherwise
   each row's `Folder` is tested with `os.access(path, W_OK)` (tqdm
   `"Checking write access"`), and a filtered per-user copy is written to
   `<hotspots_dir>/<username>/<same filename>` (reused if newer than source
   and not `--force`). No writable rows →
   `'\nNo writable hotspots found or accessible in {file}.\n'` → return True.
5. TUI `TableHotspots`; selecting a row opens a confirm modal (5845–5856):
   label `"Do you want to start this archiving job now?\nChoose 'Quit' if you
   would like to archive recursively"` with buttons **Start Job** (`continue`),
   **Back to List** (`return`), **Quit to CLI** (`quit`).
6. Folder path is row column index 5. If filtering had been skipped, a
   write-permission check runs now (`Checking write permission for selected
   folder: {folder}`; failure: `'\nError: Write permission denied for selected
   folder: {folder}\n'` → return False; success: `"  Permission granted."`).
7. Action `continue` → `self.archive([folder])`. Action `quit` → print a
   reconstructed command and return True:
   ```
   \nTo archive this folder later, run:\n
       froster archive[ --profile "<p>"][ --recursive][ --no-tar][ --nih-ref "<r>"][ --larger N][ --older N][ --newer N][ --mtime] "<folder>"\n
   ```

### 1.3 `Archiver.archive(folders)` (4266–4382)

1. `is_recursive = args.recursive`;
   `is_nih = cfg.is_nih or (args.nih and not args.nihref)`;
   `is_tar = not args.notar`; `is_force = args.force` (4271–4277).
2. If recursive: `_is_recursive_collision(folders)` (4077) — any folder being a
   subdirectory of another → per-pair message
   `Folder {b} is a subdirectory of folder {a}.\n` then
   `'\nError: You cannot archive folders recursively if there is a dependency
   between them.\n'` → return False.
3. If `is_nih`: TUI NIH grant search (`TableNIHGrants`); on selection appends
   `--nih-ref <id>` to `sys.argv` (so a Slurm resubmission carries it) and sets
   `args.nihref`; nothing selected → return `None` (→ exit 1) (4289–4301).
4. **Slurm gate** (4303–4315): if `use_slurm(args.noslurm)` (§6) — removes a
   literal `--hotspots` token from `sys.argv` if present and appends folders,
   then `_slurm_cmd(folders, 'archive')` and returns. The DB write does not
   happen in the submitting process; the Slurm job re-runs the same CLI on the
   node (with `SLURM_JOB_ID` set, so it executes locally there).
5. Local path — per top-level `folder`:
   - `s3_dest = os.path.join(f':s3:{cfg.bucket_name}', cfg.archive_dir,
     folder.lstrip('/'))` → literal
     **`:s3:<bucket>/<archive_dir><absolute-path-without-leading-slash>`**,
     e.g. `:s3:mybucket/froster/home/user/data` (4320–4323).
   - **Recursive** (4325–4338): `archive_mode = "Recursive"`; for every `root`
     yielded by `_walker(folder)` (the folder itself and all subdirectories,
     skipping `.snapshot`, symlinked dirs treated as files) compute `s3_fld`
     the same way from `root` and call
     `_archive_locally(root, s3_fld, is_tar, is_force)`. On `False` → set
     `overall_success=False`, log to stderr `\nError occurred during archive of
     {root}. Skipping remaining subfolders for {folder}.\n`, `break`. `None`
     (skip) is tolerated.
   - **Single** (4340–4348): `archive_mode = "Single"`; one
     `_archive_locally(folder, s3_dest, ...)`; `False` → `overall_success=False`,
     stderr `\nError occurred during archive of {folder}.\n`.
6. **DB mutation** (4351–4376): only if the *last* `success` value is truthy.
   One entry per top-level folder — **subfolders never get their own DB
   entries**; recursive membership is resolved at lookup time (§0.3). Key:
   `folder.rstrip('/')`. Value:
   ```json
   {
     "local_folder":      "<folder>",
     "archive_folder":    "<s3_dest of the top-level folder>",
     "s3_storage_class":  "<cfg.storage_class>",
     "profile":           "<cfg.credentials>",
     "provider":          "<cfg.provider>",
     "endpoint":          "<cfg.endpoint>",
     "archive_mode":      "Single" | "Recursive",
     "timestamp":         "<datetime.now().isoformat()>",
     "timestamp_archive": "<same timestamp>",
     "user":              "<getpass.getuser()>",
     "nih_project":       "<args.nihref>"        // only if set
   }
   ```
   Compat quirk: in recursive mode `success` holds the result for the **last**
   walked subfolder, so if the last subfolder was skipped (`None`) the DB entry
   is not written even though uploads succeeded. Return `overall_success`.

### 1.4 `_archive_locally(folder_to_archive, s3_dest, is_tar, is_force)` (4101–4264)

Returns `True` (success), `False` (failure), or `None` (skipped).

1. `hashfile = <folder>/.froster.md5sum` (4106).
2. `--force`: `reset_folder(folder)` first (§1.8); reset failure → False.
3. Without `--force`, if the hashfile exists (4118–4148): check DB entry and
   run `rclone checksum md5 <hashfile> <s3_dest> --max-depth 1`. Three cases,
   all `return False`:
   - entry + checksum OK: `'\nThe folder {folder} is already archived in S3
     bucket.\n'` + `'{archived_folder_info}\n'` (Python dict repr).
   - entry + checksum mismatch: `'\nThe folder {folder} is already archived in
     our database but checksums do not match in the S3 bucket.\n'` + info +
     `'\nIf you want to force the archiving process again on this folder,
     please us the -f or --force flag\n'` (sic "us").
   - no entry: `'\nThe hashfile ".froster.md5sum" already exists in {folder}
     from a previous archiving process attempt.'` + the same force hint.
4. Empty-folder skip (4150–4168): scandir; if no file/symlink exists whose name
   is not in `dirmetafiles` → `'\nFolder {folder} contains no files or symlinks
   to archive (only subdirectories and/or metadata), skipping.\n'` → return
   **None**. (A folder containing only `Froster.smallfiles.tar` is *not*
   skipped, since the tar isn't in `dirmetafiles`.)
5. `'\nARCHIVING {folder}'`, then `'\n    Generating Froster.allfiles.csv and
   tar small files...'` (or `'\n    Generating Froster.allfiles.csv...'` with
   `--no-tar`); run `_gen_allfiles_and_tar(folder, thresholdKB, is_tar)` (§1.5);
   `'        ...done'` or return False.
6. `'\n    Generating checksums...\n'`;
   `_gen_md5sums(folder, '.froster.md5sum')` (§1.6); `'        ...done'` or
   return False.
7. `'\n    Uploading Froster.allfiles.csv file...'` — if provider == `AWS`, set
   env `RCLONE_S3_STORAGE_CLASS=INTELLIGENT_TIERING` for this copy, then
   restore to `cfg.storage_class` afterwards (4197–4213). Command:
   `rclone copy <folder>/Froster.allfiles.csv <s3_dest> --max-depth 1 --links
   --exclude .froster.md5sum --exclude .froster-restored.md5sum --exclude
   Froster.allfiles.csv --exclude Where-did-the-files-go.txt` (source is the
   single file; excludes are inert). `'        ...done'` or
   `'        ...FAILED\n'` → False.
8. `'\n    Uploading files...'` — `rclone copy <folder> <s3_dest> --max-depth 1
   --links --exclude .froster.md5sum --exclude .froster-restored.md5sum
   --exclude Froster.allfiles.csv --exclude Where-did-the-files-go.txt
   --transfers {args.cores} --checkers {args.cores//2}
   --multi-thread-streams 4` (4223–4231). Non-recursive by construction;
   `Froster.smallfiles.tar` **is** uploaded; md5sum files and allfiles.csv are
   excluded (allfiles.csv already went up at INTELLIGENT_TIERING). `--links`
   means symlinks upload as `.rclonelink` objects. done/FAILED as above.
9. `'\n    Verifying checksums...'` — `rclone checksum md5 <hashfile> <s3_dest>
   --max-depth 1 --checkers {max(1, cores//2)}` (4240–4249). done/FAILED→False.
10. Success banner (4253–4258):
    ```
    \nARCHIVING SUCCESSFULLY COMPLETED\n
        PROVIDER:           "{cfg.provider}"
        PROFILE:            "{cfg.profile}"
        ENDPOINT:           "{cfg.endpoint}"
        LOCAL SOURCE:       "{folder_to_archive}"
        S3 DESTINATION:     "{s3_dest}"\n
    ```
    return True.

`.froster.md5sum` and `Froster.allfiles.csv` remain on disk after archiving
(needed by `delete`).

### 1.5 `_gen_allfiles_and_tar(directory, smallsize=1024, is_tar=True)` (4820–4914)

- If `<dir>/Froster.smallfiles.tar` already exists → return True immediately
  (idempotent resume).
- Only the top directory is processed (`break` when `root != directory`).
- Creates `Froster.smallfiles.tar` (mode `"w"`, uncompressed) and
  `Froster.allfiles.csv` simultaneously. CSV header (exact):
  `File,Size(bytes),Date-Modified,Date-Accessed,Owner,Group,Permissions,Tarred`
- For each entry in `files` (regular files and symlinks, incl. symlinked dirs
  from `_walker`), skipping the csv file itself: stats via `os.lstat`
  (`_get_file_stats`, 4972); dates formatted `%Y-%m-%d %H:%M:%S`; owner/group
  via pwd/grp name lookup (uid/gid on failure); permissions as `oct(st_mode)`
  (e.g. `0o100644`); `Tarred` = `No`/`Yes`.
- If `is_tar` and `lstat.st_size < smallsize*1024` (default < 1 MiB):
  `tar_file.add(file_path, arcname=file)` (flat archive, name only), then
  **`os.remove(file_path)`** — originals are deleted as they are tarred. Tar
  failures log `Warning: Failed to tar or remove {path}: {e}` and skip the CSV
  row.
- If **no** file was tarred the empty tar is removed (4906–4908).

### 1.6 `_gen_md5sums(directory, hash_file)` (5378–5432)

- Top directory only. Writes `<dir>/<hash_file>` with lines
  `f"{md5}  {file}\n"` (two spaces, filename only — md5sum-compatible), order =
  parallel completion order (non-deterministic).
- Hashes every `os.path.isfile()` entry **except**: the hash file itself,
  `Where-did-the-files-go.txt`, `.froster.md5sum`, `.froster-restored.md5sum`.
  So it **includes `Froster.smallfiles.tar` and `Froster.allfiles.csv`**.
  Broken symlinks are skipped (isfile False); good symlinks are hashed through
  the link.
- ThreadPool with `max(4, args.cores)` workers; files > 100 MiB hashed in
  parallel 100 MiB chunks (`parallel_md5sum`, 5340). Empty result file
  (0 bytes) → deleted and return False.

### 1.7 Verification semantics

`rclone checksum md5 <local .froster.md5sum> <s3_dest> --max-depth 1` compares
each md5+name in the local hash file against the remote objects' md5. Since the
hash file includes the tar and allfiles.csv, both are verified remotely too.
Any missing/mismatched file → rclone rc != 0 → FAILED.

### 1.8 `reset_folder(directory, recursive=False)` (4916–4951)

`froster archive --reset` / `--force` prelude. Per folder (only the top folder
unless `recursive`; note the `return True` at 4947 is inside the walk loop, so
at most one directory is ever processed even with `recursive=True` — a latent
bug to reproduce or knowingly fix):

```
\nResetting folder "{root}"...
    Untarring Froster.smallfiles.tar... done.        (if tar present; extract into root, then delete tar)
    Removing Froster.allfiles.csv... done|nothing to remove
    Removing .froster.md5sum... done|nothing to remove
    Removing .froster-restored.md5sum... done|nothing to remove
    Removing Where-did-the-files-go.txt... done|nothing to remove
...folder {root} reset successfully\n
```

No DB mutation.

---

## 2. `froster delete`

### 2.1 Entry: `subcmd_delete` (7512–7552)

1. Hidden `--bucket <name>`: only in debug mode (`aws.delete_bucket`), else
   `'Error: Option not available'` → False.
2. No folders → `archive_json_get_csv(['local_folder', 's3_storage_class',
   'profile'])` (5600; rows sorted by `timestamp` desc); none →
   `"No archives available."` → True; TUI `TableArchive` row select; selected
   folder appended to `sys.argv` (for Slurm re-execution).
3. `arch.delete(folders)`.

### 2.2 `Archiver.delete(folders)` (5096–5123)

1. If `--recursive`: `_is_recursive_collision` → `'\nError: You cannot delete
   folders recursively if there is a dependency between them.\n'` → False.
2. If `use_slurm(args.noslurm)` → `_slurm_cmd(folders, 'delete')` → True.
3. Else per folder: recursive → `_delete_locally(root)` for every `root` from
   `_walker(folder)`; single → `_delete_locally(folder)`. Always returns True
   (individual failures only log; exit code stays 0).

### 2.3 `_delete_locally(folder_to_delete)` (4981–5094)

1. `'\nDELETING {folder}'`.
2. If `<folder>/Where-did-the-files-go.txt` exists → `'    ...already
   deleted\n'`, return.
3. DB lookup; `None` → `'\nFolder {folder} is not archived'` + `'No entry found
   in froster-archives.json\n'`, return.
4. Hashfile resolution (5004–5016): prefer `.froster.md5sum`; else
   `.froster-restored.md5sum`; neither → `'There is no hashfile therefore
   cannot delete files in {folder}'`, return.
5. `s3_dest = entry['archive_folder'] + folder_to_delete.replace(
   entry['local_folder'], '')` (handles subfolders of recursive archives).
6. **Verification before deletion** (5025–5032): `'\n    Verifying
   checksums...'`; `rclone checksum md5 <hashfile> <s3_dest> --max-depth 1`.
   Every file in the hash file must exist remotely with matching md5. Failure →
   silent return (no deletion, exit code unaffected).
7. **Deletion** (5037–5049): top level only; `'\n    Deleting files...'`;
   delete every file in `files` **except** `.froster.md5sum`,
   `.froster-restored.md5sum`, `Froster.allfiles.csv`,
   `Where-did-the-files-go.txt`. So: **`Froster.smallfiles.tar` IS deleted**
   (it's in the archive), while allfiles.csv and md5sum files are **kept**.
   `'        ...done'`.
8. Write `Where-did-the-files-go.txt` (5051–5082) — exact body:
   ```
   The files in this folder have been moved to an AWS S3 archive!
   Archive location: {s3_dest}

   Local folder : {entry['local_folder']}
   Provider: {entry['provider']}
   Endpoint: {entry['endpoint']}
   S3 storage class: {entry['s3_storage_class']}
   Archive mode: {entry['archive_mode']}
   Archive aws profile: {entry['profile']}
   Archiver user: {entry['user']}
   Archiver email: {cfg.email}
   froster-archives.json: {self.archive_json}
   Archive tool: https://github.com/dirkpetersen/froster
   Restore command: froster restore "{folder_to_delete}"
   Deletion date: {datetime.datetime.now()}


   First 10 files deleted this time:
   {', '.join(deleted_files[:10])}

   Please see more metadata in Froster.allfiles.csv file

   You can use "visidata" or "vd" tool to help you visualize Froster.allfiles.csv file
   ```
   (`Deletion date` uses default `str(datetime)`, e.g.
   `2026-07-10 14:03:22.123456`.)
9. Final message:
   ```
   \nDELETING SUCCESSFULLY COMPLETED\n
       LOCAL DELETED FOLDER:   {folder}
       AWS S3 DESTINATION:     {s3_dest}\n
       Total files deleted:    {N}\n
       Manifest:               {readme}\n
   ```
10. **No DB mutation on delete.** (No `timestamp_deleted` exists in this
    codebase.)

---

## 3. `froster restore`

### 3.1 Entry: `subcmd_restore` (7385–7423)

1. No folders → `archive_json_get_csv(['local_folder','s3_storage_class',
   'profile','archive_mode'])`; none → `"No archives available."` → True; TUI
   select; `< 2` columns → `'\nNo archived folders found\n'` → False; append
   folder to `sys.argv`.
2. `--change-tier` → `_change_storage_tier` (7425; TUI tier selection,
   `aws.change_storage_class`, then updates DB entry `s3_storage_class` via
   `_archive_json_add_entry` — the only place restore-side DB is touched).
3. `arch.restore(folders, aws)`.

Flags (8073–8128): `-d/--days` (default `30`; **string when user-supplied** —
no `type=int`, passed straight into boto `RestoreRequest['Days']`),
`-o/--retrieve-opt` (default `'Bulk'`), `-l/--no-download`, `-r/--recursive`,
`-t/--change-tier`; `--aws/--monitor/--instance-type` are parsed but dead in
this code path.

### 3.2 `Archiver.restore(folders, aws)` (5214–5284)

1. Recursive collision check → `'\nError: You cannot restore folders
   recursively if there is a dependency between them.\n'` → False.
2. For each folder: `os.makedirs(folder)` if missing (5231–5232); then walk
   `_walker(folder)` (only the folder itself when not recursive) and per `root`:
   - No DB entry → `'\nFolder {root} is not archived'` + `'No entry found in
     froster-archives.json\n'` → continue.
   - `_contains_non_froster_files(root)` (5196) returns True only when the top
     level contains **no** file outside `dirmetafiles` (the name means the
     opposite of what it does). If the folder still has real files:
     ```
     \nWARNING: Folder {root} 
         contains files in addition to Froster meta data.\n
     Has this folder been deleted using "froster delete" command?.
     Please empty the folder before restoring.\n
     ```
     continue. (Consequence: a folder that was archived but never deleted
     cannot be re-downloaded without emptying it; a present
     `Froster.smallfiles.tar` also triggers this since it's not in
     `dirmetafiles`.)
   - `_restore_locally(root, aws)` (§3.3):
     - True (no glacier or already thawed): if `--no-download` → `'\nFolder
       restored but not downloaded (--no-download flag set)\n'` and **`return`
       (None)** — main treats falsy as failure → **exit code 1 even on
       success** (compat quirk); else `_download(root)` (§3.4).
     - False (glacier retrieval pending): if Slurm installed and not
       `--no-slurm`, schedule three follow-up jobs:
       `_slurm_cmd(folders, 'restore', scheduled="now+12hours")`,
       `"now+24hours"`, `"now+48hours"` (5271–5278). No scheduling without
       Slurm — user must rerun manually.
3. Return True (exit 0) — including the "come back later" case.

### 3.3 `_restore_locally` (5157–5194) + `AWSBoto.glacier_restore` (2111–2202)

1. `'\nRESTORING "{folder}"\n'`.
2. `archive_get_bucket_info(folder)`; `is_glacier` iff DB `s3_storage_class` ∈
   {`DEEP_ARCHIVE`,`GLACIER`}. Not glacier → `'...no glacier restore needed\n'`
   → True.
3. Glacier: `aws.glacier_restore(bucket, prefix, args.days, args.retrieveopt)`:
   - `list_objects_v2` paginated on `Bucket=bucket, Prefix=prefix`; **objects
     in subfolders skipped** (`'/' in key[len(prefix):]`, 2147–2149).
     AccessDenied → stderr `"Access denied for bucket '{bucket}'"` + `'Check
     your permissions and/or credentials.'`, returns 5 empty lists.
   - Per object `head_object`: header `Restore` containing
     `ongoing-request="true"` → `restoring_keys`; `ongoing-request="false"` →
     `restored_keys`; storage class not GLACIER/DEEP_ARCHIVE →
     `not_glacier_keys` (except keys ending `Froster.allfiles.csv`, silently
     ignored); DEEP_ARCHIVE + `Expedited` → `not_supported_keys` with message
     `'{key}: No Expedited retrieval in DEEP_ARCHIVE storage class.'`; else
     `restore_object(RestoreRequest={'Days': keep_days,
     'GlacierJobParameters': {'Tier': ret_opt}})` → `triggered_keys`. Any
     restore_object exception → `'Restore request for {key} failed.'` and
     returns 5 empty lists.
   - If any object exposed `x-amz-restore-tier`:
     `print(f'Current restore tier: {tier}\n')`.
4. Summary (5171–5176):
   ```
       Triggered Glacier retrievals: {len(trig)}
       Currently retrieving from Glacier: {len(rest)}
       Retrieved from Glacier: {len(done)}
       Not in Glacier: {len(notg)}
       Restore option not supported: {len(nosup)}\n
   ```
5. If `trig` or `rest` non-empty — "come back later" (return False):
   ```
   \n    Glacier retrievals pending. Depending on the storage class and restore mode run this command again in:\n
           Expedited mode: ~ 5 minutes (DEEP_ARCHIVE not supported)
           Standard mode: ~ 12 hours
           Bulk mode: ~ 48 hours\n
           NOTE: You can check more accurate times in the AWS S3 console\n
   ```
   Else return True.

### 3.4 `_download(folder)` (5125–5155) + `_restore_verify` (5286–5337)

1. `source = ':s3:' + bucket + '/' + prefix` (prefix ends with `/`);
   `'Downloading files...'`; `rclone copy <source> <folder> --max-depth 1`
   (no `--links`, no transfer tuning); `'    ...done\n'` / `'    ...FAILED\n'`
   (proceeds to verify even on FAILED).
2. `_restore_verify`: top level only:
   - `'\n    Generating checksums...\n'` →
     `_gen_md5sums(target, '.froster-restored.md5sum')`; `'    ...done'` or
     return.
   - `'\nVerifying checksums...'` → `rclone checksum md5
     <target>/.froster-restored.md5sum <source> --max-depth 1 --checkers
     {max(1,cores//2)}`; `'    ...done'` or `'    ...FAILED\n'` + return.
   - If `<target>/Froster.smallfiles.tar` exists: `'\nUntarring
     Froster.smallfiles.tar... '` → `tar.extractall(target)` → **tar deleted**
     → `'    ...done\n'`. (Untar only after checksum verification succeeds.)
   - Delete `Where-did-the-files-go.txt` if present (no message).
   - `'RESTORATION OF {root} COMPLETED SUCCESSFULLY\n'`.
3. **DB updates: none.** There is **no `timestamp_restored` key anywhere in
   this file**; a Go reimplementation must not invent one for compatibility.
   Leftover artifacts after restore: `.froster.md5sum` (if still present),
   `.froster-restored.md5sum`, `Froster.allfiles.csv`.

---

## 4. `froster mount` / `froster umount`

### 4.1 `subcmd_mount` (7554–7601)

1. `--list` → `print_current_mounts()` (4402): `'\nCURRENT MOUNTED
   FOLDERS:\n'` + `    {mount}` per line, or `'\nNO FOLDERS MOUNTED\n'`.
2. `--mount-point` given: must exist (`'\nError: Folder "{mp}" does not
   exist.\n'` → False) and only one folder allowed (`'\nError: Cannot mount
   multiple folders to a single mountpoint.'` / `'Check the mount command usage
   with "froster mount --help"\n'` → False).
3. No folders → TableArchive selection; none → `"\nNo archives available.\n"`
   → True.
4. `arch.mount(folders, mountpoint)` (4469): `mountpoint =
   clean_path(mountpoint)`; `_mount_locally` (4417) per folder:
   - No DB entry → `'\nWARNING: folder "{folder}" not in archive.\n'` +
     `'Nothing will be restored.\n'` → continue.
   - Folder doesn't exist locally and no mountpoint → `'\nWARNING: folder
     "{folder}" does not exist and no mountpoint provided.\n'` + `'Nothing will
     be restored.\n'` → continue.
   - Remote = `entry['archive_folder']` (**always the parent entry's S3 path**
     — for a subfolder of a recursive archive it announces `'\nMOUNTING parent
     folder "{local_folder}"[ at "{mountpoint}"]...'` and mounts the parent;
     exact-match folder prints `'\nMOUNTING "{local_folder}"[ at
     "{mountpoint}"]...'`).
   - Default mountpoint = `entry['local_folder']` (the original location).
   - Already mounted (per `/proc/mounts` fuse.rclone list) →
     `'    ..."{mountpoint}" already mounted\n'` + **`sys.exit(1)`** (hard
     exit, remaining folders not processed).
   - `rclone mount` (background, read-only; §0.5) → `'    ...MOUNTED\n'` or
     `'    ...FAILED\n'` (+ stop processing remaining folders).
5. Returns True (exit 0) regardless of per-folder warnings.

### 4.2 `subcmd_umount` (7603–7631)

Alias note: `umount` is an **alias of the `mount` subparser** (8046), so it
accepts the same flags (`--list`, folders...).

1. `--list` → `print_current_mounts()`.
2. `mounts = arch.get_mounts()`; empty → `"\nNOTE: No rclone mounts on this
   computer.\n"` → True.
3. No folders → build pseudo-CSV `"Mountpoint\n" + "\n".join(mounts)` →
   TableArchive select.
4. `arch.unmount(folders)` (4496) → `_unmount_locally` (4477): per folder
   `'\nUNMOUNTING {folder}...'`; if mounted → `fusermount3 -u` →
   `'    ...UNMOUNTED SUCCESS\n'` / `'    ...UNMOUNTING FAILED\n'`; else
   `'    ...IS NOT MOUNTED\n'`. Always returns True.

**Compat bug:** `main` calls `cmd.subcmd_umount(arch, aws)` (8454) but the
method signature is `subcmd_umount(self, arch)` (7603) — a `TypeError` is
raised, caught by main's handler → `print_error()` → **exit 1**. As shipped,
`froster umount` never reaches the logic above. go-froster implements the
*intended* behavior (documented deviation).

---

## 5. `froster test` — `subcmd_test` (7633–7728)

Runs with no credentials pre-gate in main, but performs its own check.

1. Generate bucket name `froster-cli-test-<4 random lowercase+digits>`.
2. `tempfile.mkdtemp(prefix='froster_test_')` + `<tmp>/dummy_file`.
3. `'\nTESTING FROSTER...'`; `aws.check_credentials(prints=True)`; failure →
   `'\nTESTING FAILED\n'` → False.
4. `cfg.bucket_name = new_bucket_name` (session-only override).
5. `'\nCreating dummy file {file_path}...'` — 1-byte file via `truncate(1)` —
   `'    ....dummy file create'` (sic).
6. `aws.create_bucket(new_bucket_name, cfg.region)`; failure → tearDown +
   FAILED.
7. **Index**: mock `args.folders=[tmp]`, `permissions=False`,
   `pwalkcopy=None`; run `subcmd_index`. Failure → tearDown + FAILED.
8. **Archive**: mock `older=0, newer=0, reset=False, recursive=False,
   nih=False, nihref=None, notar=True` ("True to check by file name in the
   archive"), `force=False`, `noslurm=True`; run `subcmd_archive`. Failure →
   tearDown + FAILED.
9. **Delete**: mock `bucket=None, debug=False, recursive=False, noslurm=True`;
   run `subcmd_delete`. Failure → tearDown + FAILED.
10. tearDown: `shutil.rmtree(tmp)`; `os.environ['DEBUG']='1'`;
    `aws.delete_bucket(bucket)` (empties then deletes).
11. `'\nTEST SUCCESSFULLY COMPLETED\n'` → True.

Not tested by it: restore, mount, glacier, tarring (`notar=True`), recursion,
Slurm.

---

## 6. Cross-cutting

### 6.1 Slurm gating

`use_slurm(noslurm_flag)` (8224): `is_slurm_installed()` (`shutil.which(
'sbatch')`, 8210) **and** not `--no-slurm` **and** not already inside a job
(`SLURM_JOB_ID` unset, 8217). Auto-submitting subcommands:

| Command | Gate location | cmd_type | Notes |
|---|---|---|---|
| `index` | `Archiver.index` 3940 | `index` | whole run submitted |
| `archive` | `Archiver.archive` 4303 | `archive` | after NIH selection; folders appended to argv |
| `delete` | `Archiver.delete` 5109 | `delete` | whole run submitted |
| `restore` | `Archiver.restore` 5271 | `restore` | only when glacier pending; gate is `is_slurm_installed() and not args.noslurm` (runs even inside a Slurm job); three jobs at `--begin now+12hours/now+24hours/now+48hours` |

`_slurm_cmd(folders, cmd_type, scheduled=None)` (3904–3930): label =
`_get_hotspots_filename(folders[0])` minus `.csv`, spaces→`_`. Note
`_get_hotspots_filename` (5736–5756) effectively returns
`folder.replace('/', '+') + '.csv'` (the mount-aware `@`-prefix branch computes
but then unconditionally overwrites — reproduce final behavior), so label =
`+home+user+data`. shortlabel = `os.path.basename(folders[0])`. Command =
current CLI reconstructed: `" ".join(map(shlex.quote, sys.argv))` (this is why
interactive selections are appended to `sys.argv` beforehand).

`Slurm.submit_job` (6743–6784) script (see go/internal/slurm for the Go port):

```
#!/bin/bash
#SBATCH --job-name=froster:{cmd_type}:{shortlabel}
#SBATCH --cpus-per-task={args.cores}
#SBATCH --mem={args.memory}          # GB*1024 (MB) if a partition is configured
[#SBATCH --begin={scheduled}]
#SBATCH --requeue
#SBATCH --output={slurm_dir}/froster-{cmd_type}@{label}-%J.out
#SBATCH --mail-type=FAIL,REQUEUE,END
#SBATCH --mail-user={cfg.email}
#SBATCH --time={walltime_days}-{walltime_hours}   # default 7-0
#SBATCH --partition={partition}
#SBATCH --qos={qos}
[lscratch mkdir line / TMPDIR export]
{original froster command line}
{cfg.lscratch_rmdir}
```

(`#SBATCH` lines re-sorted to the top, 6716). `slurm_dir = <data_dir>/slurm`
(169). Submission via `sbatch` on stdin; user message:

```
\nSLURM JOB\n
  ID: {jobid}
  Type: {cmd_type}
  Check status: "squeue -j {jobid}"
  Check output: "tail -n 100 -f {output_dir}-{jobid}.out"
  Cancel the job: "scancel {jobid}"\n
```

Cores/memory clamped to partition totals when `slurm_partition` is configured
(6609–6622). `sbatch` error containing `Invalid generic resource` → `'Invalid
generic resource request. Please change configuration of slurm_lscratch'`,
then `sys.exit(1)`.

### 6.2 Shared-config permission handling

`main` (8441–8442): whenever `cfg.is_shared` and `shared_dir` set, run
`cfg.assure_permissions_and_group(shared_dir)` (403–458) on **every
invocation**:

- Non-directory → raise (caught, `print_error`).
- chmod the dir and every subdirectory to `0o2775` (setgid) when bits differ.
- Files: **skipped entirely when `is_shared`** (the `continue` at 431–432
  fires, so in the shared case only directories are chmodded). For non-shared
  use: `.pem` files → `0o400`, everything else → `0o664`, and
  `chown(path, -1, dir_gid)` to inherit the directory's group.
- Failure → `print_error(...)`, returns False (non-fatal).

`_archive_json_add_entry` creates the DB's parent dir with mode `0o775` (5503);
hotspot dirs are created `0o775` (4528, 5728).

### 6.3 Miscellaneous compat notes

- `_is_correct_files_folders_permissions` (4676) and `_is_small_file_in_dir`
  (4953) are dead code — no callers.
- `--days` reaches boto as a string when user-supplied (no `type=int`).
- `TableArchive` returns the selected row; callers use `retline[0]` =
  `local_folder`.
- `archive_json_get_csv` sorts entries by `timestamp` descending and emits an
  excel-dialect CSV of requested columns (5600–5636).
- `printdbg` output and `log()` file logging require env `DEBUG=1` (8168, 8353).
- The mount/umount TUI/table and hotspot TUIs exit with `[]` on `q`.
- On success, all four core subcommands return True → exit 0;
  `restore --no-download` returns `None` → exit 1 (quirk, §3.2); `delete`
  returns True even when nothing was verified/deleted.
