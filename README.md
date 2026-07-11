![image](https://user-images.githubusercontent.com/1427719/235330281-bd876f06-2b2a-46fc-8505-c065bb508973.png)


[![Test froster](https://github.com/dirkpetersen/froster/actions/workflows/test-go.yml/badge.svg)](https://github.com/dirkpetersen/froster/actions/workflows/test-go.yml)
[![Build froster](https://github.com/dirkpetersen/froster/actions/workflows/build-go.yml/badge.svg)](https://github.com/dirkpetersen/froster/actions/workflows/build-go.yml)
[![License](https://img.shields.io/github/license/dirkpetersen/froster)](https://raw.githubusercontent.com/dirkpetersen/froster/main/LICENSE)
[![PyPI (Python froster)](https://img.shields.io/pypi/v/froster.svg?label=pypi%20%28python%20froster%29)](https://pypi.org/project/froster/)

Froster is a user-friendly archiving tool for teams that move data between high-cost POSIX file systems and low-cost S3-like object storage systems. It prevents you from making [common archiving mistakes that can put your data at risk](https://dirk-petersen.medium.com/the-gruesome-job-of-managing-petabytes-of-scientific-data-466baaa5e8bc). It currently supports these S3 providers: AWS, GCS, Wasabi, IDrive, Ceph, and Minio. Froster can efficiently crawl your Posix file system metadata, recommend folders for archiving, generate checksums, and upload your selections to Glacier or other S3-like storage. It can retrieve data back from the archive using a single command.

</br>

## Two implementations, one tool

| | Where | Status |
|---|---|---|
| **froster** (this branch, [`go/`](go/)) | single static binary; rclone embedded as a library, native parallel crawler, no Python/pip/compiler needed | active development; core workflows implemented and tested |
| **Python froster** ([`python-froster`](../../tree/python-froster) branch) | the original implementation, installed via pip/pipx | stable; frozen (bugfixes only); releases continue on PyPI |

They are **drop-in compatible**: same `~/.config/froster/config.ini`, same
`froster-archives.json` database, same artifact files
(`.froster.md5sum`, `Froster.allfiles.csv`, `Froster.smallfiles.tar`,
`Where-did-the-files-go.txt`), same S3 object layout, and the same command
line. Archives written by one implementation restore bit-for-bit with the
other — you can switch back and forth at any time.

Design rationale and decisions for the rewrite: [`GO-ARCHITECTURE.md`](GO-ARCHITECTURE.md).

</br>

## Installing froster

Build from source (any recent Go; the pinned toolchain downloads
automatically — no other dependencies):

```bash
git clone https://github.com/dirkpetersen/froster.git
cd froster/go
CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o froster ./cmd/froster
./froster --version
```

Copy the resulting single `froster` binary anywhere on your PATH (it is
fully static on Linux). Pre-built binaries for linux/amd64, linux/arm64,
darwin/arm64 and darwin/amd64 are produced by CI for every change (see the
[Build froster](../../actions/workflows/build-go.yml) workflow
artifacts); tagged binary releases will follow.

Runtime prerequisites: none for archiving/restoring. `froster mount` needs
the `fuse3` OS package (as before). Slurm is auto-detected when present.

### Configuration

froster reads the same configuration the Python version writes. The
interactive `froster config` wizard is **not implemented yet**, so either
run the Python `froster config` once, or hand-write a minimal
`~/.config/froster/config.ini` — see the
[Configuration section of go/README.md](go/README.md#configuration) for a
copy-paste example. Verify with `froster credentials`.

### What works, what doesn't (yet)

Working end-to-end: `index`, `archive` (incl. `--recursive`, `--reset`,
small-file tarring, checksum verification), `delete`, `restore` (incl.
Glacier retrieval and `--change-tier`), `mount`/`umount`, `credentials`,
Slurm batch submission, and the interactive hotspot/archive/tier tables.

Not yet implemented: the `config` wizard, `update`, `test`, and the NIH
grant search TUI (`--nih-ref <id>` works). The EC2 restore
(`restore --aws`), SES email, and Cost-Explorer extras are stubbed — the
flags parse and print a clear message
([GO-ARCHITECTURE.md §9](GO-ARCHITECTURE.md)).

Developer documentation (build, tests, package map, compatibility
artifacts, documented deviations): [`go/README.md`](go/README.md).

</br>

## Installing Python froster (stable)

The Python implementation, its installer, tests, and full user
documentation live on the
[`python-froster`](../../tree/python-froster) branch. The published
installation command keeps working unchanged (it now transparently fetches
the installer from that branch):

```
curl -s https://raw.githubusercontent.com/dirkpetersen/froster/main/install.sh?$(date +%s) | bash
```

</br>

## Usage

The command line is identical across both implementations:

```
froster config      # configure profiles/buckets (Python only, for now)
froster index /your/folder            # crawl and find archiving candidates
froster archive [/your/folder]        # tar small files, checksum, upload, verify
froster delete /your/folder           # verify remote checksums, then delete local files
froster restore /your/folder          # trigger Glacier retrieval, download, verify, untar
froster restore --change-tier /f      # change S3 storage tier without restoring
froster mount /your/folder            # read-only FUSE mount of the archive
froster umount /your/folder
froster credentials                   # check the active profile/credentials
```

For the full user guide — hotspot workflows on HPC/Slurm, shared team
configuration, AWS setup for teams, NIH grant metadata, recursive
operations, and command-by-command walkthroughs — see the
[python-froster README](../../blob/python-froster/README.md); everything
there applies to froster except the installation and `froster config`
sections.

</br>

## In case of emergency

[`s3-restore.sh`](s3-restore.sh) is a standalone, implementation-independent
script that can restore froster archives using nothing but `rclone` and
`jq` — use it if froster itself is ever unavailable.
