package hotspots

import (
	"errors"
	"math"
	"os"
	"os/user"
	"path/filepath"
	"strconv"
	"time"
)

// errIntOverflow mirrors Python's OverflowError from int(float('inf')).
var errIntOverflow = errors.New("cannot convert float infinity to integer")

// errIntNaN mirrors Python's ValueError from int(float('nan')). It cannot
// occur with pwalk data (dirsum > 0 guarantees finite or +Inf values) but
// is handled for completeness.
var errIntNaN = errors.New("cannot convert float NaN to integer")

// pyInt truncates a float toward zero like Python's int(), erroring on
// non-finite values exactly where Python raises.
func pyInt(f float64) (int64, error) {
	if math.IsInf(f, 0) {
		return 0, errIntOverflow
	}
	if math.IsNaN(f) {
		return 0, errIntNaN
	}
	return int64(f), nil
}

// DaysAgo converts a Unix timestamp (float seconds, as returned by Python's
// os.path.getatime) to a whole number of days before now, reproducing
// Archiver.daysago exactly:
//
//   - A zero (or NaN, standing in for Python None) timestamp returns 0 —
//     Python's `if not unixtime: return 0` quirk means a file with an
//     epoch atime reads as 0 days old, not ~20000.
//   - Python subtracts two *naive local* datetimes
//     (datetime.now() - datetime.fromtimestamp(t)) and takes .days, which
//     floors toward negative infinity (a timestamp 1 hour in the future is
//     -1 days). The naive wall-clock subtraction is reproduced, including
//     its DST skew: across a DST change the difference is wall-clock, not
//     absolute, time.
//   - Timestamps outside Python's datetime range (years 1..9999) raise in
//     fromtimestamp; daysago catches everything and returns 0.
func DaysAgo(epochSeconds float64, now time.Time) int {
	if epochSeconds == 0 || math.IsNaN(epochSeconds) {
		return 0
	}
	sec := math.Floor(epochSeconds)
	if sec < -62135596800 || sec > 253402300800 { // roughly years 1..9999
		return 0
	}
	nsec := int64(math.Round((epochSeconds - sec) * 1e9))
	t := time.Unix(int64(sec), nsec).In(time.Local)
	if t.Year() < 1 || t.Year() > 9999 {
		return 0 // fromtimestamp raises; daysago's except returns 0
	}
	if now.IsZero() {
		now = time.Now()
	}
	n := now.In(time.Local)

	// Naive wall-clock difference, in whole seconds plus a nonnegative
	// sub-second remainder (which can never change the floored day count).
	totalSec := naiveUnix(n) - naiveUnix(t)
	if n.Nanosecond()-t.Nanosecond() < 0 {
		totalSec--
	}
	return int(floorDiv(totalSec, 86400))
}

// naiveUnix interprets the wall-clock fields of t as if they were UTC,
// mimicking arithmetic on Python naive datetimes.
func naiveUnix(t time.Time) int64 {
	y, mo, d := t.Date()
	h, mi, s := t.Clock()
	return time.Date(y, mo, d, h, mi, s, 0, time.UTC).Unix()
}

// floorDiv is Python's // for integers (rounds toward negative infinity).
func floorDiv(a, b int64) int64 {
	q := a / b
	if a%b != 0 && (a < 0) != (b < 0) {
		q--
	}
	return q
}

// NewestFileAtime returns the newest access time (float epoch seconds)
// among the regular files directly inside folderPath, reproducing
// Archiver._get_newest_file_atime:
//
//   - An empty or non-existent path (os.path.exists follows symlinks and
//     is false on any stat error) logs " Invalid folder path: ..." and
//     returns fallback.
//   - Entries named in skipNames (Archiver.dirmetafiles) are ignored.
//   - Symlinks are followed (os.path.isfile/getatime semantics); entries
//     that fail to stat are skipped, subdirectories are not descended into.
//   - If no file qualifies, or the directory cannot be listed (Python's
//     listdir exception path), fallback is returned.
//
// fallback is typically the folder's own st_atime from the pwalk CSV.
func NewestFileAtime(folderPath string, fallback float64, skipNames []string, logf func(string, ...any)) float64 {
	return newestFileTime(folderPath, fallback, sliceToSet(skipNames), logf, atimeOf)
}

// NewestFileMtime is NewestFileAtime for modification times, reproducing
// Archiver._get_newest_file_mtime.
func NewestFileMtime(folderPath string, fallback float64, skipNames []string, logf func(string, ...any)) float64 {
	return newestFileTime(folderPath, fallback, sliceToSet(skipNames), logf, mtimeOf)
}

func sliceToSet(names []string) map[string]struct{} {
	if names == nil {
		names = DirMetaFiles
	}
	set := make(map[string]struct{}, len(names))
	for _, n := range names {
		set[n] = struct{}{}
	}
	return set
}

// newestFileTime is the shared implementation of the newest-atime/mtime
// helpers; pick extracts the relevant timestamp from a followed-symlink
// stat result.
//
// One unobservable divergence: Python stats each entry twice (isfile, then
// getatime) and a failure of the *second* stat aborts the whole scan back
// to fallback; here a single stat is used, so such a race skips only the
// vanished entry.
func newestFileTime(folderPath string, fallback float64, skip map[string]struct{}, logf func(string, ...any), pick func(os.FileInfo) float64) float64 {
	if logf == nil {
		logf = func(string, ...any) {}
	}
	if folderPath == "" || !pathExists(folderPath) {
		logf(" Invalid folder path: %s", folderPath)
		return fallback
	}

	entries, err := os.ReadDir(folderPath)
	if err != nil {
		// Python: os.listdir raises, print_error, return fallback.
		return fallback
	}

	newest := math.Inf(-1)
	found := false
	for _, e := range entries {
		name := e.Name()
		if _, skipIt := skip[name]; skipIt {
			continue
		}
		fi, err := os.Stat(filepath.Join(folderPath, name))
		if err != nil || !fi.Mode().IsRegular() {
			continue // os.path.isfile is false (broken symlink, dir, error)
		}
		if v := pick(fi); !found || v > newest {
			newest = v
			found = true
		}
	}
	if !found {
		return fallback
	}
	return newest
}

// pathExists mirrors os.path.exists: stat following symlinks, false on any
// error (including permission errors).
func pathExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// mtimeOf converts a FileInfo modification time to float epoch seconds the
// way CPython computes st_mtime (sec + 1e-9*nsec as a C double).
func mtimeOf(fi os.FileInfo) float64 {
	t := fi.ModTime()
	return float64(t.Unix()) + 1e-9*float64(t.Nanosecond())
}

// resolveID applies the uid2user/gid2group contract: any lookup error
// falls back to the decimal ID string (Python returns the int, which
// csv.writer stringifies identically).
func resolveID(id int64, lookup func(int64) (string, error)) string {
	if name, err := lookup(id); err == nil {
		return name
	}
	return strconv.FormatInt(id, 10)
}

// UIDToUser resolves a UID to a username, falling back to the decimal UID
// string like Archiver.uid2user (pwd.getpwuid KeyError -> return uid).
func UIDToUser(uid int64) string {
	return resolveID(uid, lookupUserOS)
}

// GIDToGroup resolves a GID to a group name, falling back to the decimal
// GID string like Archiver.gid2group.
func GIDToGroup(gid int64) string {
	return resolveID(gid, lookupGroupOS)
}

func lookupUserOS(uid int64) (string, error) {
	u, err := user.LookupId(strconv.FormatInt(uid, 10))
	if err != nil {
		return "", err
	}
	return u.Username, nil
}

func lookupGroupOS(gid int64) (string, error) {
	g, err := user.LookupGroupId(strconv.FormatInt(gid, 10))
	if err != nil {
		return "", err
	}
	return g.Name, nil
}
