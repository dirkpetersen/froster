#!/bin/bash
# Regenerate the golden fixtures in this directory by running the REAL Python
# froster (v0.22.0 code, editable install) end-to-end against a local Minio.
#
# Requirements:
#   - froster dev venv at $REPO/.venv (see install.sh), containing froster,
#     pwalk and rclone in .venv/bin
#   - docker
#
# Usage: ./generate.sh
#
# Everything runs inside a sandbox HOME (/tmp/froster-golden/home) so the
# user's real ~/.config/froster, ~/.local/share/froster and ~/.aws are never
# touched. See MANIFEST.md for a description of every produced fixture and
# for the Python froster bugs/quirks this script works around.

set -uo pipefail

GOLDEN="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$GOLDEN/../../.." && pwd)"
VENV="${FROSTER_VENV:-$REPO/.venv}"
SB=/tmp/froster-golden
MINIO_NAME=froster-go-fixtures-minio
MINIO_PORT=9201
BUCKET=froster-golden

die() { echo "FATAL: $*" >&2; exit 1; }

[ -x "$VENV/bin/froster" ] || die "froster not found in $VENV/bin (set FROSTER_VENV)"
[ -x "$VENV/bin/pwalk" ] || die "pwalk not found in $VENV/bin"
[ -x "$VENV/bin/rclone" ] || die "rclone not found in $VENV/bin"

mc() { docker exec $MINIO_NAME mc "$@"; }

# ---------------------------------------------------------------------------
echo "=== [0] Minio container"
# ---------------------------------------------------------------------------
docker rm -f $MINIO_NAME >/dev/null 2>&1
docker run -d --name $MINIO_NAME -p $MINIO_PORT:9000 minio/minio server /data >/dev/null || die "minio start"
for i in $(seq 1 30); do
    curl -sf http://localhost:$MINIO_PORT/minio/health/live >/dev/null && break
    sleep 1
done
mc alias set local http://localhost:9000 minioadmin minioadmin >/dev/null || die "mc alias"
mc mb local/$BUCKET >/dev/null || die "mc mb"

# ---------------------------------------------------------------------------
echo "=== [1] Sandbox HOME + config"
# ---------------------------------------------------------------------------
rm -rf $SB
mkdir -p $SB/home/.config/froster $SB/home/.aws $SB/data $SB/bin $SB/pwalkcopy

# Pre-seed [UPDATE] timestamp: froster checks GitHub for updates every 7 days
# and, when an update is found on a non-interactive stdin, crashes with
# EOFError at input() (quirk; see MANIFEST.md).
cat > $SB/home/.config/froster/config.ini <<EOF
[USER]
name = Golden Fixture
email = golden@example.com

[DEFAULT_PROFILE]
profile = profile minio

[profile minio]
provider = Minio
credentials = minio
bucket_name = $BUCKET
archive_dir = froster
storage_class = STANDARD

[UPDATE]
timestamp = $(date +%s)
EOF

cat > $SB/home/.aws/credentials <<'EOF'
[minio]
aws_access_key_id = minioadmin
aws_secret_access_key = minioadmin
EOF
chmod 600 $SB/home/.aws/credentials

# froster reads region/endpoint from the *nested* "s3 =" block (boto3-style).
cat > $SB/home/.aws/config <<EOF
[profile minio]
region = us-east-1
s3 =
    endpoint_url = http://localhost:$MINIO_PORT
EOF

# Shim bin dir: froster resolves pwalk/rclone from the directory containing the
# `froster` entry script (froster_dir = dirname(realpath(which('froster')))).
# We copy the entry script (its venv shebang keeps pointing at the real venv)
# and wrap rclone to inject RCLONE_S3_UPLOAD_CUTOFF=0: rclone >= 1.70 (AWS SDK
# Go v2) fails single-part PutObject against plain-HTTP endpoints with
# "unseekable stream is not supported without TLS and trailing checksum".
# Froster spawns rclone with a fully-replaced environment, so the variable
# cannot be injected from outside; the wrapper is the only non-invasive way.
cp "$VENV/bin/froster" $SB/bin/froster
cp "$VENV/bin/pwalk" $SB/bin/pwalk
cat > $SB/bin/rclone <<EOF
#!/bin/bash
export RCLONE_S3_UPLOAD_CUTOFF=0
exec "$VENV/bin/rclone" "\$@"
EOF
chmod +x $SB/bin/rclone

export HOME=$SB/home
export PATH=$SB/bin:/usr/local/bin:/usr/bin:/bin

# Fresh fixture dirs
rm -rf "$GOLDEN"/{config,index,archive,archive-fail-latin1,delete,restore,logs}
mkdir -p "$GOLDEN"/{config,index,archive,archive-fail-latin1,delete,restore,logs}

# Isolation sanity check
froster --version > "$GOLDEN/version.txt"
froster --info > "$GOLDEN/info.txt"
grep -q "$SB/home/.config/froster/config.ini" "$GOLDEN/info.txt" || die "isolation check failed"
froster credentials > "$GOLDEN/logs/credentials.log" 2>&1
grep -q 'credentials are valid' "$GOLDEN/logs/credentials.log" || die "minio credentials"

# ---------------------------------------------------------------------------
echo "=== [2] Dummy trees"
# ---------------------------------------------------------------------------
"$VENV/bin/python3" "$GOLDEN/generate_tree.py" $SB/data || die "generate_tree"
TREE=$SB/data/golden-tree
HOT=$SB/data/hotspot-tree

# Snapshot of every original file's md5 (for the end-to-end round-trip check).
( cd $SB/data && find golden-tree -type f -print0 | sort -z | xargs -0 md5sum ) \
    > "$GOLDEN/restore/original-files.md5"

# ---------------------------------------------------------------------------
echo "=== [3] index"
# ---------------------------------------------------------------------------
# Raw pwalk output (fixture for the Go walker; ISO-8859-1 bytes preserved).
$SB/bin/pwalk --NoSnap --one-file-system --header "$TREE" > "$GOLDEN/index/pwalk-raw-golden-tree.csv" 2>/dev/null
$SB/bin/pwalk --NoSnap --one-file-system --header "$HOT" > "$GOLDEN/index/pwalk-raw-hotspot-tree.csv" 2>/dev/null

# KNOWN BUG (captured): indexing a tree with a non-UTF-8 (Latin-1) filename
# fails: `grep -v ",-1,0$"` sees the pwalk CSV as binary and emits
# "Binary file ... matches", which DuckDB then cannot parse.
froster --no-slurm index "$TREE" > "$GOLDEN/logs/index-golden-tree.log" 2>&1
echo "exit=$? (expected 1: Latin-1 filename breaks grep/DuckDB)" >> "$GOLDEN/logs/index-golden-tree.log"
grep -q 'BinderException\|Binder Error' "$GOLDEN/logs/index-golden-tree.log" || die "expected index failure not reproduced"

froster --no-slurm index --pwalk-copy $SB/pwalkcopy "$HOT" > "$GOLDEN/logs/index-hotspot-tree.log" 2>&1 || die "index hotspot-tree"
cp $SB/home/.local/share/froster/hotspots/+tmp+froster-golden+data+hotspot-tree.csv "$GOLDEN/index/hotspots-hotspot-tree.csv"
cp $SB/pwalkcopy/+tmp+froster-golden+data+hotspot-tree.csv "$GOLDEN/index/pwalkcopy-hotspot-tree.csv"

# ---------------------------------------------------------------------------
echo "=== [4] archive: expected failure with Latin-1 filename"
# ---------------------------------------------------------------------------
# KNOWN BUG (captured): archive crashes with UnicodeEncodeError writing the
# allfiles CSV row for caf\xe9.dat -- AFTER the file was already moved into
# Froster.smallfiles.tar and removed from disk (destructive partial state).
froster --no-slurm archive --recursive "$TREE" > "$GOLDEN/archive-fail-latin1/archive-attempt.log" 2>&1
echo "exit=$? (expected 1: UnicodeEncodeError on surrogate from Latin-1 filename)" >> "$GOLDEN/archive-fail-latin1/archive-attempt.log"
grep -q 'UnicodeEncodeError' "$GOLDEN/archive-fail-latin1/archive-attempt.log" || die "expected latin-1 archive failure not reproduced"

cp "$TREE/Froster.allfiles.csv" "$GOLDEN/archive-fail-latin1/Froster.allfiles.csv.partial"
tar -tvf "$TREE/Froster.smallfiles.tar" > "$GOLDEN/archive-fail-latin1/smallfiles-tar-members.txt" 2>&1

# Recover with `archive --reset` (untars small files back, removes metadata).
froster --no-slurm archive --reset --recursive "$TREE" > "$GOLDEN/archive-fail-latin1/archive-reset.log" 2>&1 || die "archive --reset"
# Python froster simply cannot archive non-UTF-8 filenames; drop the file.
find "$TREE" -maxdepth 1 -name 'caf*.dat' -delete
# original-files.md5 keeps caf\xe9.dat out too (it never reaches S3):
grep -av 'caf' "$GOLDEN/restore/original-files.md5" > "$GOLDEN/restore/original-files.md5.tmp" \
    && mv "$GOLDEN/restore/original-files.md5.tmp" "$GOLDEN/restore/original-files.md5"

# ---------------------------------------------------------------------------
echo "=== [5] archive --recursive (clean)"
# ---------------------------------------------------------------------------
# KNOWN BUG (see archive-bug-emptydir-last/): the froster-archives.json entry
# is only written if the LAST folder visited by os.walk archived successfully.
# An empty dir is "skipped" (None), so if ext4 hash order happens to place
# empty-dir last, the whole recursive archive is missing from the database.
# Deterministic workaround: take empty-dir out for the archive run.
rmdir "$TREE/empty-dir" || die "empty-dir not empty?"
froster --no-slurm archive --recursive "$TREE" > "$GOLDEN/logs/archive-recursive.log" 2>&1 || die "archive"
mkdir "$TREE/empty-dir"   # put it back for the delete/restore stages
grep -q 'ARCHIVING SUCCESSFULLY COMPLETED' "$GOLDEN/logs/archive-recursive.log" || die "archive did not complete"

# Per-folder artifacts (flatten path with __)
for d in "" "sub_data" "sub_data/deeper"; do
    src="$TREE${d:+/$d}"
    tag="${d:-root}"; tag="${tag//\//__}"
    cp "$src/.froster.md5sum"        "$GOLDEN/archive/$tag.froster.md5sum"
    cp "$src/Froster.allfiles.csv"   "$GOLDEN/archive/$tag.Froster.allfiles.csv"
    cp "$src/Froster.smallfiles.tar" "$GOLDEN/archive/$tag.Froster.smallfiles.tar"
    tar -tvf "$src/Froster.smallfiles.tar" > "$GOLDEN/archive/$tag.smallfiles-tar-members.txt"
done

cp $SB/home/.local/share/froster/froster-archives.json "$GOLDEN/archive/froster-archives.json" \
    || die "froster-archives.json missing (recursive-archive last-folder bug?)"

# S3 object listing: key, size, storage class (+ per-object metadata incl.
# X-Amz-Meta-Md5chksum / X-Amz-Meta-Mtime that rclone sets on multipart uploads)
mc ls --recursive local/$BUCKET/ | awk '{$1="";$2="";$3="";sub(/^ +/,"")}1' | sort > "$GOLDEN/archive/s3-objects.txt"
mc ls --recursive --json local/$BUCKET/ > "$GOLDEN/archive/s3-objects.json"
mc stat --json --recursive local/$BUCKET/ > "$GOLDEN/archive/s3-objects-stat.json"

# ---------------------------------------------------------------------------
echo "=== [6] delete --recursive"
# ---------------------------------------------------------------------------
froster --no-slurm delete --recursive "$TREE" > "$GOLDEN/logs/delete-recursive.log" 2>&1 || die "delete"
grep -q 'DELETING SUCCESSFULLY COMPLETED' "$GOLDEN/logs/delete-recursive.log" || die "delete did not complete"

for d in "" "sub_data" "sub_data/deeper"; do
    src="$TREE${d:+/$d}"
    tag="${d:-root}"; tag="${tag//\//__}"
    cp "$src/Where-did-the-files-go.txt" "$GOLDEN/delete/$tag.Where-did-the-files-go.txt"
done
( cd $SB/data && find golden-tree | sort ) > "$GOLDEN/delete/post-delete-tree.txt"

# ---------------------------------------------------------------------------
echo "=== [7] restore --recursive"
# ---------------------------------------------------------------------------
froster --no-slurm restore --recursive "$TREE" > "$GOLDEN/logs/restore-recursive.log" 2>&1
echo "exit=$?" >> "$GOLDEN/logs/restore-recursive.log"

( cd $SB/data && find golden-tree | sort ) > "$GOLDEN/restore/post-restore-tree.txt"
for d in "" "sub_data" "sub_data/deeper"; do
    src="$TREE${d:+/$d}"
    tag="${d:-root}"; tag="${tag//\//__}"
    [ -f "$src/.froster-restored.md5sum" ] && cp "$src/.froster-restored.md5sum" "$GOLDEN/restore/$tag.froster-restored.md5sum"
done

# Per-folder: the restored md5 set must equal the archived md5 set.
for d in "" "sub_data" "sub_data/deeper"; do
    src="$TREE${d:+/$d}"
    diff <(sort "$src/.froster.md5sum") <(sort "$src/.froster-restored.md5sum") >/dev/null \
        || die "md5 set mismatch archive vs restore in ${d:-root}"
done

# Round-trip sanity check: every original file (minus caf\xe9.dat) must be back
# with identical content. Metadata files added by froster are ignored.
( cd $SB/data && md5sum -c "$GOLDEN/restore/original-files.md5" ) > "$GOLDEN/restore/roundtrip-check.txt" 2>&1
if grep -q 'FAILED' "$GOLDEN/restore/roundtrip-check.txt"; then
    echo "WARNING: round-trip check has failures (see restore/roundtrip-check.txt)"
else
    echo "Round-trip OK"
fi

# ---------------------------------------------------------------------------
echo "=== [8] snapshot config as used"
# ---------------------------------------------------------------------------
cp $SB/home/.config/froster/config.ini "$GOLDEN/config/config.ini"
cp $SB/home/.aws/config "$GOLDEN/config/aws-config"
cp $SB/home/.aws/credentials "$GOLDEN/config/aws-credentials"   # minioadmin defaults, not a secret
cp $SB/bin/rclone "$GOLDEN/config/rclone-wrapper.sh"

# ---------------------------------------------------------------------------
echo "=== [9] teardown"
# ---------------------------------------------------------------------------
docker rm -f $MINIO_NAME >/dev/null

echo "Golden fixtures regenerated in $GOLDEN"
