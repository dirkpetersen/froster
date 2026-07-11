# Golden fixtures: Python froster v0.22.0 end-to-end against Minio

These fixtures were produced by running the **real Python froster** (v0.22.0
code from this repo, editable install in `.venv`) through a full
index → archive → delete → restore cycle against a local Minio container.
Go tests assert against these files to prove drop-in compatibility
(GO-ARCHITECTURE.md §3.2 / §10).

Reproduce with:

```bash
# needs docker + the dev venv (install.sh); from the repo root:
FROSTER_VENV=/path/to/froster/.venv go/testdata/golden/generate.sh
```

Everything runs in a sandbox `HOME=/tmp/froster-golden/home`; the user's real
`~/.config/froster`, `~/.local/share/froster` and `~/.aws` are never touched.

## Environment

| item | value |
|---|---|
| froster code | v0.22.0 (`froster/froster.py` @ branch `go-froster-dev`) |
| reported version | `froster v0.21.2` (**quirk Q1**) |
| python | 3.12.3 |
| pwalk | 3.0.0 (venv build) |
| rclone | 1.71.2 (wrapped, **quirk Q7**) |
| S3 | Minio (docker `minio/minio`, port 9201, plain HTTP), bucket `froster-golden`, profile provider `Minio`, storage class `STANDARD` |
| host | Linux x86_64 (WSL2, ext4), user/group `dp/dp` (uid/gid 1000) |

## The dummy tree

Created by `generate_tree.py` (fixed seed 42, fixed mtime 2026-01-01 10:44:05
UTC; file *contents* are byte-for-byte reproducible). `golden-tree` is the
archived tree; `hotspot-tree` uses **sparse** files (>1 GiB apparent, ~0 disk)
so `froster index` produces hotspot rows (**quirk Q2**).

```
/tmp/froster-golden/data/golden-tree/
  empty-dir/                     (empty)
  big_alpha.dat        2 MiB     (not tarred)
  big_beta.dat         3.5 MiB   (not tarred)
  exactly_1mib.dat     1048576 B (boundary: NOT tarred, threshold is size < 1 MiB strictly)
  just_under_1mib.dat  1048575 B (boundary: tarred)
  small_report.txt     10 KiB    (tarred)
  file with spaces.txt 5 KiB     (tarred)
  values,comma.csv     4 KiB     (tarred)
  quote"file.txt       3 KiB     (tarred)
  caf\xe9.dat          2 KiB     (Latin-1 non-UTF-8 name; removed before the clean archive, see Q5)
  sub_data/
    big_gamma.dat      1.5 MiB
    small_notes.md     8 KiB     (tarred)
    deeper/
      mid_size.dat     2 MiB
      tiny.bin         100 B     (tarred)
/tmp/froster-golden/data/hotspot-tree/
  sparse_a.dat         800 MiB sparse
  sparse_b.dat         500 MiB sparse
  subhot/sparse_c.dat  1200 MiB sparse
```

## Fixture files

### Top level
- `version.txt`, `info.txt` — `froster --version` / `froster --info` output.
- `generate.sh`, `generate_tree.py` — the (re)generators; read their comments.

### config/
- `config.ini` — the froster config as used (written by the script, then
  froster itself appended/kept `[UPDATE] timestamp`). Go must round-trip this
  format. Values are synthetic; `minioadmin` is Minio's public default cred.
- `aws-config` — `~/.aws/config` with the **nested** `s3 = / endpoint_url =`
  block froster reads via `get_aws_config_option('s3.endpoint_url')`.
- `aws-credentials` — `~/.aws/credentials` profile `minio`.
- `rclone-wrapper.sh` — the wrapper injected for Q7.

### index/
- `pwalk-raw-golden-tree.csv`, `pwalk-raw-hotspot-tree.csv` — raw
  `pwalk --NoSnap --one-file-system --header` output (fixture for the Go
  walker). ISO-8859-1: the `caf\xe9.dat` byte is preserved raw. Note pwalk's
  CSV quoting doubles `"` inside filenames (`quote""file.txt`), directory rows
  have `pw_fcount >= 0`, file rows have `pw_fcount == -1, pw_dirsum == 0`.
  **`pw_dirsum` is NOT recursive**: a directory's dirsum = its direct
  children's `st_size` sum (subdirectories contribute their 4096-byte dir
  inode, not their contents). Row order = scan order, machine-dependent.
- `pwalkcopy-hotspot-tree.csv` — what `froster index --pwalk-copy DIR` saves
  (pwalk output iconv'd ISO-8859-1→UTF-8, directories still included).
- `hotspots-hotspot-tree.csv` — the hotspots CSV
  (`~/.local/share/froster/hotspots/+tmp+froster-golden+data+hotspot-tree.csv`;
  `/`→`+` path encoding). Columns
  `User,AccD,ModD,GiB,MiBAvg,Folder,Group,TiB,FileCount,DirSize`; GiB/TiB/
  MiBAvg are int-truncated; AccD/ModD are "days ago" (AccD non-deterministic,
  see Normalization).
- There is **no hotspots CSV for golden-tree**: indexing it crashes (Q4);
  `logs/index-golden-tree.log` captures the failure.

### archive/
Produced by `froster --no-slurm archive --recursive golden-tree` (with
`empty-dir` temporarily removed, see Q6). Per-folder artifacts are prefixed
`root.` / `sub_data.` / `sub_data__deeper.`:
- `*.froster.md5sum` — `.froster.md5sum` as uploaded-verified. Format:
  `<md5>  <basename>` (two spaces). Includes `Froster.allfiles.csv` and
  `Froster.smallfiles.tar`; excludes `.froster.md5sum` itself,
  `.froster-restored.md5sum` and `Where-did-the-files-go.txt`. **Line order is
  thread-completion order — unordered; compare as a set.**
- `*.Froster.allfiles.csv` — metadata CSV (all top-level files incl. tarred
  ones; columns `File,Size(bytes),Date-Modified,Date-Accessed,Owner,Group,
  Permissions,Tarred`). Permissions rendered as Python `oct()` (`0o100644`).
  Row order = `os.walk` files order (machine-dependent); `Date-Accessed` is
  non-deterministic.
- `*.Froster.smallfiles.tar` — the actual tars (committed; ~1 MiB total).
  Python `tarfile` PAX (POSIX.1-2001) format, members are top-level files
  `< 1 MiB` only, arcname = basename, original files removed after tarring.
- `*.smallfiles-tar-members.txt` — `tar -tvf` listings.
- `froster-archives.json` — the archive DB written after archiving. Note
  `"profile"` holds the **credentials** profile name (`minio`), not the
  froster profile name (`profile minio`) (**quirk Q9**), and the single entry
  for a recursive archive is keyed by the top folder with
  `archive_mode: "Recursive"`.
- `s3-objects.txt` / `s3-objects.json` / `s3-objects-stat.json` — resulting
  object listing (`mc ls`/`mc stat`): key layout
  `<bucket>/<archive_dir>/<abs-local-path>/...`, storage class STANDARD,
  and per-object metadata. rclone (multipart, Q7) sets
  `X-Amz-Meta-Md5chksum` (base64 md5) and `X-Amz-Meta-Mtime`. Note
  `.froster.md5sum` itself is **not** uploaded; `Froster.allfiles.csv` is
  uploaded (to AWS it would go to INTELLIGENT_TIERING; on non-AWS providers
  it keeps the profile storage class).

### archive-fail-latin1/
Captured **destructive failure** archiving the tree while `caf\xe9.dat`
(raw Latin-1 byte in the name) existed — see Q5:
- `archive-attempt.log` — UnicodeEncodeError (surrogate `\udce9`) while
  writing the allfiles CSV row.
- `Froster.allfiles.csv.partial` — truncated CSV left behind.
- `smallfiles-tar-members.txt` — the tar at crash time: `caf\351.dat` was
  already moved into the tar and deleted from disk (PAX `hdrcharset=BINARY`
  encoding; GNU tar prints "Ignoring unknown extended header keyword
  'hdrcharset'").
- `archive-reset.log` — recovery via `froster archive --reset` (untars small
  files back, removes metadata files).

### archive-bug-emptydir-last/
Static evidence (not regenerated by the script) of the recursive-archive DB
bug (Q6): a fully successful 3-folder recursive archive that wrote **no**
`froster-archives.json` entry because `empty-dir` happened to be walked last.

### delete/
Produced by `froster --no-slurm delete --recursive golden-tree`:
- `*.Where-did-the-files-go.txt` — manifest left in each folder. Note the
  "First 10 files deleted" list includes `Froster.smallfiles.tar` and is in
  walk order; trailing "Deletion date" is a naive local datetime.
- `post-delete-tree.txt` — the local tree after delete: only
  `.froster.md5sum`, `Froster.allfiles.csv`, `Where-did-the-files-go.txt`
  remain per folder (dirs are kept; `empty-dir` untouched — "There is no
  hashfile therefore cannot delete files", see `logs/delete-recursive.log`).

### restore/
Produced by `froster --no-slurm restore --recursive golden-tree` (Minio,
class STANDARD → `is_glacier=False` → "...no glacier restore needed", direct
download; no Glacier code path exercised — that requires DEEP_ARCHIVE/GLACIER
in the DB entry):
- `*.froster-restored.md5sum` — `.froster-restored.md5sum` files generated
  during verify (same format/exclusions as `.froster.md5sum`; identical md5
  set to the archive-side file per folder — asserted during generation).
- `post-restore-tree.txt` — tree after restore: all data files back, tar
  untarred+removed, `Where-did-the-files-go.txt` removed, both md5sum files
  left behind. `empty-dir` restore silently no-ops mid-way (Q10).
- `original-files.md5` — md5 of every original file (minus `caf\xe9.dat`)
  before archiving.
- `roundtrip-check.txt` — `md5sum -c` proof that restore reproduced every
  original file bit-for-bit.

### logs/
Full stdout+stderr of every froster invocation (`credentials`, both `index`
runs, `archive --recursive`, `delete --recursive`, `restore --recursive`).
Useful for matching user-visible output phrasing.

## Normalization required by Go golden tests

Non-deterministic between regenerations (compare structurally, not
byte-for-byte):
- all timestamps: `timestamp*` in froster-archives.json, `Deletion date`,
  CSV `Date-Accessed` (atime cannot be pinned: WSL2/relatime + tar reads
  update it; `Date-Modified` IS stable = 2026-01-01 02:04:05 local),
  pwalk `st_atime`/`st_ctime`, `AccD` in hotspots CSV, S3 `lastModified`,
  `X-Amz-Meta-Mtime` of `Froster.allfiles.csv` (mtime of a generated file).
- inode/device numbers and row order in pwalk CSVs.
- line order in `.froster.md5sum` (thread completion) and row order in
  `Froster.allfiles.csv` (os.walk order).
- md5 of `Froster.allfiles.csv` itself (it embeds atimes) — hence also the
  tar-adjacent md5sum entries for it; md5s of all *data* files and of the
  tars are stable (fixed content + fixed mtimes → deterministic PAX tar).
- `Owner`/`Group`/`User`/uid/gid columns (machine user).
- `[UPDATE] timestamp` in config.ini.
- absolute path prefix `/tmp/froster-golden` (constant for the script, but
  embedded everywhere including S3 keys).

## Python froster quirks & bugs discovered (parity-relevant!)

- **Q1 — version lies**: `froster --version` prints the *installed dist*
  version (`importlib.metadata`), here `v0.21.2`, while the code is 0.22.0.
  Editable installs go stale. Go should print its own build version.
- **Q2 — hotspot thresholds not configurable**: `max_small_file_size_kib`,
  `min_index_folder_size_gib` (1 GiB), `min_index_folder_size_avg_mib`
  (10 MiB), `max_hotspots_display_entries` are hardcoded in
  `ConfigManager.__init__`; despite README/CLAUDE.md, config.ini values are
  never read. A folder must have GiB≥1 **and** MiBAvg≥10 to appear in the
  hotspots CSV.
- **Q3 — update check crashes non-interactive runs**: when a newer release
  exists and stdin is not a TTY, the post-command update check dies with
  `EOFError` at `input()` (`Commands.subcmd_update`). generate.sh pre-seeds
  `[UPDATE] timestamp` in config.ini to suppress the 7-day check.
- **Q4 — `index` breaks on non-UTF-8 filenames**: the pipeline
  `pwalk | grep -v ",-1,0$" | iconv | duckdb` fails because GNU grep treats
  the pwalk CSV (raw Latin-1 byte) as *binary* and emits
  `Binary file ... matches`, which DuckDB then can't parse
  (`Binder Error: Referenced column "pw_fcount" not found`). Exit code 1,
  misleading "permission issues" warning. Captured in
  `logs/index-golden-tree.log`. Go (byte-oriented) must simply work here.
- **Q5 — `archive` corrupts state on non-UTF-8 filenames**:
  `os.walk` surrogate-escapes `caf\xe9.dat` → writing the CSV row raises
  `UnicodeEncodeError`, **after** the file was already tarred and unlinked.
  Result: file exists only inside `Froster.smallfiles.tar`, truncated
  `Froster.allfiles.csv` on disk. A naive re-run would even skip tarring
  (tar exists → early return) and upload the truncated CSV.
  `archive --reset` recovers. Captured in `archive-fail-latin1/`.
- **Q6 — recursive archive DB entry depends on the last-walked folder**:
  `Archiver.archive()` checks `if success:` after the subfolder loop, so only
  the *final* `_archive_locally` result decides whether the
  froster-archives.json entry is written. An empty dir returns None
  ("skipping"), so empty-dir-last (ext4 hash order!) → successful uploads
  but **no DB record**; delete/restore then claim "not archived". Captured in
  `archive-bug-emptydir-last/`.
- **Q7 — rclone ≥1.70 vs plain-HTTP S3**: single-part PutObject fails with
  "unseekable stream is not supported without TLS and trailing checksum"
  (AWS SDK Go v2 trailing checksums). Worked around with
  `RCLONE_S3_UPLOAD_CUTOFF=0` (all uploads multipart; rclone then stores
  `X-Amz-Meta-Md5chksum` so `rclone checksum md5` still verifies). Injection
  required a wrapper script because froster spawns rclone with a **fully
  replaced environment** (only RCLONE_*/AWS_* vars + HOME; not even PATH), so
  external env vars never reach rclone.
- **Q8 — Single (non-recursive) archive only covers top-level files**
  (`rclone copy --max-depth 1`; tarring/md5 also top-level only).
  Subdirectories are silently not archived unless `--recursive`.
- **Q9 — DB `"profile"` field holds the credentials profile name** (`minio`),
  not the froster profile section name (`profile minio`). The same value
  lands in `Where-did-the-files-go.txt` as "Archive aws profile".
- **Q10 — restoring an empty dir under a Recursive entry half-runs**:
  subfolder lookup resolves to the parent entry, download "succeeds",
  then md5 generation produces an empty hash file which is deleted and
  `False` returned — restore of that dir stops silently mid-log
  ("Generating checksums..." with no completion; see
  `logs/restore-recursive.log` tail). Overall exit is still 0.
- **Q11 — empty dirs & archive**: an empty dir is skipped ("contains no files
  or symlinks to archive"), nothing is uploaded for it (S3 has no dirs), but
  since delete never removes directories the empty dir survives locally;
  after a hypothetical fresh-machine restore it would be lost.
- **Q12 — `st_atime` in pwalk output ≈ scan time** on relatime mounts and
  atime cannot be pinned with `os.utime` in this environment (something
  re-reads the files); all atime-derived fixture columns are
  non-deterministic.
- Minor: froster's own `.froster.md5sum` is not uploaded to S3;
  `Froster.allfiles.csv` *is* uploaded twice in the code path (once
  standalone — INTELLIGENT_TIERING on AWS only — then excluded from the bulk
  copy); `pwalk-copy` output is iconv'd, not raw; hotspot filenames encode
  `/` as `+`.
