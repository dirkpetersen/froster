#!/usr/bin/env python3
"""Deterministically generate the dummy trees used for the froster golden fixtures.

Two trees are produced under the given base directory (default /tmp/froster-golden/data):

  golden-tree/    -- the tree that gets archived/deleted/restored (< 20 MiB real data).
                     Mix of files >1MiB and <1MiB, nested subfolders, an empty dir,
                     a name with spaces, a comma, a double quote, and one non-UTF-8
                     (Latin-1) filename created via raw bytes.

  hotspot-tree/   -- sparse files (>1GiB apparent size, ~0 disk usage) so that
                     `froster index` produces hotspot rows (froster v0.22.0 hardcodes
                     min_index_folder_size_gib=1 and min_index_folder_size_avg_mib=10;
                     these are NOT configurable via config.ini despite docs).

All file contents come from a fixed-seed PRNG and all mtimes/atimes are pinned to
FIXED_TIME so the trees are byte-for-byte reproducible (uid/gid/owner will differ
per machine; golden tests must normalize those columns).
"""

import os
import random
import sys

FIXED_TIME = 1767261845  # 2026-01-01 10:44:05 UTC (arbitrary fixed point)
SEED = 42


def write_file(path: bytes, size: int, rng: random.Random):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(rng.randbytes(size))
    os.utime(path, (FIXED_TIME, FIXED_TIME))


def write_sparse(path: bytes, size: int):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.truncate(size)
    os.utime(path, (FIXED_TIME, FIXED_TIME))


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else '/tmp/froster-golden/data'
    base = os.fsencode(base)
    rng = random.Random(SEED)

    MiB = 1024 * 1024
    KiB = 1024

    tree = base + b'/golden-tree'

    # Empty directory.
    # NOTE: created FIRST on purpose. froster v0.22.0 `archive --recursive` only writes
    # the froster-archives.json entry if the LAST subfolder visited by os.walk archived
    # successfully; an empty dir returns None ("skipping") and, if walked last, the
    # whole recursive archive is silently missing from the database (real bug).
    # os.walk yields dirs in on-disk (creation) order, so creating empty-dir before
    # sub_data makes sub_data/deeper the last visited folder.
    os.makedirs(tree + b'/empty-dir', exist_ok=True)

    # Files > 1 MiB (uploaded as-is)
    write_file(tree + b'/big_alpha.dat', 2 * MiB, rng)
    write_file(tree + b'/big_beta.dat', 3 * MiB + 512 * KiB, rng)
    # Boundary: exactly 1 MiB is NOT tarred (froster tars strictly < 1 MiB)
    write_file(tree + b'/exactly_1mib.dat', 1 * MiB, rng)
    # Boundary: one byte under 1 MiB IS tarred
    write_file(tree + b'/just_under_1mib.dat', 1 * MiB - 1, rng)

    # Small files (tarred into Froster.smallfiles.tar)
    write_file(tree + b'/small_report.txt', 10 * KiB, rng)
    write_file(tree + b'/file with spaces.txt', 5 * KiB, rng)
    write_file(tree + b'/values,comma.csv', 4 * KiB, rng)
    write_file(tree + b'/quote"file.txt', 3 * KiB, rng)
    # Latin-1 (non-UTF-8) filename: caf\xe9.dat
    write_file(tree + b'/caf\xe9.dat', 2 * KiB, rng)

    # Nested subfolders
    write_file(tree + b'/sub_data/big_gamma.dat', 1 * MiB + 512 * KiB, rng)
    write_file(tree + b'/sub_data/small_notes.md', 8 * KiB, rng)
    write_file(tree + b'/sub_data/deeper/tiny.bin', 100, rng)
    write_file(tree + b'/sub_data/deeper/mid_size.dat', 2 * MiB, rng)

    os.utime(tree + b'/empty-dir', (FIXED_TIME, FIXED_TIME))

    # Pin directory times (children first)
    for d in [tree + b'/sub_data/deeper', tree + b'/sub_data', tree]:
        os.utime(d, (FIXED_TIME, FIXED_TIME))

    # Hotspot tree: sparse files so dirsum > 1 GiB with ~0 disk usage
    hot = base + b'/hotspot-tree'
    write_sparse(hot + b'/sparse_a.dat', 800 * MiB)
    write_sparse(hot + b'/sparse_b.dat', 500 * MiB)
    write_sparse(hot + b'/subhot/sparse_c.dat', 1200 * MiB)
    for d in [hot + b'/subhot', hot]:
        os.utime(d, (FIXED_TIME, FIXED_TIME))

    print(f'Trees generated under {os.fsdecode(base)}')


if __name__ == '__main__':
    main()
