// Package archivedb reads and writes the froster archive database
// (froster-archives.json) with full drop-in compatibility with the Python
// implementation (froster/froster.py, Archiver._archive_json_add_entry and
// friends).
//
// The database is a single JSON object keyed by the absolute local folder
// path (with any trailing path separator stripped); each value describes one
// archive operation. Python writes the file with json.dump(indent=4) and no
// locking; this package produces byte-identical formatting but adds flock
// serialization and atomic temp-file+rename writes, both invisible to
// Python readers.
package archivedb

import (
	"bytes"
	"encoding/json"
	"fmt"
	"time"
)

// Known entry keys. Sources:
//
//	current Python writer (froster/froster.py, Archiver.archive ~L4357):
//	    local_folder, archive_folder, s3_storage_class, profile, provider,
//	    endpoint, archive_mode, timestamp, timestamp_archive, user,
//	    nih_project (only with --nih-ref)
//	legacy Python writer (pre-0.13, commit c787ea2):
//	    nih_project_url, nih_project_pi (and no provider/endpoint keys)
//	GO-ARCHITECTURE.md §3.2 / §7 (never written by any Python version;
//	introduced by the Go rewrite via MarkDeleted / MarkRestored):
//	    timestamp_deleted, timestamp_restored
const (
	keyLocalFolder       = "local_folder"
	keyArchiveFolder     = "archive_folder"
	keyS3StorageClass    = "s3_storage_class"
	keyProfile           = "profile"
	keyProvider          = "provider"
	keyEndpoint          = "endpoint"
	keyArchiveMode       = "archive_mode"
	keyTimestamp         = "timestamp"
	keyTimestampArchive  = "timestamp_archive"
	keyTimestampDeleted  = "timestamp_deleted"
	keyTimestampRestored = "timestamp_restored"
	keyUser              = "user"
	keyNIHProject        = "nih_project"
	keyNIHProjectURL     = "nih_project_url"
	keyNIHProjectPI      = "nih_project_pi"
)

// Archive modes as written by Python.
const (
	ModeSingle    = "Single"
	ModeRecursive = "Recursive"
)

// coreKeys are the keys the current Python writer always emits, in its
// dict-insertion order. A fresh Go-created Entry is serialized with exactly
// these keys (even when empty) so output matches Python's writer.
var coreKeys = []string{
	keyLocalFolder, keyArchiveFolder, keyS3StorageClass, keyProfile,
	keyProvider, keyEndpoint, keyArchiveMode, keyTimestamp,
	keyTimestampArchive, keyUser,
}

// optionalKeys are known keys that are only emitted when non-empty, in
// canonical order.
var optionalKeys = []string{
	keyNIHProject, keyNIHProjectURL, keyNIHProjectPI,
	keyTimestampDeleted, keyTimestampRestored,
}

// Entry is one archive record. All known values are strings in the Python
// schema. Unknown keys found in the file are preserved verbatim (bytes and
// position) so a Python froster sharing the file never loses data.
type Entry struct {
	LocalFolder       string // absolute path that was archived
	ArchiveFolder     string // rclone-style remote, e.g. ":s3:bucket/prefix/abs/path"
	S3StorageClass    string // e.g. "DEEP_ARCHIVE"
	Profile           string // froster profile name
	Provider          string // e.g. "AWS" (absent in legacy entries)
	Endpoint          string // e.g. "https://s3.us-west-2.amazonaws.com" (absent in legacy entries)
	ArchiveMode       string // ModeSingle or ModeRecursive
	Timestamp         string // Python datetime.isoformat()
	TimestampArchive  string
	TimestampDeleted  string // set by MarkDeleted; never written by Python
	TimestampRestored string // set by MarkRestored; never written by Python
	User              string
	NIHProject        string // NIH grant ref, e.g. "R41HL129728"
	NIHProjectURL     string // legacy entries only
	NIHProjectPI      string // legacy entries only

	// extra holds unknown keys verbatim; order holds the key order as read
	// from the file (nil for entries created in Go).
	extra map[string]json.RawMessage
	order []string
}

// knownField returns a pointer to the typed field for a known key, or nil.
func (e *Entry) knownField(key string) *string {
	switch key {
	case keyLocalFolder:
		return &e.LocalFolder
	case keyArchiveFolder:
		return &e.ArchiveFolder
	case keyS3StorageClass:
		return &e.S3StorageClass
	case keyProfile:
		return &e.Profile
	case keyProvider:
		return &e.Provider
	case keyEndpoint:
		return &e.Endpoint
	case keyArchiveMode:
		return &e.ArchiveMode
	case keyTimestamp:
		return &e.Timestamp
	case keyTimestampArchive:
		return &e.TimestampArchive
	case keyTimestampDeleted:
		return &e.TimestampDeleted
	case keyTimestampRestored:
		return &e.TimestampRestored
	case keyUser:
		return &e.User
	case keyNIHProject:
		return &e.NIHProject
	case keyNIHProjectURL:
		return &e.NIHProjectURL
	case keyNIHProjectPI:
		return &e.NIHProjectPI
	}
	return nil
}

// Extra returns the raw JSON value of an unknown key preserved from the
// file, or nil if absent.
func (e *Entry) Extra(key string) json.RawMessage {
	return e.extra[key]
}

// SetExtra stores an unknown key that will be written back verbatim. Known
// keys must be set via their typed fields instead.
func (e *Entry) SetExtra(key string, raw json.RawMessage) error {
	if e.knownField(key) != nil {
		return fmt.Errorf("archivedb: %q is a known key; set the typed field", key)
	}
	if e.extra == nil {
		e.extra = make(map[string]json.RawMessage)
	}
	if e.order == nil {
		e.order = e.emitOrder()
	}
	if !containsString(e.order, key) {
		e.order = append(e.order, key)
	}
	e.extra[key] = raw
	return nil
}

// IsRecursive reports whether the entry was archived with archive_mode
// "Recursive" (Python: archive_get_bucket_info).
func (e *Entry) IsRecursive() bool { return e.ArchiveMode == ModeRecursive }

// IsGlacier reports whether the storage class requires a Glacier retrieval
// before download (Python: archive_get_bucket_info checks DEEP_ARCHIVE and
// GLACIER).
func (e *Entry) IsGlacier() bool {
	return e.S3StorageClass == "DEEP_ARCHIVE" || e.S3StorageClass == "GLACIER"
}

// unmarshalOrdered decodes an entry object from dec (positioned at the
// object's '{' already consumed by the caller reading its opening token via
// Token()), capturing key order and unknown keys.
func (e *Entry) unmarshalOrdered(dec *json.Decoder) error {
	for dec.More() {
		keyTok, err := dec.Token()
		if err != nil {
			return err
		}
		key, ok := keyTok.(string)
		if !ok {
			return fmt.Errorf("non-string entry key %v", keyTok)
		}
		var raw json.RawMessage
		if err := dec.Decode(&raw); err != nil {
			return fmt.Errorf("value of key %q: %w", key, err)
		}
		e.order = append(e.order, key)
		if f := e.knownField(key); f != nil {
			// Known values are strings in the Python schema. A JSON null
			// (never written by Python, but conceivable) is treated as "".
			if !bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
				if err := json.Unmarshal(raw, f); err != nil {
					return fmt.Errorf("key %q: expected string: %w", key, err)
				}
			}
		} else {
			if e.extra == nil {
				e.extra = make(map[string]json.RawMessage)
			}
			e.extra[key] = raw
		}
	}
	if _, err := dec.Token(); err != nil { // consume '}'
		return err
	}
	return nil
}

// emitOrder computes the key order used when writing the entry:
//
//  1. Keys in their as-read file order (known keys are re-emitted even if
//     the field is now empty, mirroring Python which round-trips whatever
//     the dict holds).
//  2. Known keys set after load (e.g. timestamp_deleted) appended at the
//     end in canonical order — exactly where Python's dict insertion order
//     would put them.
//
// For a fresh Go-created entry (order == nil) it is the current Python
// writer's order: all ten core keys plus any non-empty optional keys.
func (e *Entry) emitOrder() []string {
	var out []string
	if e.order == nil {
		out = append(out, coreKeys...)
	} else {
		out = append(out, e.order...)
	}
	for _, key := range optionalKeys {
		if f := e.knownField(key); *f != "" && !containsString(out, key) {
			out = append(out, key)
		}
	}
	// Defensive: core keys set on a loaded legacy entry that lacked them.
	for _, key := range coreKeys {
		if f := e.knownField(key); *f != "" && !containsString(out, key) {
			out = append(out, key)
		}
	}
	return out
}

// writePy writes the entry as a Python-json.dump(indent=4) object at the
// given nesting depth.
func (e *Entry) writePy(buf *bytes.Buffer, depth int) error {
	keys := e.emitOrder()
	if len(keys) == 0 {
		buf.WriteString("{}")
		return nil
	}
	inner := indentOf(depth + 1)
	buf.WriteString("{\n")
	for i, key := range keys {
		if i > 0 {
			buf.WriteString(",\n")
		}
		buf.WriteString(inner)
		pyEscapeString(buf, key)
		buf.WriteString(": ")
		if f := e.knownField(key); f != nil {
			pyEscapeString(buf, *f)
		} else if raw, ok := e.extra[key]; ok {
			if err := pyWriteRaw(buf, raw, depth+1); err != nil {
				return fmt.Errorf("key %q: %w", key, err)
			}
		} else {
			// Key was in file order but is neither known nor extra —
			// cannot happen, but write null rather than corrupt the file.
			buf.WriteString("null")
		}
	}
	buf.WriteString("\n")
	buf.WriteString(indentOf(depth))
	buf.WriteString("}")
	return nil
}

// MarshalJSON renders the entry in Python json.dump(indent=4) style
// (assuming top-level placement at depth 1, as inside the DB object).
func (e *Entry) MarshalJSON() ([]byte, error) {
	var buf bytes.Buffer
	if err := e.writePy(&buf, 1); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// UnmarshalJSON decodes a single entry object, preserving key order and
// unknown keys.
func (e *Entry) UnmarshalJSON(data []byte) error {
	*e = Entry{}
	dec := json.NewDecoder(bytes.NewReader(data))
	tok, err := dec.Token()
	if err != nil {
		return err
	}
	if d, ok := tok.(json.Delim); !ok || d != '{' {
		return fmt.Errorf("archivedb: entry is not a JSON object")
	}
	return e.unmarshalOrdered(dec)
}

// FormatTimestamp renders t exactly like Python's
// datetime.datetime.now().isoformat(): microsecond precision, and the
// fractional part omitted entirely when the microseconds are zero.
func FormatTimestamp(t time.Time) string {
	s := t.Format("2006-01-02T15:04:05")
	if us := t.Nanosecond() / 1000; us != 0 {
		s += fmt.Sprintf(".%06d", us)
	}
	return s
}

func indentOf(depth int) string {
	buf := make([]byte, 0, depth*len(pyIndent))
	for range depth {
		buf = append(buf, pyIndent...)
	}
	return string(buf)
}

func containsString(list []string, s string) bool {
	for _, v := range list {
		if v == s {
			return true
		}
	}
	return false
}
