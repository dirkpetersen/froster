# go-froster: Architecture for a Go Rewrite of Froster

Status: **Proposal / design document** — no Go code exists yet.
Branch: `go-froster-dev`
Author: generated with Claude Code, reviewed by Dirk Petersen
Date: 2026-07-10

---

## 1. Executive Summary

Froster today is a single 8,500-line Python file (`froster/froster.py`) that
orchestrates three external moving parts: **pwalk** (a GPL C binary compiled at
install time), **rclone** (a downloaded Go binary driven via subprocess), and
**boto3** (AWS SDK for Python). Installation on HPC systems requires a Python
interpreter, a venv, pipx or an installer script, a C compiler for pwalk, and a
network fetch of rclone — all of which are recurring sources of support burden.

This document proposes rewriting Froster in Go as **one static binary** that:

1. **Embeds rclone as a Go library** — froster imports rclone's Go packages
   directly instead of shelling out to a separate binary. One binary contains
   all transfer, checksum, and FUSE-mount functionality.
2. **Uses AWS SDK for Go v2** for all control-plane operations (Glacier
   restore, storage-tier changes, bucket management, credentials/STS).
3. **Reimplements pwalk natively in Go** — a goroutine-based parallel
   filesystem walker replaces the C binary entirely. No compile-at-install, no
   GPL binary dependency, and the walker's semantics become testable code we
   own.
4. **Is a clean-slate redesign, not a port.** The current codebase has grown
   organically and contains substantial redundancy (see §4). We port
   *behavior* — file formats, CLI contract, S3 layout — not code structure.

### Decisions already made

These were settled before this document was written and are treated as
constraints, not open questions:

| Decision | Choice |
|---|---|
| Compatibility | **Full drop-in.** Same `config.ini`, same `froster-archives.json`, same artifact files (`.froster.md5sum`, `Froster.allfiles.csv`, `Froster.smallfiles.tar`, `Where-did-the-files-go.txt`), same S3 object layout. A user replaces the Python froster with the Go binary and everything keeps working. |
| AWS extras (EC2 cloud restore, SES email, Cost Explorer monitoring) | **Not implemented in v1.** The CLI flags/arguments remain (`restore --aws`, `--monitor`, `--instance-type`, …) and print a clear "not yet implemented in go-froster" message. §9 documents what re-adding each feature would take. |
| Hotspot analytics | **Pure Go aggregation** (no embedded DuckDB, no CGO), but the index output remains **DuckDB-friendly `.csv.zst`** so power users can run ad-hoc SQL externally. |
| Python froster | **Frozen** — bugfixes only. The modular-Python path (python-pwalk, rclone-adapter) is discontinued as a froster strategy; lessons learned from both feed this design (§6.3, §12). |

---

## 2. Why Go (and why not the modular-Python path)

Two refactoring strategies were prototyped as standalone PyPI packages:

- **python-pwalk** — pwalk's C core wrapped as a Python C-extension with an
  `os.walk()`-compatible API, thread-local buffers, zstd output.
- **rclone-adapter** — an async-first Python wrapper around a bundled rclone
  binary with typed options for all 54 subcommands.

Both work, but they *modularize the packaging problem without eliminating it*:
froster would still be a Python application that needs an interpreter, a venv,
and binary wheels matched to the platform; rclone would still be a subprocess
with its progress scraped from stderr; pwalk would still be C code maintained
through an FFI boundary. The Go rewrite eliminates the categories:

| Pain point today | Modular Python | Go rewrite |
|---|---|---|
| Install on HPC (no root, old OS, shared FS) | pip + wheels per Python version | `curl -o froster && chmod +x` — one static file |
| rclone integration | subprocess + JSON log scraping | in-process function calls, typed stats structs |
| pwalk | C extension, per-CPython-ABI wheels | native goroutines, one codebase |
| Parallelism | GIL workarounds (C threads, free-threading builds) | goroutines, first-class |
| AWS | boto3 | aws-sdk-go-v2 (same coverage for our needs) |
| Version skew (python/pip/glibc/openssl) | still present | compile-time, `CGO_ENABLED=0` |
| Slurm batch scripts | must recreate venv environment inside job | job script is literally `froster <args>` |

The one genuine loss: Python's ecosystem for interactive TUI (Textual) and
quick iteration. Go's equivalents (Bubble Tea) are mature but lower-level; §6.6
addresses this.

**Concurrency note:** pwalk's value is parallel `readdir`/`lstat` across
directory shards. Goroutines handle this naturally — a worker pool over a
directory queue with per-worker output buffers is idiomatic Go, and the
scheduler overhead is negligible at the 32-worker scale pwalk uses. We expect
throughput at parity with C pwalk (the bottleneck is filesystem metadata
latency, not CPU).

---

## 3. Current-State Inventory (what must be reproduced)

### 3.1 External dependency surface

Audit of `froster/froster.py` (v0.22.0):

**rclone subcommands actually used** (class `Rclone`):

| Call | Purpose | Flags of note |
|---|---|---|
| `copy` | upload/download archives | `-vvv`, `--s3-no-check-bucket` (Ceph) |
| `checksum md5` | verify `.froster.md5sum` against remote | |
| `mount` | FUSE read-only mount of archive | `--allow-non-empty --default-permissions --read-only --no-checksum`, backgrounded |
| `unmount` | via `fusermount3 -u` (not rclone) | |
| `version` | diagnostics | |

That is the *entire* rclone surface — five operations. This makes library
embedding straightforward (§6.2).

**boto3 clients used** (class `AWSBoto`):

| Client | Used for | go-froster v1 |
|---|---|---|
| `s3` | list/create buckets, `restore_object` (Glacier), head-object restore status (`ongoing-request` header), `copy_object` (tier change) | **AWS SDK Go v2 `s3`** |
| `sts` | identity check, credential validation | **`sts`** |
| `iam` | user/permission checks during config | **`iam`** |
| `ec2` (+ resource) | `restore --aws` cloud restore | stubbed (§9) |
| `ses` | email notifications | stubbed (§9) |
| `ce` (Cost Explorer) | `--monitor` cost tracking | stubbed (§9) |

**DuckDB**: exactly one in-memory query — a projection + `WHERE pw_fcount > -1
AND pw_dirsum > 0` filter + `ORDER BY pw_dirsum DESC` over pwalk's
*per-directory summary rows* (pwalk itself computes `pw_dirsum`/`pw_fcount`).
This is a streaming filter-and-sort, not real analytics. Pure Go replaces it
trivially (§6.4). A preprocessing step also converts pwalk CSV from ISO-8859-1
to UTF-8 to work around a DuckDB import error — irrelevant in Go, which treats
filenames as raw bytes.

**Other Python deps → Go equivalents:**

| Python | Role | Go |
|---|---|---|
| textual | TUI tables/dialogs | `charmbracelet/bubbletea` + `bubbles/table` + `lipgloss` |
| inquirer | config wizard prompts | `charmbracelet/huh` |
| tqdm | progress bars | `bubbles/progress` (interactive) / periodic log lines (Slurm) |
| psutil | CPU/mem detection, process checks | `shirou/gopsutil` or `/proc` directly |
| requests | NIH RePORTER API, GitHub release check | `net/http` |
| visidata | optional CSV viewer | dropped; hotspot CSV remains viewable with any tool |
| configparser | `config.ini` | `gopkg.in/ini.v1` (round-trip-safe) |
| duckdb | hotspot filter | pure Go (§6.4) |
| zstd (via python-pwalk plan) | index compression | `klauspost/compress/zstd` (pure Go) |

### 3.2 Compatibility contract (drop-in requirements)

These formats are frozen and become golden-test fixtures (§10):

1. **`~/.config/froster/config.ini`** — sections observed in production:
   `[USER]`, `[SHARED]`, `[NIH]`, `[DEFAULT_PROFILE]`, `[profile <name>]`
   (repeated), `[UPDATE]`. Go must read *and write* these without reordering
   or dropping unknown keys (shared-config mode means Python and Go clients
   may read the same file during transition).
2. **`~/.local/share/froster/froster-archives.json`** — dict keyed by absolute
   local folder path; entry schema (from a live DB):

   ```json
   {
     "local_folder": "/home/dp/temp/froster.data.RCv",
     "archive_folder": ":s3:froster-dipeit/froster/home/dp/temp/froster.data.RCv",
     "s3_storage_class": "DEEP_ARCHIVE",
     "profile": "froster2",
     "provider": "AWS",
     "endpoint": "https://s3.us-west-2.amazonaws.com",
     "archive_mode": "Single",
     "timestamp": "2025-10-16T19:51:57.936903",
     "timestamp_archive": "2025-10-16T19:51:57.936903",
     "user": "dp"
   }
   ```

   Note the rclone-style `:s3:` remote prefix in `archive_folder` — Go must
   parse and generate it identically. Additional keys exist for deleted /
   restored states (`timestamp_deleted`, `timestamp_restored`, NIH grant
   metadata); the Go struct must preserve unknown keys on rewrite
   (`map[string]json.RawMessage` or equivalent).
3. **Per-folder artifacts** — `.froster.md5sum` (md5sum text format),
   `Froster.allfiles.csv`, `Froster.smallfiles.tar` (plain tar, files < 1 MiB,
   preserving paths), `Where-did-the-files-go.txt` (human-readable manifest).
4. **S3 object layout** — `<bucket>/<archive-prefix>/<absolute-local-path>/…`
   exactly as rclone lays it out today, plus the same storage-class values.
5. **CLI contract** — all subcommands (`credentials`, `config`, `index`,
   `archive`, `delete`, `mount`, `umount`, `restore`, `update`, `test`), their
   3-letter aliases (`crd`, `cnf`, `idx`, `arc`, `del`, `rst`, `upd`, `tst`),
   and all flags including global `--cores --mem --no-slurm --profile --debug
   --version --info --log-print`. Flags belonging to stubbed features remain
   parseable (§9).
6. **Slurm behavior** — auto-detect `sbatch`, submit long ops as batch jobs,
   outputs to `~/.local/share/froster/slurm/`, re-submit on failure.
7. **Hotspot CSV** — same columns (`User, AccD, ModD, GiB, MiBAvg, Folder,
   Group, TiB, FileCount, DirSize`) so shared-config teams with mixed
   Python/Go clients see consistent files.

---

## 4. What the Rewrite Deletes (redundancy inventory)

The Python codebase is acknowledged to be repetitive; a port-behavior-not-code
rule turns that into concrete deletions:

- **Ten near-identical `subcmd_*` dispatch wrappers** (`Commands.subcmd_config`
  … `subcmd_update`) plus a hand-rolled argparse tree with ~90 lines of
  embedded help prose → a declarative `cobra` command tree; help text lives
  with each command; dispatch disappears.
- **`ConfigManager` (~1,500 lines)** interleaves XDG path logic, interactive
  prompting, AWS-profile CRUD, ini round-tripping, and shared-config
  switching. In Go: a `config` package with a typed `Config` struct + a
  separate `wizard` package (huh forms) — prompting code stops being mixed
  into accessors.
- **Repeated boto3 client construction and try/except/`print_error()` blocks**
  (the same session-build + error-print pattern appears at every AWS call
  site) → one `awsx.Client` constructor; Go error wrapping (`fmt.Errorf("…:
  %w")`) replaces ~200 scattered `print_error()` calls, with a single
  top-level handler that prints and logs.
- **Duplicated S3 listing / bucket-check logic** between archive, restore,
  tier-change, and config paths → one `awsx` listing helper.
- **Global mutable state** (`cfg`, `args` threaded through every class,
  module-level `log()`) → dependency-injected structs; `log/slog` with a
  `--debug` level flag.
- **Dead / commented code** (`subcmd_ssh`/`scp` parser block is already
  commented out) → gone.
- **The ISO-8859-1→UTF-8 CSV conversion workaround** → unnecessary (Go handles
  arbitrary-byte filenames).
- **Textual CSS blocks duplicated across five `Table*` apps** → one shared
  Bubble Tea table component parameterized by columns/actions.

Rough expectation: behavior currently spread over ~8,500 lines of Python fits
in ~6,000–8,000 lines of Go *including* the new walker — with the EC2/SES/CE
code (~2,000 lines) dropped to stubs and the walker replacing an external C
program.

---

## 5. Proposed Repository & Module Layout

Development happens on this branch in a `go/` subdirectory until parity, then
the repo root flips (Python moves to `legacy/`):

```
go/
├── go.mod                        # module github.com/dirkpetersen/froster/go  (final: TBD)
├── cmd/froster/main.go           # entry point, wiring only
├── internal/
│   ├── cli/                      # cobra commands: one file per subcommand
│   │   ├── root.go               # global flags, version/info/log-print
│   │   ├── archive.go  restore.go  index.go  delete.go
│   │   ├── mount.go  config.go  credentials.go  update.go  test.go
│   │   └── stubs.go              # not-implemented messaging for --aws etc.
│   ├── config/                   # ini read/write, XDG paths, profiles, shared mode
│   ├── archivedb/                # froster-archives.json load/save, unknown-key-preserving
│   ├── walker/                   # pwalk replacement (§6.3)
│   ├── hotspots/                 # aggregation, thresholds, CSV writer (§6.4)
│   ├── archive/                  # archive workflow: tar small files, md5, upload, verify
│   ├── restore/                  # glacier trigger/poll, download, verify, untar, tier change
│   ├── transfer/                 # rclone-library wrapper: copy, check, stats (§6.2)
│   ├── mount/                    # rclone VFS mount/unmount (§6.2)
│   ├── awsx/                     # aws-sdk-go-v2: s3 control ops, sts, iam, profiles
│   ├── slurm/                    # detection, sbatch submission, job templates
│   ├── tui/                      # bubbletea: hotspot table, archive table, tier selector,
│   │   └── wizard/               #   huh-based config wizard
│   ├── nih/                      # NIH RePORTER client + grants TUI
│   └── logging/                  # slog setup, froster.log file handler
└── testdata/                     # golden fixtures generated by Python froster (§10)
```

Principles:

- `internal/` everywhere — this is an application, not a library; no public
  API commitment.
- Workflow packages (`archive`, `restore`) depend on capability packages
  (`transfer`, `awsx`, `walker`); capability packages don't know about
  workflows. The `cli` layer only parses flags and calls workflows.
- Every workflow function takes a `context.Context` — Ctrl-C, Slurm time
  limits, and future timeouts propagate uniformly (the Python version's
  signal handling is ad hoc).

---

## 6. Component Design

### 6.1 CLI (`internal/cli`)

`spf13/cobra` with aliases matching today's argparse tree exactly. A
compatibility test enumerates the Python parser's surface (subcommands,
aliases, flags, defaults) and asserts the cobra tree matches. Global flags
(`--cores`, `--mem`, `--no-slurm`, `--profile`, `--debug`) become persistent
flags on the root command.

### 6.2 rclone as a library (`internal/transfer`, `internal/mount`)

rclone is written in Go and importable: `github.com/rclone/rclone`. Two
integration styles exist:

1. **`librclone`** (`librclone/librclone`): the stable RPC facade — you call
   `RPC("sync/copy", jsonArgs)`. Stable API, but stringly-typed and designed
   for FFI consumers.
2. **Direct `fs` packages** (`fs`, `fs/sync`, `fs/operations`, `vfs`,
   `cmd/mountlib`): what rclone's own commands use. Typed, full-featured, but
   *not* a stability-guaranteed API — internals move between minor versions.

**Recommendation: direct `fs` packages, with rclone pinned per release and the
integration isolated behind our own two small interfaces** (`transfer.Engine`,
`mount.Mounter`). Rationale: we need progress stats (`fs/accounting`),
per-file md5 checking (`operations.CheckMd5` equivalent), and VFS mount —
librclone's JSON facade covers copy but makes mount/stats integration
awkward. The interface isolation caps the blast radius of rclone upgrades to
two files, and our five-operation surface (§3.1) keeps the contact area tiny.

Key mechanics:

- **Backends**: import only what we support — `backend/s3` covers AWS, GCS
  (S3 interop mode), Wasabi, IDrive, Ceph, Minio (all are S3-compatible
  profiles in froster today), plus `backend/local`. *Not* importing
  `backend/all` keeps the binary ~35–45 MB instead of ~90 MB.
- **Config without files**: froster currently synthesizes rclone remotes via
  environment variables and `:s3:bucket/path` connection strings. In-process,
  we build an `fs.Fs` with `fs.NewFs(ctx, ":s3,provider=AWS,region=…:bucket/path")`
  or a `configmap` populated from the froster profile — no rclone.conf ever
  touches disk, same as today.
- **Progress**: `fs/accounting.Stats(ctx)` gives typed transfer stats; we
  render them with bubbles/progress interactively or as periodic log lines
  under Slurm — replacing today's `-vvv` stderr scraping.
- **Checksum verify**: `operations.Check` with an md5 hash source reproduces
  `rclone checksum md5 .froster.md5sum remote:` semantics.
- **Mount**: `vfs` + `cmd/mountlib` with the go-fuse backend (pure Go, no
  CGO). Runtime still requires `/dev/fuse` and the `fusermount3` setuid
  helper — same OS prerequisite as today (froster already checks
  `shutil.which('fusermount3')`). Mount flags map to VFS options
  (`ReadOnly: true`, `NoChecksum: true`, `AllowNonEmpty`, default
  permissions). Unmount uses mountlib's unmount rather than shelling to
  `fusermount3 -u`. One behavioral improvement: today's mount is a
  fire-and-forget background subprocess; in-process we can offer
  `froster mount --daemon` (self-re-exec, like rclone's own `--daemon`) while
  keeping foreground mode for Slurm.
- **License**: rclone is MIT; froster is MIT. Static linking is clean.

**Fallback position** (recorded in case direct-API churn proves painful):
switch `transfer.Engine`'s implementation to librclone RPC without touching
any workflow code. That's the payoff of the interface isolation.

### 6.3 Filesystem walker (`internal/walker`) — the pwalk replacement

A from-scratch Go implementation (clean-room w.r.t. the GPL C pwalk; we own
the semantics, MIT-licensed):

- **Work model**: a bounded worker pool (default `min(32, NumCPU)`, matching
  pwalk's cap; `--cores` overrides) pulling directories from a work queue.
  Each worker `os.ReadDir`s its directory, `Lstat`s entries, emits one CSV
  row per inode, computes the per-directory rollup (`pw_dirsum` = sum of file
  sizes directly in the dir, `pw_fcount` = file count), and enqueues
  subdirectories. Unbounded queue growth is handled the same way python-pwalk
  does it: workers push discovered dirs to an overflow slice when the channel
  is full (avoids deadlock on deep/wide trees).
- **Row schema**: byte-identical to pwalk's CSV header (`inode, parent-inode,
  directory-depth, filename, fileExtension, UID, GID, st_size, st_dev,
  st_blocks, st_nlink, st_mode, st_atime, st_mtime, st_ctime, pw_fcount,
  pw_dirsum`) — this is what the hotspot stage and `Froster.allfiles.csv`
  consumers expect. Filename quoting matches pwalk (quotes doubled, raw bytes
  passed through).
- **Learnings carried over from python-pwalk**: per-worker output buffers
  flushed to per-worker spill files, merged at the end (no global lock on the
  writer); `.snapshot` directory filtering; `st_dev` capture for
  cross-filesystem detection; optional zstd compression of the output
  (`klauspost/compress/zstd`, pure Go) producing `.csv.zst` readable directly
  by DuckDB — preserving the "DuckDB-friendly output" decision.
- **Error policy**: permission errors are counted and logged, never fatal
  (matches pwalk); a summary line reports skipped entries.
- **Performance target**: ≥ C pwalk on the same hardware (goroutines schedule
  I/O-blocked stat calls efficiently; python-pwalk's benchmark suite in
  `~/gh/python-pwalk/benchmarks` is reusable as a harness for A/B testing).

### 6.4 Hotspot analysis (`internal/hotspots`)

Reproduces the DuckDB query + post-processing in one streaming pass:

1. Read the walker output (`.csv` or `.csv.zst`), select rows where
   `pw_fcount > -1 && pw_dirsum > 0` (directory-rollup rows only).
2. Compute derived columns (GiB, TiB, MiB-average) exactly as the SQL does.
3. Sort by `pw_dirsum` descending, apply the `thresholdGB` / `thresholdMB`
   filters, resolve UID/GID→names, convert times to days-ago, and write the
   hotspot CSV with today's exact header.
4. Aggregate `agedbytes` buckets for the summary report.

No SQL engine, no CGO. The intermediate `.csv.zst` remains on disk for
external DuckDB/visidata analysis (documented in the README as the supported
power-user path).

### 6.5 AWS control plane (`internal/awsx`)

`aws-sdk-go-v2` — `config.LoadDefaultConfig` honors the same
`~/.aws/credentials` + `~/.aws/config` profiles froster manages today, so
credential drop-in-compat is free. Operations:

- `s3`: `ListBuckets`/`CreateBucket`/`HeadBucket`, `ListObjectsV2`,
  `RestoreObject` (Glacier trigger with `Days` + `Tier` from
  `--retrieve-opt`), `HeadObject` restore-status polling (parse
  `x-amz-restore: ongoing-request="…"` — the SDK exposes it as
  `Restore *string`, same string parsing as Python), `CopyObject` with
  `MetadataDirective=COPY` + `StorageClass` for tier changes.
- `sts.GetCallerIdentity` for credential validation; `iam` checks used by the
  config wizard.
- Custom-endpoint support (Ceph/Minio/Wasabi/IDrive/GCS) via
  `BaseEndpoint` — mirrors today's `endpoint` profile key.
- Retries/backoff come from the SDK's standard retryer (replacing hand-rolled
  retry loops).

Division of labor is unchanged from today: **rclone (in-process) moves bytes;
the AWS SDK does control-plane calls.** We deliberately do *not* route
restore/tier-change through rclone's backend features — the SDK is the
first-class API for those and keeps behavior identical to boto3's.

### 6.6 TUI (`internal/tui`)

- One reusable Bubble Tea **table screen** (columns, rows, key bindings,
  multi-select, "Quit to CLI" action) instantiated four ways: hotspots,
  archived-folders (delete/restore), NIH grants, storage-tier selector — the
  five Textual apps with duplicated CSS collapse into one component plus
  configs.
- Modal confirmations (delete, tier change) as an overlay model.
- The config wizard uses `huh` forms (select/input/confirm groups) replacing
  inquirer prompt chains.
- **Slurm/non-TTY rule** (exists informally today, made explicit): every TUI
  has a headless equivalent — flags already cover this (`archive` with
  explicit folders, `--older/--newer/--larger` filters). Any code path must
  work with no TTY; TUIs are sugar. `test -t 0` gate at the CLI layer.

### 6.7 Slurm (`internal/slurm`)

Same strategy, dramatically simpler mechanics: detect `sbatch` on PATH,
estimate walltime, template a batch script whose payload is *the same froster
binary re-invoking itself* with `--no-slurm` appended — no venv activation, no
`PATH` reconstruction, no Python-version matching inside the job. Job output
to `~/.local/share/froster/slurm/`, `--cores`/`--mem` map to
`--cpus-per-task`/`--mem`, and the resubmit-on-failure hook is preserved.

### 6.8 Config & archive DB (`internal/config`, `internal/archivedb`)

- `gopkg.in/ini.v1` with `PreserveSurroundedQuote` and key-order preservation;
  round-trip tests against real config.ini files (including `[profile x]`
  sections and the shared-config redirection).
- Archive DB: typed struct for known keys + raw-message passthrough for
  unknown keys; file locking (`flock`) around read-modify-write — today's
  Python does non-atomic rewrites, which is a known hazard in shared-config
  mode. Write via temp-file + rename for atomicity. (Both are invisible
  improvements, not format changes.)
- `update` subcommand: checks GitHub releases (as today) but the action
  becomes "download new static binary to the install path" — self-update is
  near-trivial for a single binary (`minio/selfupdate` or a 50-line
  download+rename).

### 6.9 Logging & errors

`log/slog` with two handlers: human-readable console (respecting `--debug`)
and the `~/.local/share/froster/froster.log` file (kept, so `--log-print`
still works). Errors wrap upward with context (`archiving %q: uploading: %w`)
and are printed once at the top level — replacing the scattered
`print_error()` traceback dumps. AWS errors keep the current improvement of
including the active profile name.

---

## 7. Workflows (end-to-end flows in the new architecture)

**Index**: `walker.Walk(folder)` → `.csv.zst` → `hotspots.Analyze` → hotspot
CSV (+ summary). One process, no tempfile-encoding conversions, no external
binaries.

**Archive**: resolve targets (CLI args or hotspot TUI) → per folder:
`walker` quick-scan → partition small files (< `max_small_file_size_kib`) →
`archive/tar` writer builds `Froster.smallfiles.tar` (unless `--no-tar`) →
parallel MD5 (worker pool, `crypto/md5`) → `.froster.md5sum` +
`Froster.allfiles.csv` → `transfer.Copy` (in-process rclone, storage class
set via S3 backend option) → `transfer.CheckMd5` verify → `archivedb` update.
`--recursive` iterates subfolders as today.

**Delete**: verify remote checksums (`transfer.CheckMd5`) → delete local files
→ write `Where-did-the-files-go.txt` (same template) → `archivedb` timestamp.

**Restore**: `archivedb` lookup → `awsx` HeadObject sweep → trigger
`RestoreObject` for cold objects (Bulk/Standard/Expedited from
`--retrieve-opt`) → poll/report status → when ready, `transfer.Copy` down
(unless `--no-download`) → md5 verify → untar smallfiles → mark restored.
`--aws`/`--monitor`/`--instance-type` print the §9 stub message.

**Tier change** (`restore --change-tier`): tier-selector TUI → confirm modal →
`awsx.ChangeStorageClass` (list + CopyObject loop with progress; skip objects
already in target class; refuse GLACIER/DEEP_ARCHIVE sources pending restore —
same rules as today) → `archivedb` update.

**Mount/Umount**: `archivedb` lookup → `mount.Mount(remote, mountpoint)`
(read-only VFS) → foreground or `--daemon`; `umount` via mountlib.

---

## 8. Build, Distribution, Platforms

- `CGO_ENABLED=0`; every chosen dependency (rclone s3/local backends, go-fuse,
  bubbletea, ini, zstd, aws-sdk-go-v2) is pure Go. Result: one static ELF.
- **goreleaser** matrix: `linux/amd64`, `linux/arm64` (first-class — HPC and
  Graviton). `darwin/arm64` best-effort (mount requires macFUSE; may ship
  with mount disabled). Windows out of scope (unchanged from today).
- Binary size estimate: 35–50 MB (rclone s3+local+vfs ≈ 25–30 MB, AWS SDK ≈
  8 MB, TUI ≈ 3 MB). Acceptable for the target environment; document
  `upx --lzma` as an optional squeeze if users care.
- Release: GitHub Releases with checksums; `install.sh` shrinks to
  curl-latest-binary; PyPI publishing continues only for the frozen Python
  line. Version scheme: go-froster starts at **v1.0.0-alpha**, declaring
  v1.0.0 = parity milestone.
- CI: `go test ./...`, `golangci-lint`, goreleaser snapshot builds, plus the
  cross-implementation golden tests (§10) run against a Minio service
  container so no AWS credentials are needed for PR CI; a nightly job runs
  the same suite against real AWS (including a real DEEP_ARCHIVE
  restore-status check, mocked in PR CI).

---

## 9. Stubbed Features (kept in CLI, documented for revival)

Per the scope decision, these parse but print:

```
Error: 'restore --aws' is not yet implemented in go-froster.
This feature exists in Python froster (pip install froster==0.22.x).
Track re-implementation: https://github.com/dirkpetersen/froster/issues/<n>
```

Revival notes, so the door stays open:

| Feature | Python surface | What a Go revival needs |
|---|---|---|
| **EC2 cloud restore** (`restore --aws`, `--instance-type`, `ssh` subcmd) | ~1,200 lines: AMI selection, instance-type auto-pick by restore size, security-group/key management, cloud-init bootstrap that installs froster, SSH/SCP helpers | `ec2` SDK client; cloud-init template becomes trivial (download one binary instead of pip-installing froster on the instance — the rewrite actively simplifies this feature); `golang.org/x/crypto/ssh` replaces subprocess ssh. Cleanest design: a separate `internal/cloudrestore` package so core stays lean. |
| **SES email notifications** | ~150 lines, used by EC2 monitor flow | `sesv2` client + one templated send call. Consider generalizing to a webhook/command hook instead of hard-coding SES. |
| **Cost Explorer monitoring** (`--monitor`) | ~400 lines: crontab install on EC2 instance, idle detection, cost query | `costexplorer` client; the crontab-on-instance pattern should be redesigned (systemd timer in cloud-init). Depends on EC2 restore reviving first. |

The `credentials` subcommand (profile checking) is **not** in this list — it
stays fully implemented (it's core `sts`/`iam` surface).

---

## 10. Testing & Parity Strategy

The drop-in requirement makes parity mechanically checkable:

1. **Golden fixtures**: run Python froster 0.22 against a synthetic tree
   (reuse `tests/generate_dummy_data.py` semantics) and capture: hotspot CSV,
   `.froster.md5sum`, `Froster.allfiles.csv`, tar member list,
   `Where-did-the-files-go.txt`, archive-DB entries, and the S3 object listing
   (against Minio). Commit these under `go/testdata/`. Go tests assert
   byte/semantic equality (CSV compared field-wise; timestamps normalized).
2. **Cross-implementation round-trip** (the critical test): *archive with
   Python 0.22 → restore with go-froster*, and *archive with go-froster →
   restore with Python 0.22*, against Minio in CI. This directly proves the
   drop-in claim in both directions.
3. **Config round-trip**: read every config.ini fixture, rewrite, diff.
4. **CLI-surface test**: generated dump of the argparse tree (subcommands,
   aliases, flags, defaults) checked against the cobra tree.
5. **Walker A/B**: python-pwalk's benchmark harness comparing row counts,
   dirsum/fcount rollups, and throughput vs C pwalk on a large tree
   (manual/nightly, not PR CI).
6. **Unit tests** land with each package from day one — a categorical upgrade
   over the current integration-only test suite.

---

## 11. Phased Plan

Each phase ends with something demonstrable; order chosen so the riskiest
integrations (rclone-as-library, walker performance) are validated first.

| Phase | Deliverable | Proves |
|---|---|---|
| **0. Spike** (short) | Throwaway prog: in-process rclone copy to Minio with progress stats + go-fuse mount/read/unmount; walker prototype vs C pwalk on 1M files | The two architectural bets, before committing |
| **1. Skeleton** | cobra tree (all commands/aliases/flags, stubs everywhere), config read/write, archivedb read/write, slog, CI | CLI + compat-contract foundations; config round-trip tests green |
| **2. Index** | walker + hotspots + hotspot TUI | `froster index` at parity; golden CSV tests green |
| **3. Archive + Delete** | tar/md5 pipeline, transfer.Copy/CheckMd5, archive TUI, Where-did-the-files-go | Python-restorable archives (cross-impl test A) |
| **4. Restore + Tier** | glacier trigger/poll, download/verify/untar, tier-change TUI | cross-impl test B; full core loop closed |
| **5. Mount + Slurm + polish** | VFS mount/daemon, sbatch integration, config wizard (huh), NIH grants, self-update, `test` subcommand | Full parity minus stubbed extras |
| **6. Beta → v1.0.0** | goreleaser artifacts, docs/README rewrite, migration note, nightly real-AWS CI | Ship |

Suggested checkpoint after Phase 0: if the rclone library spike reveals
unacceptable API churn pain, fall back to librclone RPC (§6.2) *before* the
transfer package grows.

---

## 12. Risks & Open Questions

| Risk | Assessment | Mitigation |
|---|---|---|
| rclone internal API churn | Real; rclone doesn't guarantee `fs/*` stability | Pin per release; isolate behind 2 interfaces; librclone RPC fallback; Phase-0 spike |
| go-fuse mount edge cases on HPC (old kernels, NFS homes, no fusermount3) | Same runtime prerequisites as today's rclone-binary mount — not a regression | Keep the existing "install fuse3" guidance; mount is optional functionality |
| Walker slower than C pwalk on exotic filesystems (Lustre/GPFS) | Unlikely (metadata-latency-bound) but unproven | Phase-0 A/B on a real HPC filesystem; keep `--cores` tunable |
| Textual→BubbleTea regressions (five screens to rebuild) | Medium effort, low risk; TUIs are sugar over headless paths | Headless-first rule (§6.6) |
| Binary size complaints | 35–50 MB is large vs a Python wheel but small vs a venv | Document; optional upx |
| Shared-config mode with mixed Python+Go clients during transition | Highest-stakes compat surface (concurrent JSON writes) | flock + atomic rename in Go (Python side already tolerates readers); cross-impl CI |
| Non-UTF-8 filenames | Go is *better* here (raw bytes) but golden tests must include Latin-1 fixture names | Fixture coverage |
| Two codebases during transition | Python is frozen (bugfix-only) by decision | Freeze announcement in README; route feature requests to Go |

Open questions (none block Phase 0):

1. **Module path / repo shape**: `go/` subdir in this repo (assumed here) vs a
   fresh `go-froster` repo. Subdir keeps issues/stars/history unified;
   separate repo gives a clean module path. Current plan assumes subdir.
2. **GCS native mode**: today GCS is used via S3-interop. Should go-froster
   ever import rclone's native `backend/googlecloudstorage` (+~5 MB)? Deferred
   — S3-interop parity first.
3. **`visidata` guidance**: README currently suggests visidata for hotspot
   browsing; with `.csv.zst` output we should document `duckdb` CLI
   one-liners instead. Cosmetic, Phase 6.
4. **macOS support level**: best-effort build or explicit "Linux only" for
   v1.0? Leaning best-effort-without-mount.

---

## 13. Relationship to python-pwalk and rclone-adapter

Both projects remain useful as standalone PyPI packages for the Python
ecosystem and are **not deprecated as libraries** — only their role as
froster's future architecture ends. Concretely reused here:

- python-pwalk: walker design (worker buffers, spillover, `.snapshot`
  filtering, zstd/DuckDB output contract) and its benchmark suite (§10.5).
- rclone-adapter: the typed-options catalog (`rclone_help.json`) is a handy
  reference for mapping froster's rclone flags onto rclone's Go option
  structs; its progress-event model informs `transfer`'s stats API.
