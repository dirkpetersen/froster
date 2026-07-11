package hotspots

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/user"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/klauspost/compress/zstd"
)

// The golden files in testdata/ were produced by testdata/gen_golden.py,
// which runs the *real* Python froster code (DuckDB query + verbatim
// post-processing loop calling Archiver.uid2user/daysago/etc.) with
// TZ=UTC and datetime.now() pinned to 2026-01-01 00:00:00 UTC.
var fixedNow = time.Unix(1767225600, 0)

func TestMain(m *testing.M) {
	// The goldens were generated with TZ=UTC; DaysAgo uses naive local
	// wall-clock arithmetic like Python's datetime.now().
	time.Local = time.UTC
	os.Exit(m.Run())
}

// goldenOpts pins Now and the uid/gid resolution used when the goldens
// were generated (uid/gid 0 -> "root", anything else unresolvable).
func goldenOpts() Options {
	return Options{
		Now: fixedNow,
		LookupUser: func(uid int64) (string, error) {
			if uid == 0 {
				return "root", nil
			}
			return "", fmt.Errorf("uid not found: %d", uid)
		},
		LookupGroup: func(gid int64) (string, error) {
			if gid == 0 {
				return "root", nil
			}
			return "", fmt.Errorf("gid not found: %d", gid)
		},
	}
}

type goldenSummary struct {
	NumHotspots  int     `json:"numhotspots"`
	TotalBytes   int64   `json:"totalbytes"`
	TotalFolders int     `json:"totalfolders"`
	AgedBytes    []int64 `json:"agedbytes"`
	DaysAged     []int   `json:"daysaged"`
	Error        *string `json:"error"`
	NowEpoch     int64   `json:"now_epoch"`
}

func readGolden(t *testing.T, name string) ([]byte, []byte, goldenSummary) {
	t.Helper()
	fixture, err := os.ReadFile(filepath.Join("testdata", name+".pwalk.csv"))
	if err != nil {
		t.Fatal(err)
	}
	golden, err := os.ReadFile(filepath.Join("testdata", name+".golden.csv"))
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(filepath.Join("testdata", name+".summary.json"))
	if err != nil {
		t.Fatal(err)
	}
	var sum goldenSummary
	if err := json.Unmarshal(raw, &sum); err != nil {
		t.Fatal(err)
	}
	if sum.NowEpoch != fixedNow.Unix() {
		t.Fatalf("golden now_epoch %d != test fixedNow %d", sum.NowEpoch, fixedNow.Unix())
	}
	return fixture, golden, sum
}

func TestGoldenBasic(t *testing.T) {
	fixture, golden, want := readGolden(t, "basic")

	var out bytes.Buffer
	sum, err := Analyze(bytes.NewReader(fixture), &out, goldenOpts())
	if err != nil {
		t.Fatalf("Analyze: %v", err)
	}
	if !bytes.Equal(out.Bytes(), golden) {
		t.Errorf("hotspot CSV differs from Python golden:\ngot:\n%q\nwant:\n%q", out.Bytes(), golden)
	}
	if sum.NumHotspots != want.NumHotspots {
		t.Errorf("NumHotspots = %d, want %d", sum.NumHotspots, want.NumHotspots)
	}
	if sum.TotalBytes != want.TotalBytes {
		t.Errorf("TotalBytes = %d, want %d", sum.TotalBytes, want.TotalBytes)
	}
	if sum.TotalFolders != want.TotalFolders {
		t.Errorf("TotalFolders = %d, want %d", sum.TotalFolders, want.TotalFolders)
	}
	if len(sum.AgedBytes) != len(want.AgedBytes) {
		t.Fatalf("AgedBytes length = %d, want %d", len(sum.AgedBytes), len(want.AgedBytes))
	}
	for i := range want.AgedBytes {
		if sum.AgedBytes[i] != want.AgedBytes[i] {
			t.Errorf("AgedBytes[%d] = %d, want %d", i, sum.AgedBytes[i], want.AgedBytes[i])
		}
	}
	for i, d := range want.DaysAged {
		if DaysAged[i] != d {
			t.Errorf("DaysAged[%d] = %d, want %d", i, DaysAged[i], d)
		}
	}
	if sum.ThresholdGiB != DefaultThresholdGiB || sum.ThresholdMiBAvg != DefaultThresholdMiBAvg {
		t.Errorf("effective thresholds = %d/%d, want %d/%d",
			sum.ThresholdGiB, sum.ThresholdMiBAvg, DefaultThresholdGiB, DefaultThresholdMiBAvg)
	}
}

// TestGoldenFile exercises AnalyzeFile with both a plain CSV and a
// zstd-compressed copy (detected by magic bytes, not extension).
func TestGoldenFile(t *testing.T) {
	fixture, golden, want := readGolden(t, "basic")
	dir := t.TempDir()

	plain := filepath.Join(dir, "in.csv")
	if err := os.WriteFile(plain, fixture, 0o644); err != nil {
		t.Fatal(err)
	}

	compressed := filepath.Join(dir, "in.csv.zst")
	f, err := os.Create(compressed)
	if err != nil {
		t.Fatal(err)
	}
	zw, err := zstd.NewWriter(f)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := zw.Write(fixture); err != nil {
		t.Fatal(err)
	}
	if err := zw.Close(); err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}

	for _, input := range []string{plain, compressed} {
		outPath := filepath.Join(dir, filepath.Base(input)+".hotspots.csv")
		sum, err := AnalyzeFile(input, outPath, goldenOpts())
		if err != nil {
			t.Fatalf("AnalyzeFile(%s): %v", input, err)
		}
		got, err := os.ReadFile(outPath)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(got, golden) {
			t.Errorf("%s: hotspot CSV differs from golden", input)
		}
		if sum.NumHotspots != want.NumHotspots || sum.TotalBytes != want.TotalBytes {
			t.Errorf("%s: summary = %+v, want %+v", input, sum, want)
		}
	}
}

// TestZeroFilesAbort reproduces the Python OverflowError: a directory with
// pw_fcount == 0 over the GiB threshold has MiBAvg == +Inf; int(inf)
// aborts the whole run after the rows already written (partial CSV).
func TestZeroFilesAbort(t *testing.T) {
	fixture, golden, want := readGolden(t, "zerofiles")
	if want.Error == nil || !strings.Contains(*want.Error, "infinity") {
		t.Fatalf("zerofiles golden should record an OverflowError, got %v", want.Error)
	}

	var out bytes.Buffer
	sum, err := Analyze(bytes.NewReader(fixture), &out, goldenOpts())
	if err == nil {
		t.Fatal("Analyze should fail on pw_fcount=0 row over the GiB threshold")
	}
	if !strings.Contains(err.Error(), "infinity") {
		t.Errorf("error = %v, want mention of infinity", err)
	}
	if sum != nil {
		t.Errorf("summary should be nil on abort (Python returns False), got %+v", sum)
	}
	if !bytes.Equal(out.Bytes(), golden) {
		t.Errorf("partial CSV differs from Python golden:\ngot:\n%q\nwant:\n%q", out.Bytes(), golden)
	}
}

func pwalkHeader() string {
	return `inode,parent-inode,directory-depth,"filename","fileExtension",UID,GID,st_size,st_dev,st_blocks,st_nlink,"st_mode",st_atime,st_mtime,st_ctime,pw_fcount,pw_dirsum` + "\n"
}

func dirRow(folder string, uid, gid, atime, mtime, fcount, dirsum int64) string {
	return fmt.Sprintf(`42,1,1,"%s","",%d,%d,4096,64,8,2,"0040755",%d,%d,%d,%d,%d`+"\n",
		folder, uid, gid, atime, mtime, mtime, fcount, dirsum)
}

// TestLiveNewestTimes verifies the newest-file atime/mtime scan against a
// real directory: symlinks followed, subdirectories ignored, dirmetafiles
// skipped — but Froster.smallfiles.tar NOT skipped (Python quirk) — and
// the CSV times superseded by the live values.
//
// Some environments (observed on WSL2) run a background scanner that reads
// freshly created files a few milliseconds after creation, clobbering
// their atimes; the test therefore re-applies the intended times after a
// settle delay and retries a few times before failing.
func TestLiveNewestTimes(t *testing.T) {
	now := time.Now()
	dir := t.TempDir()
	target := t.TempDir() // symlink target outside the scanned folder

	type stamped struct {
		path         string
		atime, mtime time.Time
	}
	var files []stamped
	mkfile := func(path string, atime, mtime time.Time) {
		t.Helper()
		if err := os.WriteFile(path, []byte("x"), 0o644); err != nil {
			t.Fatal(err)
		}
		files = append(files, stamped{path, atime, mtime})
	}
	ago := func(days int) time.Time { return now.Add(-time.Duration(days)*24*time.Hour - time.Hour) }

	mkfile(filepath.Join(dir, "file1"), ago(5), ago(7))
	mkfile(filepath.Join(dir, "file2"), ago(200), ago(3))
	// Python's dirmetafiles list does NOT include the smallfiles tar, so it
	// participates in the scan.
	mkfile(filepath.Join(dir, "Froster.smallfiles.tar"), ago(2), ago(9))
	// Skipped metadata file: would otherwise dominate both scans.
	mkfile(filepath.Join(dir, "Froster.allfiles.csv"), ago(0), ago(0))
	// Symlink to a file outside the folder: followed (newest atime).
	mkfile(filepath.Join(target, "linked"), ago(1), ago(8))
	if err := os.Symlink(filepath.Join(target, "linked"), filepath.Join(dir, "link")); err != nil {
		t.Fatal(err)
	}
	// Broken symlink and subdirectory: ignored.
	if err := os.Symlink(filepath.Join(target, "gone"), filepath.Join(dir, "broken")); err != nil {
		t.Fatal(err)
	}
	sub := filepath.Join(dir, "subdir")
	if err := os.Mkdir(sub, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Chtimes(sub, ago(0), ago(0)); err != nil {
		t.Fatal(err)
	}

	csvAtime := now.Add(-100 * 24 * time.Hour).Unix()
	input := pwalkHeader() + dirRow(dir, 0, 0, csvAtime, csvAtime, 2, 2<<30)
	opts := goldenOpts()
	opts.Now = now

	var accd, modd string
	for attempt := 0; attempt < 5; attempt++ {
		if attempt > 0 {
			time.Sleep(time.Duration(attempt) * 100 * time.Millisecond)
		}
		for _, f := range files {
			if err := os.Chtimes(f.path, f.atime, f.mtime); err != nil {
				t.Fatal(err)
			}
		}
		var out bytes.Buffer
		sum, err := Analyze(strings.NewReader(input), &out, opts)
		if err != nil {
			t.Fatalf("Analyze: %v", err)
		}
		if sum.NumHotspots != 1 {
			t.Fatalf("NumHotspots = %d, want 1", sum.NumHotspots)
		}
		fields := strings.Split(strings.Split(out.String(), "\r\n")[1], ",")
		accd, modd = fields[1], fields[2]
		if accd == "1" && modd == "3" {
			break
		}
	}
	// Newest atime: symlink target at 1 day (not the CSV's 100 days).
	if accd != "1" {
		t.Errorf("AccD = %s, want 1 (live symlink-target atime; environment may clobber atimes)", accd)
	}
	// Newest mtime: file2 at 3 days.
	if modd != "3" {
		t.Errorf("ModD = %s, want 3 (live file2 mtime)", modd)
	}
}

func TestNewestFileTimeFallbacks(t *testing.T) {
	var logged []string
	logf := func(format string, args ...any) {
		logged = append(logged, fmt.Sprintf(format, args...))
	}

	// Empty and non-existent paths: logged, fallback returned.
	if got := NewestFileAtime("", 42, nil, logf); got != 42 {
		t.Errorf("empty path: got %v, want fallback 42", got)
	}
	if got := NewestFileAtime("/nonexistent/froster-test", 43, nil, logf); got != 43 {
		t.Errorf("nonexistent path: got %v, want fallback 43", got)
	}
	if len(logged) != 2 || !strings.Contains(logged[0], "Invalid folder path") {
		t.Errorf("expected two 'Invalid folder path' log lines, got %q", logged)
	}

	// Directory with no regular files: fallback.
	empty := t.TempDir()
	if got := NewestFileMtime(empty, 44, nil, nil); got != 44 {
		t.Errorf("empty dir: got %v, want fallback 44", got)
	}

	// Path exists but is a file: os.path.exists is true, listdir raises,
	// Python's except returns the fallback.
	file := filepath.Join(t.TempDir(), "plainfile")
	if err := os.WriteFile(file, []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	if got := NewestFileAtime(file, 45, nil, nil); got != 45 {
		t.Errorf("file-as-folder: got %v, want fallback 45", got)
	}
}

func TestDaysAgo(t *testing.T) {
	now := fixedNow
	cases := []struct {
		name string
		t    float64
		want int
	}{
		{"zero epoch quirk", 0, 0},
		{"NaN (Python None)", nanFloat(), 0},
		{"just under a day", float64(now.Unix() - 86399), 0},
		{"exactly a day", float64(now.Unix() - 86400), 1},
		{"just over a day", float64(now.Unix() - 86401), 1},
		{"10 days", float64(now.Unix() - 10*86400), 10},
		// timedelta.days floors toward -inf: future timestamps go negative.
		{"1 hour in the future", float64(now.Unix() + 3600), -1},
		{"25 hours in the future", float64(now.Unix() + 90000), -2},
		// Out of Python's datetime range: fromtimestamp raises, daysago -> 0.
		{"absurdly large", 1e18, 0},
		{"absurdly negative", -1e18, 0},
	}
	for _, c := range cases {
		if got := DaysAgo(c.t, now); got != c.want {
			t.Errorf("%s: DaysAgo(%v) = %d, want %d", c.name, c.t, got, c.want)
		}
	}
}

func nanFloat() float64 {
	f := 0.0
	return f / f
}

func TestIDFallbacks(t *testing.T) {
	if got := UIDToUser(4200001); got != "4200001" {
		t.Errorf("UIDToUser(4200001) = %q, want numeric fallback", got)
	}
	if got := GIDToGroup(4200002); got != "4200002" {
		t.Errorf("GIDToGroup(4200002) = %q, want numeric fallback", got)
	}
	if u, err := user.LookupId("0"); err == nil {
		if got := UIDToUser(0); got != u.Username {
			t.Errorf("UIDToUser(0) = %q, want %q", got, u.Username)
		}
	}
}

// TestLatin1Reader checks the full byte range against Python's
// bytes.decode('iso-8859-1').encode('utf-8') (which string(rune(b))
// reproduces per byte), plus tiny destination buffers.
func TestLatin1Reader(t *testing.T) {
	in := make([]byte, 256)
	var want []byte
	for i := 0; i < 256; i++ {
		in[i] = byte(i)
		want = append(want, []byte(string(rune(i)))...)
	}
	got, err := io.ReadAll(newLatin1Reader(bytes.NewReader(in)))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, want) {
		t.Errorf("latin-1 transcode mismatch:\ngot  %x\nwant %x", got, want)
	}

	// Two-byte destination buffer forces the split-sequence path.
	r := newLatin1Reader(bytes.NewReader(in))
	var chunked []byte
	buf := make([]byte, 2)
	for {
		n, err := r.Read(buf)
		chunked = append(chunked, buf[:n]...)
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
	}
	if !bytes.Equal(chunked, want) {
		t.Errorf("chunked latin-1 transcode mismatch")
	}
}

// TestExcelQuoting pins the writer to Python csv excel-dialect behavior
// (observed output of csv.writer for the same fields).
func TestExcelQuoting(t *testing.T) {
	var buf bytes.Buffer
	bw := bufio.NewWriter(&buf)
	err := writeExcelRow(bw, []string{
		"plain", "has,comma", `has"quote`, " leadspace", "trailspace ",
		"new\nline", "", "tab\there",
	})
	if err != nil {
		t.Fatal(err)
	}
	bw.Flush()
	want := "plain,\"has,comma\",\"has\"\"quote\", leadspace,trailspace ,\"new\nline\",,tab\there\r\n"
	if buf.String() != want {
		t.Errorf("excel row = %q, want %q", buf.String(), want)
	}
}

// TestMalformedRowsSkipped emulates DuckDB's ignore_errors=1: rows with a
// wrong column count or unparseable numerics are dropped silently.
func TestMalformedRowsSkipped(t *testing.T) {
	input := pwalkHeader() +
		dirRow("/nope/good", 0, 0, fixedNow.Unix()-86400, fixedNow.Unix()-86400, 4, 4<<30) +
		"1,2,3\n" + // wrong column count
		`42,1,1,"/nope/badnum","",0,0,4096,64,8,2,"0040755",abc,0,0,3,3221225472` + "\n" + // bad st_atime
		`42,1,1,"/nope/badfc","",0,0,4096,64,8,2,"0040755",0,0,0,xyz,3221225472` + "\n" // bad pw_fcount

	var out bytes.Buffer
	sum, err := Analyze(strings.NewReader(input), &out, goldenOpts())
	if err != nil {
		t.Fatalf("Analyze: %v", err)
	}
	if sum.TotalFolders != 1 || sum.NumHotspots != 1 {
		t.Errorf("TotalFolders/NumHotspots = %d/%d, want 1/1", sum.TotalFolders, sum.NumHotspots)
	}
	if !strings.Contains(out.String(), "/nope/good") {
		t.Errorf("expected the good row in output, got %q", out.String())
	}
}

func TestMissingColumn(t *testing.T) {
	input := "inode,filename,pw_fcount\n" + `1,"/x",3` + "\n"
	if _, err := Analyze(strings.NewReader(input), io.Discard, goldenOpts()); err == nil {
		t.Fatal("expected error for missing pwalk columns")
	}
}

// TestThresholdEdges verifies the inclusive (>=) comparisons at non-default
// thresholds.
func TestThresholdEdges(t *testing.T) {
	atime := fixedNow.Unix() - 86400
	input := pwalkHeader() +
		dirRow("/nope/at-gib", 0, 0, atime, atime, 100, 50<<30) + // 50.0 GiB, 512 MiBAvg
		dirRow("/nope/under-gib", 0, 0, atime, atime, 100, 50<<30-1) + // just under
		dirRow("/nope/at-mib", 0, 0, atime, atime, 1024, 50<<30) + // MiBAvg exactly 50.0
		dirRow("/nope/under-mib", 0, 0, atime, atime, 1025, 50<<30) // just under

	opts := goldenOpts()
	opts.ThresholdGiB = 50
	opts.ThresholdMiBAvg = 50
	var out bytes.Buffer
	sum, err := Analyze(strings.NewReader(input), &out, opts)
	if err != nil {
		t.Fatalf("Analyze: %v", err)
	}
	if sum.NumHotspots != 2 {
		t.Errorf("NumHotspots = %d, want 2\noutput:\n%s", sum.NumHotspots, out.String())
	}
	for _, want := range []string{"/nope/at-gib", "/nope/at-mib"} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("expected %s in output", want)
		}
	}
	for _, notWant := range []string{"/nope/under-gib", "/nope/under-mib"} {
		if strings.Contains(out.String(), notWant) {
			t.Errorf("did not expect %s in output", notWant)
		}
	}
	if sum.TotalFolders != 4 {
		t.Errorf("TotalFolders = %d, want 4", sum.TotalFolders)
	}
}

// TestSortStability: equal pw_dirsum keeps input order (DuckDB's tie order
// is unspecified; we pin input order).
func TestSortStability(t *testing.T) {
	atime := fixedNow.Unix() - 86400
	input := pwalkHeader() +
		dirRow("/nope/small", 0, 0, atime, atime, 2, 2<<30) +
		dirRow("/nope/tie-a", 0, 0, atime, atime, 4, 4<<30) +
		dirRow("/nope/tie-b", 0, 0, atime, atime, 4, 4<<30)

	var out bytes.Buffer
	if _, err := Analyze(strings.NewReader(input), &out, goldenOpts()); err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimRight(out.String(), "\r\n"), "\r\n")
	if len(lines) != 4 {
		t.Fatalf("expected header + 3 rows, got %d lines", len(lines))
	}
	wantOrder := []string{"/nope/tie-a", "/nope/tie-b", "/nope/small"}
	for i, want := range wantOrder {
		if !strings.Contains(lines[i+1], want) {
			t.Errorf("row %d = %q, want folder %s", i+1, lines[i+1], want)
		}
	}
}
