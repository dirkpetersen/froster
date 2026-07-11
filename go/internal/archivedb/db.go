package archivedb

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// ErrCorrupt is wrapped by errors returned when froster-archives.json
// exists but cannot be parsed. The Python implementation logs
// "Cannot read <path>, file corrupt?" and silently treats the DB as
// missing (reads return no entry, writes are aborted); the Go
// implementation instead surfaces the condition as an error so callers
// can refuse to continue rather than silently ignoring an existing
// archive database. This is a deliberate, documented deviation.
var ErrCorrupt = errors.New("archive database corrupt")

// DB is a handle to a froster-archives.json file. Load returns a snapshot
// of the file contents; mutating methods (Upsert, MarkDeleted,
// MarkRestored) re-read the file under an exclusive flock, apply the
// change, write atomically via temp-file+rename, and refresh the in-memory
// snapshot — so concurrent Go writers never lose each other's updates.
//
// A DB value is not safe for concurrent use by multiple goroutines; open
// one handle per goroutine (the file itself is protected by flock).
type DB struct {
	path    string
	entries map[string]*Entry
	order   []string // top-level key order as stored in the file
}

// Load reads the archive database at path. A missing file yields an empty
// database (mirroring Python, which starts with an empty dict). A file
// that exists but does not parse returns an error wrapping ErrCorrupt.
func Load(path string) (*DB, error) {
	db := &DB{path: path, entries: make(map[string]*Entry)}
	if err := db.reload(); err != nil {
		return nil, err
	}
	return db, nil
}

// Path returns the location of the underlying froster-archives.json file.
func (db *DB) Path() string { return db.path }

// Len returns the number of entries in the snapshot.
func (db *DB) Len() int { return len(db.entries) }

// reload replaces the in-memory snapshot with the current file contents.
func (db *DB) reload() error {
	data, err := os.ReadFile(db.path)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			db.entries = make(map[string]*Entry)
			db.order = nil
			return nil
		}
		return fmt.Errorf("archivedb: reading %s: %w", db.path, err)
	}
	entries, order, err := decodeDB(data)
	if err != nil {
		return fmt.Errorf("archivedb: cannot read %s, file corrupt?: %w (%w)", db.path, err, ErrCorrupt)
	}
	db.entries = entries
	db.order = order
	return nil
}

// decodeDB parses the top-level JSON object, preserving key order.
func decodeDB(data []byte) (map[string]*Entry, []string, error) {
	entries := make(map[string]*Entry)
	var order []string
	dec := json.NewDecoder(bytes.NewReader(data))
	tok, err := dec.Token()
	if err != nil {
		return nil, nil, err
	}
	if d, ok := tok.(json.Delim); !ok || d != '{' {
		return nil, nil, fmt.Errorf("top level is not a JSON object")
	}
	for dec.More() {
		keyTok, err := dec.Token()
		if err != nil {
			return nil, nil, err
		}
		key, ok := keyTok.(string)
		if !ok {
			return nil, nil, fmt.Errorf("non-string top-level key %v", keyTok)
		}
		valTok, err := dec.Token()
		if err != nil {
			return nil, nil, fmt.Errorf("entry %q: %w", key, err)
		}
		if d, ok := valTok.(json.Delim); !ok || d != '{' {
			return nil, nil, fmt.Errorf("entry %q is not a JSON object", key)
		}
		e := &Entry{}
		if err := e.unmarshalOrdered(dec); err != nil {
			return nil, nil, fmt.Errorf("entry %q: %w", key, err)
		}
		if _, dup := entries[key]; !dup {
			order = append(order, key)
		}
		entries[key] = e
	}
	if _, err := dec.Token(); err != nil { // consume closing '}'
		return nil, nil, err
	}
	return entries, order, nil
}

// encode renders the database exactly like Python's
// json.dump(data, file, indent=4): 4-space indent, ensure_ascii escapes,
// insertion-ordered keys, no trailing newline.
func encodeDB(entries map[string]*Entry, order []string) ([]byte, error) {
	var buf bytes.Buffer
	if len(order) == 0 {
		buf.WriteString("{}")
		return buf.Bytes(), nil
	}
	buf.WriteString("{\n")
	for i, key := range order {
		if i > 0 {
			buf.WriteString(",\n")
		}
		buf.WriteString(pyIndent)
		pyEscapeString(&buf, key)
		buf.WriteString(": ")
		if err := entries[key].writePy(&buf, 1); err != nil {
			return nil, fmt.Errorf("entry %q: %w", key, err)
		}
	}
	buf.WriteString("\n}")
	return buf.Bytes(), nil
}

// NormalizeKey converts a folder path into a database key the way Python
// does when adding entries: key = folder.rstrip(os.path.sep).
func NormalizeKey(folder string) string {
	return strings.TrimRight(folder, string(os.PathSeparator))
}

// Get returns the entry covering folder, mirroring Python's
// Archiver.froster_archives_get_entry:
//
//  1. an exact key match wins;
//  2. otherwise the nearest parent directory that has an entry with
//     archive_mode == "Recursive" is returned (this is how archived
//     subfolders are matched for recursive restore/delete);
//  3. otherwise nil.
func (db *DB) Get(folder string) *Entry {
	if e, ok := db.entries[folder]; ok {
		return e
	}
	// Python iterates pathlib.Path(folder).parents, which walks the
	// lexical parents of the (lightly normalized) path up to "/".
	p := filepath.Clean(folder)
	if e, ok := db.entries[p]; ok && p != folder {
		return e
	}
	for {
		parent := filepath.Dir(p)
		if parent == p {
			return nil
		}
		if e, ok := db.entries[parent]; ok && e.ArchiveMode == ModeRecursive {
			return e
		}
		p = parent
	}
}

// All returns every entry sorted by the timestamp key in reverse
// (newest first), the ordering Python uses in archive_json_get_csv for the
// interactive archive tables. The sort is stable, so entries with equal
// timestamps keep file order.
func (db *DB) All() []*Entry {
	keys := append([]string(nil), db.order...)
	sort.SliceStable(keys, func(i, j int) bool {
		return db.entries[keys[i]].Timestamp > db.entries[keys[j]].Timestamp
	})
	out := make([]*Entry, len(keys))
	for i, k := range keys {
		out[i] = db.entries[k]
	}
	return out
}

// EntriesUnder returns all entries whose key equals parent or lies below
// it in the directory tree, sorted by key. Python has no direct
// equivalent (its recursive restore walks the local filesystem and calls
// froster_archives_get_entry per subfolder); this helper lets Go find
// archived subfolders even after the local tree was deleted.
func (db *DB) EntriesUnder(parent string) []*Entry {
	parent = NormalizeKey(parent)
	var keys []string
	for _, k := range db.order {
		if k == parent || strings.HasPrefix(k, parent+"/") {
			keys = append(keys, k)
		}
	}
	sort.Strings(keys)
	out := make([]*Entry, len(keys))
	for i, k := range keys {
		out[i] = db.entries[k]
	}
	return out
}

// Upsert inserts or wholesale-replaces the entry keyed by
// NormalizeKey(e.LocalFolder), exactly like Python's
// _archive_json_add_entry (data[key] = value). The write is performed
// under an exclusive flock with a fresh read of the file, so concurrent
// updates to other keys are preserved.
func (db *DB) Upsert(e *Entry) error {
	if e == nil {
		return errors.New("archivedb: nil entry")
	}
	key := NormalizeKey(e.LocalFolder)
	if key == "" {
		return fmt.Errorf("archivedb: entry has no usable local_folder (%q)", e.LocalFolder)
	}
	return db.mutate(func() error {
		if _, exists := db.entries[key]; !exists {
			db.order = append(db.order, key)
		}
		db.entries[key] = e
		return nil
	})
}

// UpsertAt stores e under an explicit key instead of e.LocalFolder. Python
// needs this in exactly one place: a tier change on a subfolder of a
// recursive archive re-keys a copy of the parent entry under the requested
// subfolder path while keeping the copy's local_folder pointing at the
// parent (froster.py _change_storage_tier ~7500).
func (db *DB) UpsertAt(folder string, e *Entry) error {
	if e == nil {
		return errors.New("archivedb: nil entry")
	}
	key := NormalizeKey(folder)
	if key == "" {
		return fmt.Errorf("archivedb: empty key (%q)", folder)
	}
	return db.mutate(func() error {
		if _, exists := db.entries[key]; !exists {
			db.order = append(db.order, key)
		}
		db.entries[key] = e
		return nil
	})
}

// MarkDeleted stamps the entry for folder with timestamp_deleted at time
// t. The key is written in Python datetime.isoformat() format. Note: the
// Python implementation never writes this key; it exists per
// GO-ARCHITECTURE.md §3.2/§7 and is ignored by Python readers (unknown
// keys survive Python rewrites because Python round-trips whole dicts).
func (db *DB) MarkDeleted(folder string, t time.Time) error {
	return db.stamp(folder, keyTimestampDeleted, t)
}

// MarkRestored stamps the entry for folder with timestamp_restored at
// time t. See MarkDeleted for compatibility notes.
func (db *DB) MarkRestored(folder string, t time.Time) error {
	return db.stamp(folder, keyTimestampRestored, t)
}

func (db *DB) stamp(folder, key string, t time.Time) error {
	return db.mutate(func() error {
		e := db.Get(folder)
		if e == nil {
			return fmt.Errorf("archivedb: no entry found for %q in %s", folder, db.path)
		}
		field := e.knownField(key)
		if !containsString(e.order, key) && e.order != nil {
			// Loaded entry: append the key at the end, matching Python
			// dict insertion order semantics.
			e.order = append(e.order, key)
		}
		*field = FormatTimestamp(t)
		return nil
	})
}

// mutate performs a locked read-modify-write cycle: acquire an exclusive
// flock on a sidecar lock file, reload the database from disk, apply fn to
// the fresh snapshot, and write the result atomically (temp file + rename,
// preserving the original file's permissions). The Python implementation
// does an unlocked, non-atomic rewrite; the file format is unchanged, only
// the write discipline is safer.
func (db *DB) mutate(fn func() error) error {
	dir := filepath.Dir(db.path)
	// Python: os.makedirs(dirname, exist_ok=True, mode=0o775)
	if err := os.MkdirAll(dir, 0o775); err != nil {
		return fmt.Errorf("archivedb: creating %s: %w", dir, err)
	}

	unlock, err := lockFile(db.path + ".lock")
	if err != nil {
		return fmt.Errorf("archivedb: locking %s: %w", db.path, err)
	}
	defer unlock()

	// Re-read under the lock so concurrent writers are never clobbered.
	if err := db.reload(); err != nil {
		return err
	}
	if err := fn(); err != nil {
		return err
	}

	out, err := encodeDB(db.entries, db.order)
	if err != nil {
		return fmt.Errorf("archivedb: encoding %s: %w", db.path, err)
	}

	// Preserve the permissions of an existing file; default to 0644 for a
	// new one (what Python's open(..., 'w') yields under the usual umask).
	mode := fs.FileMode(0o644)
	if info, err := os.Stat(db.path); err == nil {
		mode = info.Mode().Perm()
	}

	tmp, err := os.CreateTemp(dir, ".froster-archives-*.json.tmp")
	if err != nil {
		return fmt.Errorf("archivedb: creating temp file: %w", err)
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName) // no-op after successful rename

	if _, err := tmp.Write(out); err != nil {
		tmp.Close()
		return fmt.Errorf("archivedb: writing %s: %w", tmpName, err)
	}
	if err := tmp.Chmod(mode); err != nil {
		tmp.Close()
		return fmt.Errorf("archivedb: chmod %s: %w", tmpName, err)
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return fmt.Errorf("archivedb: syncing %s: %w", tmpName, err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("archivedb: closing %s: %w", tmpName, err)
	}
	if err := os.Rename(tmpName, db.path); err != nil {
		return fmt.Errorf("archivedb: renaming %s to %s: %w", tmpName, db.path, err)
	}
	return nil
}
