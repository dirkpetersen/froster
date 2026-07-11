# go-froster

Go rewrite of [froster](../README.md) as a single static binary: rclone is
embedded as a library (no subprocess), pwalk is reimplemented natively (no
C compile at install), and boto3 is replaced by aws-sdk-go-v2. It is a
**drop-in replacement** for the Python CLI: same `config.ini`, same
`froster-archives.json`, same artifact files (`.froster.md5sum`,
`Froster.allfiles.csv`, `Froster.smallfiles.tar`,
`Where-did-the-files-go.txt`), same S3 object layout, same CLI surface.
Design rationale and decisions: [`GO-ARCHITECTURE.md`](../GO-ARCHITECTURE.md)
(repo root).

## Status

Core workflows are implemented and tested end-to-end (including against
Minio and cross-checked against golden fixtures produced by Python froster
v0.22.0):

| Working | Not yet |
|---|---|
| `index` (native walker + hotspot analysis) | `config` interactive wizard |
| `archive` (incl. `--recursive`, `--reset`, small-file tarring, md5 verify) | `update` self-update check |
| `delete`, `restore` (incl. Glacier retrieval trigger/poll) | `test` self-test workflow |
| `restore --change-tier` (storage tier change) | interactive NIH grant TUI (`--nih-ref <ref>` works) |
| `mount` / `umount` (in-process FUSE) | `--default-profile` interactive selector |
| `credentials` | EC2/SES/Cost-Explorer extras — **stubbed** per GO-ARCHITECTURE.md §9 (`restore --aws`, `--monitor`, `--instance-type`, `mount --aws` parse but print "not yet implemented") |
| Slurm gating/submission, hotspot/archive/tier TUIs (Bubble Tea) | |

## Build & run

```bash
cd go
go build ./cmd/froster        # → ./froster
./froster --version           # froster v0.0.0-dev
```

`go.mod` declares `go 1.25.0` / `toolchain go1.25.12`; any reasonably
recent `go` command auto-downloads that toolchain (default
`GOTOOLCHAIN=auto`). No CGO is required: a plain `go build` links
dynamically against libc (host cgo default), while `CGO_ENABLED=0 go build`
produces a fully static ELF — the release configuration (GO-ARCHITECTURE.md §8).

Version is injected at build time via ldflags
(`internal/version.Version`, default `0.0.0-dev`):

```bash
go build -trimpath \
  -ldflags "-s -w -X github.com/dirkpetersen/froster/go/internal/version.Version=0.22.0" \
  -o froster ./cmd/froster
```

Binary size: ~41 MiB plain `go build`, ~29 MiB with `-s -w`. Most of that
is rclone's s3/local/VFS stack; only the `s3` and `local` rclone backends
are linked in (importing `backend/all` would roughly double this).

Note: `froster mount` re-executes this same binary as a detached FUSE
daemon (see `cmd/froster/main.go` and `workflow.IsMountDaemon`), like
Python's background rclone process.

## Dependency pinning: aws-sdk-go-v2 must track rclone

From the NOTE in [`go.mod`](go.mod), and worth repeating prominently:

> The `github.com/aws/aws-sdk-go-v2` module versions must track rclone's
> own pins (rclone's s3 backend is built on aws-sdk-go-v2; upgrading the
> SDK past rclone's tested versions breaks its middleware registration,
> e.g. `not found: S3100Continue`). When bumping rclone, re-align the
> aws-sdk versions to rclone's go.mod.

So: never `go get -u` the AWS SDK modules independently. Bump
`github.com/rclone/rclone` first, then copy rclone's aws-sdk-go-v2 /
smithy-go versions into our `go.mod`.

## Tests

```bash
cd go
go test ./...          # unit + Docker-guarded integration tests
go test -short ./...   # unit tests only (skips Minio integration tests)
```

### Guarded integration tests

All of these skip themselves (with a message) when their prerequisite is
missing, so `go test ./...` is always safe to run.

**Minio round-trips (need Docker).** Each launches a throwaway
`minio/minio` container and force-removes it afterwards; skipped when
`docker` is not in PATH, the daemon is unreachable, the container fails to
start, or `-short` is set:

| Test | Package | Container / port | Exercises |
|---|---|---|---|
| `TestMinioEndToEnd` | `internal/transfer` | `froster-go-transfer-minio` :9101 | rclone-as-library copy/checksum |
| `TestMinioIntegration` | `internal/awsx` | `froster-go-awsx-minio` :9301 | bucket ops, object listing, control plane |
| `TestMinioArchiveDeleteRestoreRoundTrip` | `internal/workflow` | `froster-go-workflow-minio` :9401 | full archive → delete → restore cycle |

```bash
go test -v -run TestMinioArchiveDeleteRestoreRoundTrip ./internal/workflow
```

**FUSE mount tests** (`internal/mount`): `TestMountLocalReadOnly`,
`TestExternalUnmount`. Skipped unless `/dev/fuse` exists and `fusermount3`
is in PATH.

**Walker golden test vs C pwalk** (`internal/walker`):
`TestGoldenAgainstCPwalk` compares byte-level CSV output against the
reference C pwalk binary. It looks for the binary at
`~/gh/python-pwalk/filesystem-reporting-tools/pwalk`, overridable with
`PWALK_C_BIN`; skipped when not found:

```bash
PWALK_C_BIN=/path/to/pwalk go test -v -run TestGoldenAgainstCPwalk ./internal/walker
```

**Walker performance vs C pwalk**: a wall-clock comparison on a ≥200k-file
tree, expensive, so opt-in:

```bash
WALKER_BENCH_VS_C=1 go test -run TestBenchmarkVsCPwalk -v ./internal/walker
go test -bench BenchmarkWalk ./internal/walker    # Go-only micro-benchmark
```

Known flake: `internal/walker` `TestZstdRoundTrip` walks the same tree
twice and can see directory `st_atime` differ by 1s between passes
(relatime); rerun on failure.

## Package map

All under `internal/` (one-line purpose; see each package's doc comment for
detail):

| Package | Purpose |
|---|---|
| `app` | The real `cli.App`: loads config, gates on credentials/Slurm, drives interactive selection, dispatches into `workflow`. Entry: `app.New()` |
| `archivedb` | Read/write `froster-archives.json`, byte-identical to Python's `json.dump(indent=4)`; adds flock + atomic writes (invisible to Python). Entry: `archivedb.Load` |
| `awsx` | AWS control plane (boto3/`AWSBoto` port): buckets, Glacier restore trigger/status, storage-tier changes via aws-sdk-go-v2. Errors annotated with the credentials profile name |
| `cli` | Cobra command tree; surface must match Python argparse exactly, enforced by `contract_test.go` against `testdata/cli-contract.json`. Entry: `cli.Execute(app)` |
| `config` | `config.ini` + XDG paths + `~/.aws/{config,credentials}`, in Python configparser's exact output format (round-trip safe) |
| `hotspots` | Hotspot analysis: pure-Go replacement of the DuckDB query in `Archiver._index_locally` (reads plain or zstd pwalk CSV). Entry: `hotspots.AnalyzeFile` |
| `logging` | Python-parity logging: stdout, plus `froster.log` append in debug mode (`--log-print` dumps it) |
| `mount` | Read-only FUSE mounts via rclone VFS/mountlib with the pure-Go go-fuse backend; reproduces Python's `rclone mount --allow-non-empty --default-permissions --read-only --no-checksum` in-process |
| `slurm` | Slurm detection, batch-script generation (same `#SBATCH` template/paths as Python), `sbatch` submission |
| `transfer` | rclone-as-library data plane: copy to/from S3-compatible storage, md5sum-file verification, rclone version string. Only s3+local backends linked |
| `tui` | Bubble Tea replacement for the five Python Textual apps: `PickHotspots`, `PickArchivedFolder`, `SelectStorageTier`, `PickString`, `Confirm` |
| `version` | Build-time version/commit, injected via `-ldflags -X` |
| `walker` | Native Go replacement for C pwalk 3.0.0; emits byte-compatible CSV (`pwalk --NoSnap --one-file-system --header`), optional zstd output. Entry: `walker.Walk` |
| `workflow` | The core workflows (archive/delete/restore/mount/umount/reset/index) with drop-in behavioral parity — every user-visible message and artifact format reproduced from the behavior spec, typos included |

`cmd/froster` is the thin main: mount-daemon re-exec detection, then
`cli.Execute(app.New())`.

## Compatibility corner

Three artifacts define "drop-in compatible"; keep them in sync with any
behavior change:

- **CLI contract** — [`testdata/cli-contract.json`](testdata/cli-contract.json):
  a JSON dump of Python froster's argparse tree (subcommands, aliases,
  flags, defaults). `internal/cli/contract_test.go` asserts the cobra tree
  matches. Regenerate (needs the Python dev venv, see `install.sh`):

  ```bash
  # from the repo root
  unset SLURM_CPUS_ON_NODE SLURM_MEM_PER_NODE
  .venv/bin/python3 go/testdata/dump_cli_contract.py > go/testdata/cli-contract.json
  ```

- **Behavior spec** — [`docs/python-behavior-spec.md`](docs/python-behavior-spec.md):
  the authoritative, line-referenced description of Python froster v0.22.0
  behavior (messages, exit codes, artifact formats, DB mutations). Workflow
  code cites spec sections in comments.

- **Golden fixtures** — [`testdata/golden/`](testdata/golden/): artifacts
  captured from a real Python froster v0.22.0 index → archive → delete →
  restore cycle against Minio. [`MANIFEST.md`](testdata/golden/MANIFEST.md)
  describes every file, the normalization rules (what is non-deterministic),
  and the Python quirks/bugs discovered (Q1–Q12). Regenerate (needs docker
  + the dev venv):

  ```bash
  FROSTER_VENV=/path/to/froster/.venv go/testdata/golden/generate.sh
  ```

### Deliberate deviations from Python froster

Everything else is bug-for-bug compatible (including message typos). The
exceptions are marked `DOCUMENTED DEVIATION` in the code; this is the
authoritative list:

1. **`froster umount` works.** Shipped Python `umount` always dies with a
   `TypeError` before doing anything (spec §4.2); Go implements the
   *intended* behavior (`internal/workflow/mount.go`,
   `internal/app/mount.go`). Relatedly, `umount` is its own cobra command
   rather than an argparse alias of `mount` — user-visible behavior
   identical (`internal/cli/commands.go`).
2. **Corrupt archive DB is a hard error.** Python logs "Cannot read …,
   file corrupt?" and silently pretends `froster-archives.json` is empty;
   Go refuses to continue (`internal/archivedb/db.go`,
   `internal/app/session.go`).
3. **Recursive archive always records its DB entry** when at least one
   subfolder archived and none failed. Python gates the write on the
   *last-walked* subfolder only, so an empty dir walked last silently
   loses the entry despite successful uploads (Python bug, quirk Q6;
   `internal/workflow/archive.go`).
4. **`archive --reset --recursive` resets every subdirectory.** Python's
   `return True` inside the walk loop resets at most one
   (`internal/workflow/archive.go`).
5. **`restore --no-download` exits 0 on success.** Python returns `None`
   there, which main treats as failure → exit 1
   (`internal/workflow/restore.go`).
6. **`restore --days` is validated up front**; a non-numeric value fails
   with a clear message instead of blowing up per-object inside boto
   (`internal/app/restore.go`).
7. **Tier change on a subfolder of a recursive archive updates the parent
   entry in place.** Python re-keys the parent entry under the subfolder
   path, duplicating it (`internal/app/restore.go`).
8. **Slurm resubmission from the hotspot TUI is non-interactive.** The
   selected folder is appended to the replayed argv; Python's equivalent
   hinges on a `--hotspots` token that never exists, so its batch job
   would re-open the TUI (`internal/app/hotspots.go`).
9. **`--version` prints the build-injected version.** Python prints the
   installed-dist version, which goes stale in editable installs (quirk
   Q1; `internal/version`).
10. **Walker vs C pwalk** (`internal/walker/walker.go` doc comment): a
    basename ending in `.` gets extension `""` instead of C pwalk's
    uninitialized stack memory; pwalk's `--exclude`/`--depth`/`--chown_*`
    options are not implemented (froster never uses them); no `setuid(0)`
    attempt at startup.

Behavior-invisible robustness additions (Python readers unaffected):
`archivedb` uses flock serialization and atomic temp-file+rename writes.
