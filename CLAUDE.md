# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Froster is a user-friendly archiving tool for teams that move data between high-cost POSIX file systems and low-cost S3-like object storage systems (AWS, GCS, Wasabi, IDrive, Ceph, Minio). It handles large-scale data archiving (hundreds of TiB to PiB), particularly on HPC systems with Slurm integration.

**Key capabilities:**
- Crawl file systems to identify archiving candidates ("hotspots")
- Archive folders to S3/Glacier with checksum verification
- Restore data from Glacier with retrieval status tracking
- Mount S3/Glacier storage via FUSE
- Slurm batch job integration for long-running operations

## Installation and Setup

### Install for development

```bash
# Clone and set up development environment
git clone https://github.com/dirkpetersen/froster.git
cd froster
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode
export LOCAL_INSTALL=true
./install.sh
```

The `install.sh` script installs:
- Froster Python package (via pip in editable mode)
- pwalk (C-based parallel file system crawler, compiled from source)
- rclone (S3 transfer tool, downloaded binary)

### Test commands

```bash
# Run basic feature tests
python3 tests/test_basic_features.py

# Run credentials tests
python3 tests/test_credentials.py

# Run all tests with unittest
python3 -m unittest discover tests/
```

## Architecture

### Single-File Monolithic Design

Froster is implemented as a **single 8000+ line Python file** (`froster/froster.py`). This design is intentional for:
- Simplified deployment on HPC systems
- Easy review by system administrators
- Reduced dependency complexity

### Core Classes

**ConfigManager** (line 127): Manages configuration using XDG Base Directory conventions
- Config location: `~/.config/froster/config.ini`
- Data location: `~/.local/share/froster/`
- AWS credentials: `~/.aws/credentials` and `~/.aws/config`
- Archive database: `~/.local/share/froster/froster-archives.json`

**AWSBoto** (line 1619): Direct AWS S3/Glacier operations using boto3
- Glacier retrieval triggering and status checking
- S3 bucket operations
- Storage class management (DEEP_ARCHIVE, GLACIER, etc.)

**Archiver** (line 3485): Main workflow orchestration
- File system indexing with pwalk
- Folder hotspot generation using DuckDB for CSV processing
- Small file tarring (<1 MiB files → `Froster.smallfiles.tar`)
- MD5 checksum generation and verification
- Archive metadata tracking in JSON database

**Rclone** (line 5972): S3 transfer operations wrapper
- Multi-threaded upload/download via rclone
- Progress tracking and logging
- Environment-based credential passing

**Slurm** (line 6263): Batch job submission for HPC environments
- Auto-submits long-running operations as Slurm jobs
- Job monitoring and output file generation
- Automatic re-execution on job failure

**Commands** (line 6843): CLI argument parsing and subcommand dispatch
- Routes subcommands: config, index, archive, delete, restore, mount, umount
- Handles global flags: --cores, --mem, --no-slurm, --profile, --debug

### Textual TUI Applications

Froster uses Textual for interactive selection interfaces:

**TableHotspots** (line 5767): Interactive folder selection from indexed hotspots
- Displays folders with size, avg file size, access/modify age
- Supports filtering by --older, --newer, --larger flags
- "Quit to CLI" generates archive command for batch operations

**TableArchive** (line 5862): Select previously archived folders for delete/restore

**TableNIHGrants** (line 5893): Search and link NIH research grants for FAIR metadata

### Key Data Flow

1. **Index**: pwalk → CSV → DuckDB filtering → hotspots CSV → froster-archives.json
2. **Archive**: Source folder → tar small files → MD5 checksums → rclone upload → checksum verify → update JSON database
3. **Delete**: Verify checksums → delete local files → leave `Where-did-the-files-go.txt` manifest
4. **Restore**: Check Glacier status → trigger retrieval if needed → wait → download with rclone → verify checksums → untar

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

### Running tests

```bash
# Single test file
python3 tests/test_basic_features.py

# All tests
python3 -m unittest discover tests/

# Tests require AWS credentials as environment variables
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET="..."
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

### Code navigation helpers

Key functions for understanding the codebase:
- `main()` (line 7907): Entry point
- `Commands.parse_arguments()`: CLI argument structure
- `Archiver._index_locally()` (line 3525): pwalk → hotspots generation
- `Archiver.do_archive()`: Main archive workflow
- `Rclone._run_rclone_command()` (line 6014): S3 transfers
- `AWSBoto.glacier_restore_status()`: Glacier retrieval checking

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

Releases are automated via GitHub Actions:

1. Update version in `pyproject.toml`
2. Push to `main` branch
3. Create GitHub release with tag format: `v<Major>.<Minor>.<Subminor>`
4. GitHub Action builds and publishes to PyPI automatically

Versioning:
- Major: Breaking changes or major features
- Minor: Backward-compatible new functionality
- Subminor: Bug fixes or small improvements

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
- Set during `froster config` or in config.ini

**Multiple users / shared configuration:**
- Set shared config directory during `froster config`
- Allows teams to share hotspot files and archive database
- Individual credentials remain in `~/.aws/`
