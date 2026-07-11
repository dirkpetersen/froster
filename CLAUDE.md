# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Froster is a user-friendly archiving tool for teams that move data between high-cost POSIX file systems and low-cost S3-like object storage systems (AWS, GCS, Wasabi, IDrive, Ceph, Minio). It handles large-scale data archiving (hundreds of TiB to PiB), particularly on HPC systems with Slurm integration.

**Key capabilities:**
- Crawl file systems to identify archiving candidates ("hotspots")
- Archive folders to S3/Glacier with checksum verification
- Restore data from Glacier with retrieval status tracking
- Change storage tier of archived data without restoring it
- Mount S3/Glacier storage via FUSE
- Slurm batch job integration for long-running operations

## Repository Layout — Two Implementations

**This branch (`main`) contains only the Go implementation (`go/`); there is
no Python code anywhere in this tree.** The original Python implementation
is **frozen** (bugfixes only) and lives entirely on the **`python-froster`**
branch, including its installer, tests, workflows, and full user README.
Both implementations are drop-in compatible (same config.ini,
froster-archives.json, artifact files, S3 layout, CLI surface), proven by
cross-implementation round-trip tests.

New feature work goes to Go. Apply a Python change only if it is a bugfix
(on `python-froster`), and consider whether it needs a Go counterpart.

### Documentation policy

`README.md` on `main` is the **user-facing product doc** and must read as
if froster has always been this single Go binary — no "two
implementations" framing, no mention that it was ever written in Python, no
links to the `python-froster` branch. The **only** place the Go rewrite is
acknowledged is the "Deferred features" section, which lists what earlier
(pre-v0.23) releases had that this one doesn't yet (`config` wizard,
`update`, `test`, NIH grant search TUI, EC2/SES/Cost-Explorer restore) and
notes that archives from any earlier version restore unchanged. When
correcting facts in `README.md`, adjust wording for the single-binary
reality (binary download, manual `config.ini`, built-in crawler/rclone)
rather than adding implementation-history commentary.

This restriction is specific to `README.md`. Engineering docs — this file,
`go/README.md`, `GO-ARCHITECTURE.md`, `go/docs/python-behavior-spec.md` —
are expected to reference `python-froster` freely; the facts there (fixture
regeneration, behavioral parity, the rewrite rationale) require it.

## Go Implementation (`go/`)

Key documents (read before making changes):
- `GO-ARCHITECTURE.md` (repo root): design decisions and implementation status
- `go/README.md`: build, test matrix, package map, configuration example, documented deviations
- `go/docs/python-behavior-spec.md`: the behavioral contract extracted from Python — the source of truth for workflow parity (workflow code cites its sections)
- `go/testdata/cli-contract.json`: the CLI surface, enforced by `internal/cli/contract_test.go` (regeneration requires a `python-froster` worktree; recipe in go/README.md)
- `go/testdata/golden/`: fixtures captured from real Python froster runs; `MANIFEST.md` documents known Python quirks/bugs (Q1–Q12)

### Common commands

```bash
cd go
go build ./cmd/froster        # build the binary (toolchain auto-downloads)
go build ./... && go vet ./... && go test ./...   # must stay green
go test -short ./...          # skip Docker/Minio integration tests
```

Docker-guarded integration tests (skip automatically without Docker):
transfer (Minio port 9101), awsx (9301), workflow archive→delete→restore
round-trip (9401). FUSE mount tests need `/dev/fuse` + `fusermount3`.
Walker golden test compares against C pwalk via `PWALK_C_BIN`.

Release build:
```bash
CGO_ENABLED=0 go build -trimpath -ldflags "-s -w \
  -X github.com/dirkpetersen/froster/go/internal/version.Version=<ver>" \
  -o froster ./cmd/froster
```

### Package map (one line each)

- `internal/cli` — cobra command tree; must match `cli-contract.json` exactly (argparse semantics: global flags before the subcommand, TraverseChildren)
- `internal/app` — implements `cli.App`; session/config bootstrap, credentials gate, Slurm gating, TUI fallbacks
- `internal/workflow` — archive/delete/restore/mount/reset/index workflows (parity with the behavior spec)
- `internal/walker` — native pwalk replacement (byte-compatible CSV, faster than C pwalk)
- `internal/hotspots` — pure-Go replacement for the Python DuckDB hotspot query (byte-identical output)
- `internal/transfer`, `internal/mount` — rclone embedded via its Go `fs` packages (s3+local backends only); FUSE via mountlib/go-fuse
- `internal/awsx` — AWS SDK v2 control plane (Glacier restore, tier change, buckets, STS)
- `internal/config`, `internal/archivedb` — drop-in config.ini and froster-archives.json access (order/unknown-key preserving; flock + atomic writes)
- `internal/slurm`, `internal/tui`, `internal/logging`, `internal/version` — supporting packages

### Critical rules

- **Do NOT bump aws-sdk-go-v2 versions independently** — they must track
  rclone's own pins (rclone's s3 backend breaks otherwise; see the NOTE in
  `go/go.mod`). When bumping rclone, re-align the SDK versions to rclone's go.mod.
- Behavioral parity with Python is the prime directive: exact messages,
  step order, exit codes, file formats. Divergences require a
  `DOCUMENTED DEVIATION` comment and an entry in go/README.md's deviations
  list. Python's own *bugs* are generally not reproduced (see that list).
- All four release targets must keep compiling:
  `GOOS=linux/darwin × GOARCH=amd64/arm64` with `CGO_ENABLED=0`
  (CI enforces via `.github/workflows/build-go.yml`).

### Not yet implemented (stubs return a clear error)

`config` wizard, `update`, `test`, NIH grant TUI, `--default-profile`
selector; EC2/SES/Cost-Explorer extras stubbed per GO-ARCHITECTURE.md §9.
These are the same items listed in `README.md`'s "Deferred features"
section — keep both in sync when one changes.

### Release process

Tag-triggered via `.github/workflows/release-go.yml`:

```bash
git tag -a vX.Y.Z -m "froster X.Y.Z"
git push origin vX.Y.Z
```

Builds all four `GOOS`/`GOARCH` targets (static, `-trimpath -ldflags "-s -w"`,
version/commit injected from the tag), generates a sha256 checksum file, and
publishes a GitHub release with the binaries attached and notes
auto-generated from commits. Verify with `gh run list --workflow=release-go.yml`
and `gh release view vX.Y.Z`.

## Important file artifacts (shared with Python froster)

**Generated during archiving:**
- `.froster.md5sum`: MD5 checksums of all files in folder
- `Froster.allfiles.csv`: Metadata for all files (including tarred files)
- `Froster.smallfiles.tar`: Archive of files < 1 MiB (threshold is hardcoded)
- `Where-did-the-files-go.txt`: Manifest created after deletion

**Configuration:**
- `~/.config/froster/config.ini`: user settings and profiles (XDG paths; `XDG_CONFIG_HOME`/`XDG_DATA_HOME` honored)
- `~/.local/share/froster/froster-archives.json`: archive database
- `~/.aws/credentials` + `~/.aws/config`: credentials/region/endpoint per profile

**Never manually delete archived folders; `froster delete` verifies remote checksums first.**

## Python froster (frozen, branch `python-froster`)

For anything Python: check out that branch (or a worktree). Its own
CLAUDE.md, README, tests (`python3 -m unittest discover tests/`), its own
`install.sh`, and PyPI release process live there — entirely separate from
the root `install.sh` on `main`, which installs the Go binary (see below).

## `install.sh` (root, `main` branch)

Installs the Go binary directly: detects OS/arch, resolves the latest (or
`--version`-pinned) release via GitHub's `/releases/latest` redirect (no
API/JSON parsing), downloads the matching `froster-<ver>-<os>-<arch>` asset,
verifies it against the release's sha256 checksums file, and installs to
`~/.local/bin` (if on PATH) / `~/bin` / `/usr/local/bin` (if root) /
`--dir` override. Test changes to it against a real release before pushing —
see the manual test recipe used during development (HOME/PATH overrides,
`fakeroot` for the root branch) rather than assuming syntax correctness.
