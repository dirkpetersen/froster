#!/usr/bin/env python3
"""Golden-file generator for the go/internal/hotspots package.

This harness writes the pwalk-format CSV fixtures in this directory and then
runs the *real* Python froster code (froster/froster.py) over them to produce
the expected hotspot CSV goldens and summary JSON. It reproduces the exact
pipeline of Archiver._index_locally after the pwalk run:

    grep -v ",-1,0$"  ->  iconv ISO-8859-1 -> UTF-8  ->  DuckDB SQL
    ->  post-processing loop (thresholds, _get_newest_file_atime/_mtime,
        uid2user/gid2group, daysago, int truncation)  ->  csv excel dialect

The post-processing loop below is copied verbatim from _index_locally
(lines ~3830-3870 of froster/froster.py) and calls the real Archiver
methods, so the goldens encode genuine Python semantics, quirks included.

Determinism:
  * TZ is forced to UTC and datetime.datetime.now() is patched to
    NOW = 2026-01-01 00:00:00 (epoch 1767225600).
  * Hotspot folders use non-existent paths so _get_newest_file_atime
    falls back to the CSV st_atime (the live-stat path is covered by
    Go-only tests against temp dirs).
  * UIDs/GIDs are either 0 (resolves to "root" on any Linux) or
    4200001/4200002 (never present, exercising the numeric fallback).

Usage:
    cd <repo root>
    .venv/bin/python3 go/internal/hotspots/testdata/gen_golden.py

Requires the repo venv (duckdb installed). Never touches ~/.config/froster
or ~/.local/share/froster: HOME and XDG dirs are pointed at a temp dir.
"""

import csv
import datetime as real_datetime
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))

# ---------------------------------------------------------------------------
# Sandbox the environment BEFORE importing froster (ConfigManager and log()
# read HOME/XDG paths at import/instantiation time).
# ---------------------------------------------------------------------------
_sandbox = tempfile.mkdtemp(prefix='froster-golden-home.')
os.environ['HOME'] = _sandbox
os.environ['XDG_CONFIG_HOME'] = os.path.join(_sandbox, '.config')
os.environ['XDG_DATA_HOME'] = os.path.join(_sandbox, '.local', 'share')
os.environ.pop('DEBUG', None)
os.environ['TZ'] = 'UTC'
time.tzset()

sys.path.insert(0, REPO_ROOT)
import froster.froster as F  # noqa: E402

NOW = real_datetime.datetime(2026, 1, 1, 0, 0, 0)
NOW_EPOCH = int(NOW.timestamp())  # 1767225600 with TZ=UTC
assert NOW_EPOCH == 1767225600, NOW_EPOCH


class FakeDateTime(real_datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        assert tz is None
        return cls(2026, 1, 1, 0, 0, 0)


# Patch the datetime module *object* froster imported.
F.datetime.datetime = FakeDateTime

# Build a bare Archiver carrying only what the helper methods need
# (mirrors Archiver.__init__ constants; avoids ConfigManager side effects).
a = F.Archiver.__new__(F.Archiver)
a.allfiles_csv_filename = 'Froster.allfiles.csv'
a.md5sum_filename = '.froster.md5sum'
a.md5sum_restored_filename = '.froster-restored.md5sum'
a.where_did_the_files_go_filename = 'Where-did-the-files-go.txt'
a.dirmetafiles = [a.allfiles_csv_filename,
                  a.md5sum_filename,
                  a.md5sum_restored_filename,
                  a.where_did_the_files_go_filename]
# Effective Python defaults: ConfigManager hardcodes min_index_folder_size_gib=1
# and min_index_folder_size_avg_mib=10; Archiver.__init__ then does
# `int(x) if x else 10`, yielding thresholdGB=1, thresholdMB=10.
a.thresholdGB = 1
a.thresholdMB = 10

DAYSAGED = [5475, 3650, 1825, 1095, 730, 365, 90, 30]

PWALK_HEADER = (b'inode,parent-inode,directory-depth,"filename"'
                b',"fileExtension",UID,GID,st_size,st_dev,st_blocks'
                b',st_nlink,"st_mode",st_atime,st_mtime,st_ctime,pw_fcount'
                b',pw_dirsum\n')


def days(n):
    return NOW_EPOCH - n * 86400


def dir_row(inode, name_bytes, uid, gid, atime, mtime, fcount, dirsum):
    """A pwalk directory-rollup row (fileProcess.c printStat format)."""
    return (b'%d,1,1,"%s","",%d,%d,4096,64,8,2,"0040755",%d,%d,%d,%d,%d\n'
            % (inode, name_bytes, uid, gid, atime, mtime, mtime, fcount, dirsum))


def file_row(inode, name_bytes, ext, uid, gid, size, atime, mtime):
    return (b'%d,2,2,"%s","%s",%d,%d,%d,64,2048,1,"0100644",%d,%d,%d,-1,0\n'
            % (inode, name_bytes, ext, uid, gid, size, atime, mtime, mtime))


BASE = b'/nonexistent/froster-golden'

BASIC_ROWS = [
    # R1: plain hotspot, resolvable uid/gid 0 -> root.
    dir_row(101, BASE + b'/proj1', 0, 0, days(10), days(20), 100, 50 * 2**30),
    # R2: GiB exactly at threshold (1.0), numeric uid/gid fallback.
    dir_row(102, BASE + b'/edge-exact', 4200001, 4200002,
            days(400), days(500), 100, 2**30),
    # R3: one byte below the GiB threshold -> excluded.
    dir_row(103, BASE + b'/below-gib', 0, 0, days(1), days(1), 1, 2**30 - 1),
    # R4: MiBAvg exactly at threshold (10.0), very old atime (all age buckets).
    dir_row(104, BASE + b'/mib-exact', 0, 4200002,
            days(6000), days(6001), 1024, 10 * 2**30),
    # R5: MiBAvg just below threshold (10240/1025) -> excluded.
    dir_row(105, BASE + b'/mib-below', 0, 0, days(1), days(1), 1025, 10 * 2**30),
    # R6: plain file row (pw_fcount=-1, pw_dirsum=0) -> removed by grep.
    file_row(106, BASE + b'/proj1/file1.dat', b'dat', 0, 0, 2**20,
             days(10), days(20)),
    # R7: directory with pw_dirsum=0 -> excluded by WHERE (and not counted).
    dir_row(107, BASE + b'/empty-dir', 0, 0, days(1), days(1), 5, 0),
    # R8: quote + comma in folder name (pwalk doubles the quote).
    dir_row(108, BASE + b'/we""ird,name', 0, 0,
            days(100), days(100), 3, 3 * 2**30),
    # R9: raw latin-1 byte 0xE9 in name -> iconv turns it into UTF-8 e-acute.
    dir_row(109, BASE + b'/caf\xe9', 0, 0, days(31), days(31), 2, 2 * 2**30),
    # R10: valid UTF-8 e-diaeresis bytes -> iconv mojibake (latin-1 reinterpretation).
    dir_row(110, BASE + b'/na\xc3\xafve', 0, 0, days(30), days(30), 4, 4 * 2**30),
    # R11: st_atime == 0 -> daysago() "not unixtime" quirk returns 0.
    dir_row(111, BASE + b'/atime-zero', 0, 0, 0, days(50), 8, 8 * 2**30),
    # R12: pw_fcount=0 but below GiB threshold -> short-circuit skip (no inf error).
    dir_row(112, BASE + b'/zerofiles-small', 0, 0, days(1), days(1), 0, 4096),
]

ZEROFILES_ROWS = [
    # Z1: normal hotspot, highest dirsum -> written before the failure.
    dir_row(201, BASE + b'/ok-first', 0, 0, days(40), days(40), 10, 20 * 2**30),
    # Z2: pw_fcount=0 with dirsum over the GiB threshold: MiBAvg = inf,
    #     int(inf) raises OverflowError and aborts the whole loop.
    dir_row(202, BASE + b'/zerofiles-big', 0, 0, days(10), days(10), 0, 2 * 2**30),
    # Z3: valid hotspot sorted after Z2 -> never written (loop aborted).
    dir_row(203, BASE + b'/ok-after', 0, 0, days(5), days(5), 5, 2**30),
]


def run_pipeline(raw_bytes, golden_csv_path):
    """grep -v ',-1,0$' -> iconv latin1->utf8 -> DuckDB -> verbatim loop."""
    import duckdb

    # grep -v ",-1,0$" (byte-wise, per physical line, like the shell pipeline)
    kept = [ln for ln in raw_bytes.split(b'\n') if not ln.endswith(b',-1,0')]
    filtered = b'\n'.join(kept)

    # iconv -f ISO-8859-1 -t UTF-8
    converted = filtered.decode('iso-8859-1').encode('utf-8')

    with tempfile.NamedTemporaryFile(suffix='.csv') as conv:
        conv.write(converted)
        conv.flush()

        sql_query = f"""SELECT UID as User,
                        st_atime as AccD, st_mtime as ModD,
                        pw_dirsum/1073741824 as GiB,
                        pw_dirsum/1048576/pw_fcount as MiBAvg,
                        filename as Folder, GID as Group,
                        pw_dirsum/1099511627776 as TiB,
                        pw_fcount as FileCount, pw_dirsum as DirSize
                    FROM read_csv_auto('{conv.name}',
                            ignore_errors=1)
                    WHERE pw_fcount > -1 AND pw_dirsum > 0
                    ORDER BY pw_dirsum Desc
                """
        con = duckdb.connect(':memory:')
        rows = con.execute(sql_query).fetchall()
        header = con.execute(sql_query).description
        con.close()

    totalbytes = 0
    numhotspots = 0
    agedbytes = [0] * len(DAYSAGED)
    error = None

    # --- verbatim from Archiver._index_locally (post-processing loop) ---
    with open(golden_csv_path, 'w') as f:
        writer = csv.writer(f, dialect='excel')
        writer.writerow([col[0] for col in header])
        try:
            for r in rows:
                row = list(r)
                if row[3] >= a.thresholdGB and row[4] >= a.thresholdMB:
                    atime = a._get_newest_file_atime(row[5], row[1])
                    mtime = a._get_newest_file_mtime(row[5], row[2])
                    row[0] = a.uid2user(row[0])
                    row[1] = a.daysago(atime)
                    row[2] = a.daysago(mtime)
                    row[3] = int(row[3])
                    row[4] = int(row[4])
                    row[6] = a.gid2group(row[6])
                    row[7] = int(row[7])
                    writer.writerow(row)
                    numhotspots += 1
                    totalbytes += row[9]
                    for i in range(0, len(DAYSAGED)):
                        if row[1] > DAYSAGED[i]:
                            agedbytes[i] += row[9]
        except OverflowError as e:
            # _index_locally catches this at function level and returns
            # False; the partially written CSV is left behind.
            error = f'{type(e).__name__}: {e}'
    # --- end verbatim ---

    summary = {
        'numhotspots': numhotspots,
        'totalbytes': totalbytes,
        'totalfolders': len(rows),
        'agedbytes': agedbytes,
        'daysaged': DAYSAGED,
        'error': error,
        'now_epoch': NOW_EPOCH,
    }
    return summary


def main():
    fixtures = [
        ('basic', BASIC_ROWS),
        ('zerofiles', ZEROFILES_ROWS),
    ]
    for name, rows in fixtures:
        raw = PWALK_HEADER + b''.join(rows)
        fixture_path = os.path.join(HERE, f'{name}.pwalk.csv')
        with open(fixture_path, 'wb') as f:
            f.write(raw)
        golden_path = os.path.join(HERE, f'{name}.golden.csv')
        summary = run_pipeline(raw, golden_path)
        with open(os.path.join(HERE, f'{name}.summary.json'), 'w') as f:
            json.dump(summary, f, indent=2)
            f.write('\n')
        print(f'{name}: {summary}')


if __name__ == '__main__':
    main()
