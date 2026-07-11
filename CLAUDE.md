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

## Two Implementations — Where to Work

**Froster is being rewritten in Go; the Go implementation in `go/` is the
primary development line.** The Python implementation (`froster/froster.py`)
is **frozen** — bugfixes only — and its maintenance branch is
`froster-python`. Both implementations are drop-in compatible (same
config.ini, froster-archives.json, artifact files, S3 layout, CLI surface),
proven by cross-implementation round-trip tests.

Key Go-side documents (read before touching `go/`):
- `GO-ARCHITECTURE.md` (repo root): design decisions and implementation status
- `go/README.md`: build, test matrix, package map, documented deviations
- `go/docs/python-behavior-spec.md`: the behavioral contract extracted from
  Python — the source of truth for workflow parity
- `go/testdata/cli-contract.json`: the CLI surface, enforced by a test
  (regenerate with `go/testdata/dump_cli_contract.py`)
- `go/testdata/golden/`: fixtures captured from real Python froster runs
  (MANIFEST.md documents known Python quirks/bugs)

Go rules: `cd go && go build ./... && go vet ./... && go test ./...` must
stay green (Docker-guarded Minio tests skip without Docker). Do NOT bump
aws-sdk-go-v2 versions independently — they must track rclone's pins (see
the NOTE in `go/go.mod`). New feature work goes to Go; only apply a Python
change if it is a bugfix, and consider whether the fix needs a Go
counterpart (or is already handled there).

## Installation and Setup

### Install for development

```bash
# Clone and set up development environment
git clone https://github.com/dirkpetersen/froster.git
cd froster
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode (auto-detects venv + pyproject.toml)
./install.sh
```

The `install.sh` script automatically detects development environments (when inside a virtual environment with `pyproject.toml` present) and installs:
- Froster Python package (via pip in editable mode)
- pwalk (C-based parallel file system crawler, compiled from source)
- rclone (S3 transfer tool, downloaded binary)

**Note:** You can still manually override by setting `export LOCAL_INSTALL=true` if needed.

### Test commands

```bash
# Run basic feature tests
python3 tests/test_basic_features.py

# Run credentials tests
python3 tests/test_credentials.py

# Run all tests with unittest
python3 -m unittest discover tests/

# Tests require AWS credentials as environment variables (see tests/config.py)
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET="..."
```

CI runs these same tests via GitHub Actions (`.github/workflows/test-basic-features.yml`, `test-credentials.yml`) on Python 3.10–3.13, plus install-script workflows.

## Architecture

### Single-File Monolithic Design

Froster is implemented as a **single 8500+ line Python file** (`froster/froster.py`). This design is intentional for:
- Simplified deployment on HPC systems
- Easy review by system administrators
- Reduced dependency complexity

### Core Classes

Line numbers below drift as the file changes; use them as starting points and confirm with a search for `class <Name>` or `def <name>`.

**ConfigManager** (line ~128): Manages configuration using XDG Base Directory conventions
- Config location: `~/.config/froster/config.ini`
- Data location: `~/.local/share/froster/`
- AWS credentials: `~/.aws/credentials` and `~/.aws/config`
- Archive database: `~/.local/share/froster/froster-archives.json`

**AWSBoto** (line ~1620): Direct AWS S3/Glacier operations using boto3
- `glacier_restore()`: triggers Glacier retrieval and checks restore status via the `ongoing-request` header
- `change_storage_class()`: storage tier migration for archived objects
- S3 bucket operations, EC2 instance management for `restore --aws`

**Archiver** (line ~3577): Main workflow orchestration
- `index()` / `_index_locally()`: file system indexing with pwalk, hotspot generation using DuckDB for CSV processing
- `archive()` / `_archive_locally()`: small file tarring (<1 MiB files → `Froster.smallfiles.tar`), MD5 checksum generation, rclone upload, verification
- `delete()`, `restore()` / `_restore_locally()`: post-archive workflows
- Archive metadata tracking in `froster-archives.json`

**Rclone** (line ~6285): S3 transfer operations wrapper
- `_run_rclone_command()`: multi-threaded upload/download via rclone
- Progress tracking and logging
- Environment-based credential passing

**Slurm** (line ~6589): Batch job submission for HPC environments
- Auto-submits long-running operations as Slurm jobs
- Job monitoring and output file generation
- Automatic re-execution on job failure

**NIHReporter** (line ~6982): Queries the NIH RePORTER API for grant metadata

**Commands** (line ~7169): CLI argument parsing and subcommand dispatch
- Routes subcommands: credentials, config, index, archive, delete, mount, umount, restore, update, test (each has a 3-letter alias, e.g. `arc`, `rst`)
- Handles global flags: --cores, --mem, --no-slurm, --profile, --debug

### Textual TUI Applications

Froster uses Textual for interactive selection interfaces:

**TableHotspots** (line ~5859): Interactive folder selection from indexed hotspots
- Displays folders with size, avg file size, access/modify age
- Supports filtering by --older, --newer, --larger flags
- "Quit to CLI" generates archive command for batch operations

**TableArchive** (line ~5954): Select previously archived folders for delete/restore

**TableNIHGrants** (line ~5985): Search and link NIH research grants for FAIR metadata

**TableStorageTierSelector** (line ~6128): Pick a new S3 storage tier (with cost info) for `froster restore --change-tier`, confirmed via a modal dialog

### Key Data Flow

1. **Index**: pwalk → CSV → DuckDB filtering → hotspots CSV → froster-archives.json
2. **Archive**: Source folder → tar small files → MD5 checksums → rclone upload → checksum verify → update JSON database
3. **Delete**: Verify checksums → delete local files → leave `Where-did-the-files-go.txt` manifest
4. **Restore**: Check Glacier status → trigger retrieval if needed → wait → download with rclone → verify checksums → untar
5. **Tier change**: `restore --change-tier` → TUI tier selection → `AWSBoto.change_storage_class()` (data in GLACIER/DEEP_ARCHIVE must be restored first)

## Common Development Tasks

### Building and testing locally

```bash
# After modifying froster/froster.py, test immediately (editable install)
froster --version
froster --info

# Test a complete workflow with dummy data
mkdir -p /tmp/test_archive
dd if=/dev/zero of=/tmp/test_archive/file1.dat bs=1M count=10
froster archive /tmp/test_archive
```

### Debugging

Use the `--debug` flag for verbose logging:
```bash
froster --debug archive /path/to/folder
```

Logs are written to `~/.local/share/froster/froster.log`. View with:
```bash
froster --log-print
```

### Important file artifacts

**Generated by Froster during archiving:**
- `.froster.md5sum`: MD5 checksums of all files in folder
- `Froster.allfiles.csv`: Metadata for all files (including tarred files)
- `Froster.smallfiles.tar`: Archive of files < 1 MiB
- `Where-did-the-files-go.txt`: Manifest created after deletion

**Configuration files:**
- `~/.config/froster/config.ini`: User settings and profiles
- `~/.local/share/froster/froster-archives.json`: Archive operation database

## Release Process

Releases are automated via GitHub Actions (`.github/workflows/pypi-release-publish.yml`):

1. Update version in `pyproject.toml`
2. Push to `main` branch
3. Create GitHub release with tag format: `v<Major>.<Minor>.<Subminor>`
4. GitHub Action builds and publishes to PyPI automatically

Versioning:
- Major: Breaking changes or major features
- Minor: Backward-compatible new functionality
- Subminor: Bug fixes or small improvements

Development happens on the `dev` branch; PRs merge `dev` → `main`.

## Important Considerations

**HPC-specific behaviors:**
- Auto-detects Slurm and submits long-running operations as batch jobs
- Use `--no-slurm` to force foreground execution
- Slurm outputs go to `~/.local/share/froster/slurm/`

**Checksum verification:**
- MD5 checksums are generated before upload and verified after
- Never manually delete archived folders; use `froster delete` to ensure verification

**Small file handling:**
- Files < 1 MiB are automatically tarred (saves on Glacier overhead of ~40 KiB per object)
- Configure threshold: `~/.config/froster/config.ini` → `max_small_file_size_kib`
- Disable tarring: `froster archive --no-tar`

**Storage class selection:**
- Default: AWS `DEEP_ARCHIVE` (most cost-effective, 48-72hr retrieval)
- Other classes: GLACIER, STANDARD_IA, ONEZONE_IA, INTELLIGENT_TIERING
- Set during `froster config` or in config.ini; change later with `froster restore --change-tier`

**Multiple users / shared configuration:**
- Set shared config directory during `froster config`
- Allows teams to share hotspot files and archive database
- Individual credentials remain in `~/.aws/`
