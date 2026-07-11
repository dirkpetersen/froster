// Package hotspots reproduces froster's hotspot-analysis stage: the DuckDB
// query and post-processing loop of Archiver._index_locally in
// froster/froster.py (v0.22.0), byte-for-byte where feasible.
//
// The Python pipeline this package replaces is:
//
//	pwalk CSV
//	  | grep -v ",-1,0$"                      (drop non-directory rows)
//	  | iconv -f ISO-8859-1 -t UTF-8          (unconditional transcode)
//	  | DuckDB: SELECT UID as User, st_atime as AccD, st_mtime as ModD,
//	            pw_dirsum/2^30 as GiB, pw_dirsum/2^20/pw_fcount as MiBAvg,
//	            filename as Folder, GID as Group, pw_dirsum/2^40 as TiB,
//	            pw_fcount as FileCount, pw_dirsum as DirSize
//	            WHERE pw_fcount > -1 AND pw_dirsum > 0
//	            ORDER BY pw_dirsum DESC        (read_csv_auto, ignore_errors=1)
//	  | Python loop: threshold filter, live newest-file atime/mtime,
//	            uid/gid resolution, days-ago conversion, int truncation
//	  | csv.writer(dialect='excel')            (CRLF, minimal quoting)
//
// # Encoding decision
//
// Python unconditionally transcodes the pwalk output from ISO-8859-1 to
// UTF-8 before parsing. Because every byte sequence is valid ISO-8859-1,
// this never fails — but it also means filenames that were already valid
// multi-byte UTF-8 are mojibake'd (each byte is reinterpreted as a Latin-1
// character: "é" becomes "Ã©"). This package applies the identical
// transformation (see latin1Reader), so the resulting hotspot CSV is
// byte-identical to Python's, mojibake included. A side effect faithfully
// reproduced: for folders whose names contain non-ASCII bytes, the
// transcoded path no longer matches the on-disk path, so the live
// newest-file atime/mtime scan fails its existence check and falls back to
// the CSV values — exactly as in Python.
//
// pwalk itself (fizwit/filesystem-reporting-tools fileProcess.c) doubles
// embedded double quotes and strips control bytes < 32 from names, so real
// input never contains embedded newlines.
//
// # Known deliberate divergences
//
//   - Rows DuckDB's ignore_errors=1 would silently drop (wrong field count,
//     unparseable numerics) are likewise skipped here; however a row with an
//     *empty* numeric field becomes NULL in DuckDB (kept, then crashing or
//     misbehaving later in Python) whereas this package skips it. pwalk
//     never emits such rows.
//   - Ties in the pw_dirsum sort keep input order (DuckDB's tie order is
//     unspecified).
//   - Python's grep step can mangle records whose filenames contain
//     newlines; real pwalk strips those bytes, so this cannot occur.
//   - UID/GID resolution uses os/user (pure-Go /etc/passwd parsing when
//     CGO_ENABLED=0) instead of glibc NSS; on LDAP/SSSD-only systems the
//     numeric fallback triggers where Python resolved a name.
package hotspots

import (
	"bufio"
	"bytes"
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"os"
	"sort"
	"strconv"
	"time"

	"github.com/klauspost/compress/zstd"
)

// DaysAged holds the aging buckets (in days) used for the Summary's
// AgedBytes accounting, matching the daysaged list in
// Archiver._index_locally: 15, 10, 5, 3, 2, 1 years, 90 and 30 days.
var DaysAged = []int{5475, 3650, 1825, 1095, 730, 365, 90, 30}

// Header is the exact hotspot CSV header row, as produced by the aliases in
// the Python SQL query.
var Header = []string{"User", "AccD", "ModD", "GiB", "MiBAvg", "Folder", "Group", "TiB", "FileCount", "DirSize"}

// DirMetaFiles are froster-generated metadata files ignored by the
// newest-file atime/mtime scan (Archiver.dirmetafiles). Note that
// Froster.smallfiles.tar is deliberately NOT in this list, matching Python.
var DirMetaFiles = []string{
	"Froster.allfiles.csv",
	".froster.md5sum",
	".froster-restored.md5sum",
	"Where-did-the-files-go.txt",
}

// Effective Python defaults. ConfigManager hardcodes
// min_index_folder_size_gib = 1 and min_index_folder_size_avg_mib = 10
// (they are not read from config.ini in v0.22.0); Archiver.__init__ then
// applies `int(x) if x else 10`, yielding thresholdGB = 1, thresholdMB = 10.
// (That fallback also means a configured value of 0 becomes 10 — a quirk
// that belongs to the config layer, not this package.)
const (
	DefaultThresholdGiB    = 1
	DefaultThresholdMiBAvg = 10
)

// Options control an analysis run. The zero value reproduces froster's
// defaults.
type Options struct {
	// ThresholdGiB is the minimum folder size in GiB (inclusive, compared
	// against the float GiB value like Python's `row[3] >= thresholdGB`).
	// 0 means DefaultThresholdGiB.
	ThresholdGiB int

	// ThresholdMiBAvg is the minimum average file size in MiB (inclusive).
	// 0 means DefaultThresholdMiBAvg.
	ThresholdMiBAvg int

	// Now anchors the days-ago conversion; the zero value means time.Now().
	// Python calls datetime.datetime.now() per row; a fixed Now makes runs
	// deterministic.
	Now time.Time

	// SkipNames lists directory entries ignored by the newest-file
	// atime/mtime scan. nil means DirMetaFiles.
	SkipNames []string

	// LookupUser resolves a UID to a username; any error falls back to the
	// decimal UID string (Python's uid2user KeyError fallback writes the
	// numeric uid). nil means os/user.LookupId.
	LookupUser func(uid int64) (string, error)

	// LookupGroup resolves a GID to a group name, with the same fallback
	// contract as LookupUser. nil means os/user.LookupGroupId.
	LookupGroup func(gid int64) (string, error)

	// Logf receives diagnostic messages (e.g. Python's
	// " Invalid folder path: ..." log line). nil discards them.
	Logf func(format string, args ...any)
}

func (o *Options) normalize() {
	if o.ThresholdGiB == 0 {
		o.ThresholdGiB = DefaultThresholdGiB
	}
	if o.ThresholdMiBAvg == 0 {
		o.ThresholdMiBAvg = DefaultThresholdMiBAvg
	}
	if o.Now.IsZero() {
		o.Now = time.Now()
	}
	if o.SkipNames == nil {
		o.SkipNames = DirMetaFiles
	}
	if o.LookupUser == nil {
		o.LookupUser = lookupUserOS
	}
	if o.LookupGroup == nil {
		o.LookupGroup = lookupGroupOS
	}
	if o.Logf == nil {
		o.Logf = func(string, ...any) {}
	}
}

// Summary aggregates the run statistics that _index_locally reports after
// writing the hotspot CSV.
type Summary struct {
	// NumHotspots is the number of rows written (excluding the header).
	NumHotspots int

	// TotalFolders is the number of directory-rollup rows examined, i.e.
	// Python's len(rows) after the WHERE clause but before thresholds
	// ("Total folders processed").
	TotalFolders int

	// TotalBytes is the summed DirSize of all hotspot rows.
	TotalBytes int64

	// AgedBytes[i] is the summed DirSize of hotspots whose access age in
	// days is strictly greater than DaysAged[i].
	AgedBytes []int64

	// ThresholdGiB and ThresholdMiBAvg echo the effective thresholds used.
	ThresholdGiB    int
	ThresholdMiBAvg int
}

// row is one directory-rollup record surviving the WHERE clause.
type row struct {
	uid, gid       int64
	atime, mtime   int64
	fcount, dirsum int64
	folder         string
	gib, mibAvg    float64
	tib            float64
}

// requiredCols maps the pwalk header names this package consumes.
var requiredCols = []string{"filename", "UID", "GID", "st_atime", "st_mtime", "pw_fcount", "pw_dirsum"}

var zstdMagic = []byte{0x28, 0xB5, 0x2F, 0xFD}

// AnalyzeFile reads a pwalk-format CSV file (plain, or zstd-compressed —
// detected by the frame magic rather than the file extension) and writes
// the hotspot CSV to outputPath, returning the run Summary.
//
// On error the partially written output file is left in place, matching
// Python, where the with-block closes the partial CSV before
// _index_locally's except handler returns False.
func AnalyzeFile(inputPath, outputPath string, opts Options) (*Summary, error) {
	in, err := os.Open(inputPath)
	if err != nil {
		return nil, fmt.Errorf("hotspots: %w", err)
	}
	defer in.Close()

	br := bufio.NewReaderSize(in, 64*1024)
	var r io.Reader = br
	if magic, err := br.Peek(len(zstdMagic)); err == nil && bytes.Equal(magic, zstdMagic) {
		zr, err := zstd.NewReader(br)
		if err != nil {
			return nil, fmt.Errorf("hotspots: opening zstd stream: %w", err)
		}
		defer zr.Close()
		r = zr
	}

	out, err := os.Create(outputPath)
	if err != nil {
		return nil, fmt.Errorf("hotspots: %w", err)
	}
	summary, aerr := Analyze(r, out, opts)
	if cerr := out.Close(); aerr == nil && cerr != nil {
		aerr = fmt.Errorf("hotspots: %w", cerr)
	}
	return summary, aerr
}

// Analyze reads pwalk-format CSV bytes from r (raw pwalk output; the
// ISO-8859-1 -> UTF-8 transcode is applied internally) and writes the
// hotspot CSV to w. It returns the run Summary, or a nil Summary and an
// error if the analysis aborts — including the faithful reproduction of
// Python's OverflowError when a directory with pw_fcount == 0 exceeds the
// GiB threshold (MiBAvg is +Inf there, and Python's int(inf) aborts the
// whole indexing run after the rows already written).
func Analyze(r io.Reader, w io.Writer, opts Options) (*Summary, error) {
	opts.normalize()

	rows, err := readRows(r)
	if err != nil {
		return nil, err
	}

	// ORDER BY pw_dirsum DESC. DuckDB's tie order is unspecified; keep
	// input order for ties.
	sort.SliceStable(rows, func(i, j int) bool { return rows[i].dirsum > rows[j].dirsum })

	bw := bufio.NewWriter(w)
	if err := writeExcelRow(bw, Header); err != nil {
		return nil, err
	}

	summary := &Summary{
		TotalFolders:    len(rows),
		AgedBytes:       make([]int64, len(DaysAged)),
		ThresholdGiB:    opts.ThresholdGiB,
		ThresholdMiBAvg: opts.ThresholdMiBAvg,
	}
	skip := make(map[string]struct{}, len(opts.SkipNames))
	for _, n := range opts.SkipNames {
		skip[n] = struct{}{}
	}

	for _, rw := range rows {
		// Python: `if row[3] >= self.thresholdGB and row[4] >= self.thresholdMB`.
		// Short-circuit order matters: a pw_fcount==0 row (MiBAvg == +Inf)
		// below the GiB threshold is skipped without touching MiBAvg.
		if !(rw.gib >= float64(opts.ThresholdGiB) && rw.mibAvg >= float64(opts.ThresholdMiBAvg)) {
			continue
		}

		atime := newestFileTime(rw.folder, float64(rw.atime), skip, opts.Logf, atimeOf)
		mtime := newestFileTime(rw.folder, float64(rw.mtime), skip, opts.Logf, mtimeOf)
		user := resolveID(rw.uid, opts.LookupUser)
		accd := DaysAgo(atime, opts.Now)
		modd := DaysAgo(mtime, opts.Now)
		gibInt, err := pyInt(rw.gib)
		if err != nil {
			bw.Flush()
			return nil, fmt.Errorf("hotspots: GiB of %q: %w", rw.folder, err)
		}
		mibInt, err := pyInt(rw.mibAvg)
		if err != nil {
			// Python: OverflowError("cannot convert float infinity to
			// integer") from int(row[4]); _index_locally's except handler
			// aborts the run, leaving the partial CSV behind.
			bw.Flush()
			return nil, fmt.Errorf("hotspots: MiBAvg of %q (pw_fcount=%d): %w", rw.folder, rw.fcount, err)
		}
		group := resolveID(rw.gid, opts.LookupGroup)

		out := []string{
			user,
			strconv.Itoa(accd),
			strconv.Itoa(modd),
			strconv.FormatInt(gibInt, 10),
			strconv.FormatInt(mibInt, 10),
			rw.folder,
			group,
			strconv.FormatInt(int64(rw.tib), 10),
			strconv.FormatInt(rw.fcount, 10),
			strconv.FormatInt(rw.dirsum, 10),
		}
		if err := writeExcelRow(bw, out); err != nil {
			return nil, err
		}

		summary.NumHotspots++
		summary.TotalBytes += rw.dirsum
		for i, aged := range DaysAged {
			if accd > aged {
				summary.AgedBytes[i] += rw.dirsum
			}
		}
	}

	if err := bw.Flush(); err != nil {
		return nil, err
	}
	return summary, nil
}

// readRows parses the pwalk CSV (transcoding ISO-8859-1 -> UTF-8 first,
// like the Python iconv step) and returns the directory-rollup rows
// matching `WHERE pw_fcount > -1 AND pw_dirsum > 0`, with the derived
// float columns computed exactly like the DuckDB DOUBLE arithmetic
// (including MiBAvg == +Inf when pw_fcount == 0).
func readRows(r io.Reader) ([]row, error) {
	cr := csv.NewReader(newLatin1Reader(r))
	cr.FieldsPerRecord = -1 // column-count mismatches are skipped, like ignore_errors=1

	head, err := cr.Read()
	if err != nil {
		return nil, fmt.Errorf("hotspots: reading pwalk CSV header: %w", err)
	}
	idx, err := columnIndexes(head)
	if err != nil {
		return nil, err
	}
	ncols := len(head)

	var rows []row
	for {
		rec, err := cr.Read()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			var pe *csv.ParseError
			if errors.As(err, &pe) {
				continue // malformed record: DuckDB ignore_errors=1 drops it
			}
			return nil, fmt.Errorf("hotspots: reading pwalk CSV: %w", err)
		}
		if len(rec) != ncols {
			continue
		}
		fcount, err1 := strconv.ParseInt(rec[idx.fcount], 10, 64)
		dirsum, err2 := strconv.ParseInt(rec[idx.dirsum], 10, 64)
		if err1 != nil || err2 != nil {
			continue
		}
		if !(fcount > -1 && dirsum > 0) {
			continue
		}
		uid, err1 := strconv.ParseInt(rec[idx.uid], 10, 64)
		gid, err2 := strconv.ParseInt(rec[idx.gid], 10, 64)
		atime, err3 := strconv.ParseInt(rec[idx.atime], 10, 64)
		mtime, err4 := strconv.ParseInt(rec[idx.mtime], 10, 64)
		if err1 != nil || err2 != nil || err3 != nil || err4 != nil {
			continue
		}
		rows = append(rows, row{
			uid:    uid,
			gid:    gid,
			atime:  atime,
			mtime:  mtime,
			fcount: fcount,
			dirsum: dirsum,
			folder: rec[idx.folder],
			// DuckDB `/` is DOUBLE division; reproduce the exact operation
			// order: (dirsum/2^20)/fcount, not dirsum/(2^20*fcount).
			gib:    float64(dirsum) / 1073741824.0,
			mibAvg: float64(dirsum) / 1048576.0 / float64(fcount),
			tib:    float64(dirsum) / 1099511627776.0,
		})
	}
	return rows, nil
}

type colIndexes struct {
	folder, uid, gid, atime, mtime, fcount, dirsum int
}

// columnIndexes locates the required pwalk columns by (case-insensitive,
// like DuckDB identifiers) header name.
func columnIndexes(head []string) (colIndexes, error) {
	find := func(name string) (int, error) {
		for i, h := range head {
			if equalFold(h, name) {
				return i, nil
			}
		}
		return 0, fmt.Errorf("hotspots: pwalk CSV header is missing column %q", name)
	}
	var ci colIndexes
	var err error
	targets := []struct {
		name string
		dst  *int
	}{
		{"filename", &ci.folder},
		{"UID", &ci.uid},
		{"GID", &ci.gid},
		{"st_atime", &ci.atime},
		{"st_mtime", &ci.mtime},
		{"pw_fcount", &ci.fcount},
		{"pw_dirsum", &ci.dirsum},
	}
	for _, t := range targets {
		if *t.dst, err = find(t.name); err != nil {
			return ci, err
		}
	}
	return ci, nil
}

// equalFold is strings.EqualFold restricted to ASCII (header names are
// ASCII; avoids surprising Unicode case folding).
func equalFold(a, b string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := 0; i < len(a); i++ {
		ca, cb := a[i], b[i]
		if 'A' <= ca && ca <= 'Z' {
			ca += 'a' - 'A'
		}
		if 'A' <= cb && cb <= 'Z' {
			cb += 'a' - 'A'
		}
		if ca != cb {
			return false
		}
	}
	return true
}
