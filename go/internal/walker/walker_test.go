package walker

import (
	"bytes"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"github.com/klauspost/compress/zstd"
	"golang.org/x/sys/unix"
)

// walkSorted runs Walk and returns the header (if any) plus the sorted
// data rows, since row order is intentionally nondeterministic.
func walkSorted(t *testing.T, root string, opts Options) (header string, rows []string, sum Summary) {
	t.Helper()
	var buf bytes.Buffer
	sum, err := Walk(root, &buf, opts)
	if err != nil {
		t.Fatalf("Walk(%q): %v", root, err)
	}
	lines := strings.Split(strings.TrimSuffix(buf.String(), "\n"), "\n")
	if opts.Header {
		header, lines = lines[0], lines[1:]
	}
	if len(lines) == 1 && lines[0] == "" {
		lines = nil
	}
	sort.Strings(lines)
	return header, lines, sum
}

// rowFor returns the single row whose quoted filename field matches path.
func rowFor(t *testing.T, rows []string, path string) string {
	t.Helper()
	needle := `,"` + strings.ReplaceAll(path, `"`, `""`) + `","`
	var found []string
	for _, r := range rows {
		if strings.Contains(r, needle) {
			found = append(found, r)
		}
	}
	if len(found) != 1 {
		t.Fatalf("expected exactly 1 row for %q, got %d:\n%s", path, len(found), strings.Join(found, "\n"))
	}
	return found[0]
}

// field returns the i-th CSV field of a pwalk row. Quoted fields never
// contain commas in these tests' fixtures except where noted.
func fields(row string) []string {
	return splitPwalkRow(row)
}

// splitPwalkRow splits a pwalk CSV row into its 17 fields, honoring the
// quoting of the filename, extension, and mode fields.
func splitPwalkRow(row string) []string {
	var out []string
	var cur strings.Builder
	inQuote := false
	for i := 0; i < len(row); i++ {
		c := row[i]
		switch {
		case c == '"':
			if inQuote && i+1 < len(row) && row[i+1] == '"' {
				cur.WriteByte('"')
				i++
			} else {
				inQuote = !inQuote
			}
		case c == ',' && !inQuote:
			out = append(out, cur.String())
			cur.Reset()
		default:
			cur.WriteByte(c)
		}
	}
	out = append(out, cur.String())
	return out
}

const (
	fldInode = iota
	fldParentInode
	fldDepth
	fldFilename
	fldExt
	fldUID
	fldGID
	fldSize
	fldDev
	fldBlocks
	fldNlink
	fldMode
	fldAtime
	fldMtime
	fldCtime
	fldFcount
	fldDirsum
)

func mustWrite(t *testing.T, path string, size int) {
	t.Helper()
	if err := os.WriteFile(path, bytes.Repeat([]byte{'x'}, size), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestHeaderLine(t *testing.T) {
	want := `inode,parent-inode,directory-depth,"filename","fileExtension",UID,GID,st_size,st_dev,st_blocks,st_nlink,"st_mode",st_atime,st_mtime,st_ctime,pw_fcount,pw_dirsum` + "\n"
	if Header != want {
		t.Errorf("Header constant mismatch:\ngot  %q\nwant %q", Header, want)
	}
	dir := t.TempDir()
	var buf bytes.Buffer
	if _, err := Walk(dir, &buf, Options{Header: true}); err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(buf.String(), want) {
		t.Errorf("output does not start with header: %q", buf.String())
	}
}

func TestBasicTreeSemantics(t *testing.T) {
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, "a", "b"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(root, "empty"), 0o755); err != nil {
		t.Fatal(err)
	}
	mustWrite(t, filepath.Join(root, "top.txt"), 100)
	mustWrite(t, filepath.Join(root, "a", "mid.dat"), 200)
	mustWrite(t, filepath.Join(root, "a", "b", "deep.log"), 300)

	_, rows, sum := walkSorted(t, root, Options{Header: true})

	// 4 directory rows (root, a, a/b, empty) + 3 file rows.
	if sum.DirRows != 4 || sum.FileRows != 3 {
		t.Errorf("summary rows: got dirs=%d files=%d, want 4/3", sum.DirRows, sum.FileRows)
	}
	if len(rows) != 7 {
		t.Fatalf("got %d rows, want 7:\n%s", len(rows), strings.Join(rows, "\n"))
	}

	rootRow := fields(rowFor(t, rows, root))
	if rootRow[fldDepth] != "-1" || rootRow[fldParentInode] != "0" {
		t.Errorf("root row depth/pino = %s/%s, want -1/0", rootRow[fldDepth], rootRow[fldParentInode])
	}
	// Root contains a, empty, top.txt.
	if rootRow[fldFcount] != "3" {
		t.Errorf("root pw_fcount = %s, want 3", rootRow[fldFcount])
	}

	top := fields(rowFor(t, rows, filepath.Join(root, "top.txt")))
	if top[fldDepth] != "0" || top[fldFcount] != "-1" || top[fldDirsum] != "0" {
		t.Errorf("top.txt depth/fcount/dirsum = %s/%s/%s, want 0/-1/0",
			top[fldDepth], top[fldFcount], top[fldDirsum])
	}
	if top[fldParentInode] != rootRow[fldInode] {
		t.Errorf("top.txt parent inode %s != root inode %s", top[fldParentInode], rootRow[fldInode])
	}
	if top[fldExt] != "txt" || top[fldSize] != "100" {
		t.Errorf("top.txt ext/size = %q/%s, want txt/100", top[fldExt], top[fldSize])
	}
	if !strings.HasSuffix(rowFor(t, rows, filepath.Join(root, "top.txt")), ",-1,0") {
		t.Error("file row must end in ,-1,0 (froster grep filter contract)")
	}

	a := fields(rowFor(t, rows, filepath.Join(root, "a")))
	if a[fldDepth] != "0" || a[fldExt] != "" || a[fldFcount] != "2" {
		t.Errorf("dir a depth/ext/fcount = %s/%q/%s, want 0//2", a[fldDepth], a[fldExt], a[fldFcount])
	}
	b := fields(rowFor(t, rows, filepath.Join(root, "a", "b")))
	if b[fldDepth] != "1" || b[fldParentInode] != a[fldInode] {
		t.Errorf("dir a/b depth=%s pino=%s, want 1/%s", b[fldDepth], b[fldParentInode], a[fldInode])
	}
	deep := fields(rowFor(t, rows, filepath.Join(root, "a", "b", "deep.log")))
	if deep[fldDepth] != "2" {
		t.Errorf("deep.log depth = %s, want 2", deep[fldDepth])
	}
	empty := fields(rowFor(t, rows, filepath.Join(root, "empty")))
	if empty[fldFcount] != "0" || empty[fldDirsum] != "0" {
		t.Errorf("empty dir fcount/dirsum = %s/%s, want 0/0", empty[fldFcount], empty[fldDirsum])
	}

	// pw_dirsum of a = size of mid.dat + st_size of subdir b.
	var bStat unix.Stat_t
	if err := unix.Lstat(filepath.Join(root, "a", "b"), &bStat); err != nil {
		t.Fatal(err)
	}
	wantSum := fmt.Sprint(200 + bStat.Size)
	if a[fldDirsum] != wantSum {
		t.Errorf("dir a pw_dirsum = %s, want %s", a[fldDirsum], wantSum)
	}
}

func TestQuotingEdgeCases(t *testing.T) {
	root := t.TempDir()
	mustWrite(t, filepath.Join(root, `quo"te.txt`), 1)
	mustWrite(t, filepath.Join(root, "com,ma.csv"), 1)
	mustWrite(t, filepath.Join(root, "bad\nname\tfile.txt"), 1)
	// Latin-1 (non-UTF-8) byte in the name: caf\xe9.txt.
	latin1 := string([]byte{'c', 'a', 'f', 0xe9, '.', 't', 'x', 't'})
	mustWrite(t, filepath.Join(root, latin1), 1)

	_, rows, sum := walkSorted(t, root, Options{})

	// Quote doubled inside the always-quoted field.
	q := rowFor(t, rows, filepath.Join(root, `quo"te.txt`))
	if !strings.Contains(q, `"`+root+`/quo""te.txt"`) {
		t.Errorf("quote not doubled: %s", q)
	}
	// Comma preserved verbatim inside quotes.
	c := rowFor(t, rows, filepath.Join(root, "com,ma.csv"))
	if !strings.Contains(c, `"`+root+`/com,ma.csv"`) {
		t.Errorf("comma mangled: %s", c)
	}
	// Control bytes stripped, remaining bytes joined.
	b := rowFor(t, rows, filepath.Join(root, "badnamefile.txt"))
	if !strings.Contains(b, `"`+root+`/badnamefile.txt"`) {
		t.Errorf("control bytes not stripped: %s", b)
	}
	if sum.BadNames != 1 {
		t.Errorf("BadNames = %d, want 1", sum.BadNames)
	}
	// Non-UTF-8 byte passes through raw.
	l := rowFor(t, rows, filepath.Join(root, latin1))
	if !strings.Contains(l, "/caf\xe9.txt\",\"txt\"") {
		t.Errorf("latin-1 byte not passed through raw: %q", l)
	}
}

func TestExtensionRules(t *testing.T) {
	cases := []struct{ name, want string }{
		{"plain.txt", "txt"},
		{"noext", ""},
		{".bashrc", ""},          // leading dot is not an extension
		{"..leading.txt", "txt"}, // scan starts at offset 1
		{"..leading", "leading"}, // dot at offset 1 counts
		{"multi.part.tar.gz", "gz"},
		{"trailing.", ""}, // deviation: C pwalk emits stack garbage here
		{"a", ""},
		{".", ""},
		{"a.", ""},
		{"a.b", "b"},
	}
	for _, c := range cases {
		if got := fileExt(c.name); got != c.want {
			t.Errorf("fileExt(%q) = %q, want %q", c.name, got, c.want)
		}
	}
}

func TestSymlinkHardlinkFifo(t *testing.T) {
	root := t.TempDir()
	mustWrite(t, filepath.Join(root, "plain.txt"), 1234)
	if err := os.Link(filepath.Join(root, "plain.txt"), filepath.Join(root, "hard.txt")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("plain.txt", filepath.Join(root, "link")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("/nonexistent/target.foo", filepath.Join(root, "dangling.lnk")); err != nil {
		t.Fatal(err)
	}
	if err := unix.Mkfifo(filepath.Join(root, "pipe.fifo"), 0o644); err != nil {
		t.Fatal(err)
	}

	_, rows, _ := walkSorted(t, root, Options{})

	plain := fields(rowFor(t, rows, filepath.Join(root, "plain.txt")))
	hard := fields(rowFor(t, rows, filepath.Join(root, "hard.txt")))
	if plain[fldInode] != hard[fldInode] {
		t.Errorf("hardlink inode mismatch: %s vs %s", plain[fldInode], hard[fldInode])
	}
	if plain[fldNlink] != "2" || hard[fldNlink] != "2" {
		t.Errorf("nlink = %s/%s, want 2/2", plain[fldNlink], hard[fldNlink])
	}

	link := fields(rowFor(t, rows, filepath.Join(root, "link")))
	if link[fldMode] != "0120777" {
		t.Errorf("symlink mode = %q, want 0120777", link[fldMode])
	}
	// Symlinks are lstat'd, never followed: size is the target string length.
	if link[fldSize] != "9" { // len("plain.txt")
		t.Errorf("symlink size = %s, want 9", link[fldSize])
	}
	dangling := fields(rowFor(t, rows, filepath.Join(root, "dangling.lnk")))
	if dangling[fldExt] != "lnk" || dangling[fldFcount] != "-1" {
		t.Errorf("dangling symlink ext/fcount = %q/%s", dangling[fldExt], dangling[fldFcount])
	}

	fifo := fields(rowFor(t, rows, filepath.Join(root, "pipe.fifo")))
	if fifo[fldMode] != "0010644" {
		t.Errorf("fifo mode = %q, want 0010644", fifo[fldMode])
	}
}

func TestSnapshotFiltering(t *testing.T) {
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, ".snapshot"), 0o755); err != nil {
		t.Fatal(err)
	}
	mustWrite(t, filepath.Join(root, ".snapshot", "inside.txt"), 50)
	mustWrite(t, filepath.Join(root, "visible.txt"), 100)

	// With NoSnap: no .snapshot rows, but the parent rollup still counts
	// the .snapshot entry and its inode size (C pwalk quirk).
	_, rows, _ := walkSorted(t, root, Options{NoSnap: true})
	for _, r := range rows {
		if strings.Contains(r, ".snapshot") {
			t.Errorf("NoSnap leaked row: %s", r)
		}
	}
	var snapStat unix.Stat_t
	if err := unix.Lstat(filepath.Join(root, ".snapshot"), &snapStat); err != nil {
		t.Fatal(err)
	}
	rootRow := fields(rowFor(t, rows, root))
	if rootRow[fldFcount] != "2" {
		t.Errorf("NoSnap root fcount = %s, want 2 (snapshot still counted)", rootRow[fldFcount])
	}
	if want := fmt.Sprint(100 + snapStat.Size); rootRow[fldDirsum] != want {
		t.Errorf("NoSnap root dirsum = %s, want %s (snapshot inode size still counted)",
			rootRow[fldDirsum], want)
	}
	if len(rows) != 2 { // root dir row + visible.txt
		t.Errorf("NoSnap rows = %d, want 2:\n%s", len(rows), strings.Join(rows, "\n"))
	}

	// Without NoSnap the .snapshot tree is fully reported.
	_, rows, _ = walkSorted(t, root, Options{})
	rowFor(t, rows, filepath.Join(root, ".snapshot"))
	rowFor(t, rows, filepath.Join(root, ".snapshot", "inside.txt"))
	if len(rows) != 4 {
		t.Errorf("default rows = %d, want 4", len(rows))
	}
}

func TestPermissionErrorsNonFatal(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("running as root; permission errors cannot be provoked")
	}
	root := t.TempDir()
	locked := filepath.Join(root, "locked")
	if err := os.Mkdir(locked, 0o755); err != nil {
		t.Fatal(err)
	}
	mustWrite(t, filepath.Join(locked, "unreachable.txt"), 10)
	if err := os.Chmod(locked, 0); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Chmod(locked, 0o755) })
	mustWrite(t, filepath.Join(root, "ok.txt"), 10)

	_, rows, sum := walkSorted(t, root, Options{})
	if sum.OpenErrors != 1 {
		t.Errorf("OpenErrors = %d, want 1", sum.OpenErrors)
	}
	if len(sum.Errs) == 0 {
		t.Error("expected recorded error message")
	}
	// The unreadable directory gets no row at all (C pwalk behavior)...
	for _, r := range rows {
		if strings.Contains(r, "locked") {
			t.Errorf("unexpected row for unreadable dir: %s", r)
		}
	}
	// ...but is still counted in the parent rollup.
	rootRow := fields(rowFor(t, rows, root))
	if rootRow[fldFcount] != "2" {
		t.Errorf("root fcount = %s, want 2", rootRow[fldFcount])
	}
}

func TestZstdRoundTrip(t *testing.T) {
	root := t.TempDir()
	mustWrite(t, filepath.Join(root, "a.txt"), 100)
	mustWrite(t, filepath.Join(root, "b.txt"), 200)
	if err := os.Mkdir(filepath.Join(root, "sub"), 0o755); err != nil {
		t.Fatal(err)
	}
	mustWrite(t, filepath.Join(root, "sub", "c.txt"), 300)

	var plain bytes.Buffer
	if _, err := Walk(root, &plain, Options{Header: true, Workers: 1}); err != nil {
		t.Fatal(err)
	}
	var compressed bytes.Buffer
	if _, err := Walk(root, &compressed, Options{Header: true, Workers: 1, Zstd: true}); err != nil {
		t.Fatal(err)
	}

	dec, err := zstd.NewReader(&compressed)
	if err != nil {
		t.Fatal(err)
	}
	defer dec.Close()
	round, err := io.ReadAll(dec)
	if err != nil {
		t.Fatalf("decompressing: %v", err)
	}

	// The two walks read the same live tree back to back, so directory
	// st_atime can legitimately differ between them (relatime updates on
	// the first walk's readdir). Blank the st_atime column (index 12; the
	// filenames in this fixture contain no commas) — atime fidelity is
	// covered by the golden comparison against C pwalk.
	sortLines := func(b []byte) []string {
		l := strings.Split(strings.TrimSuffix(string(b), "\n"), "\n")
		for i, ln := range l {
			f := strings.Split(ln, ",")
			if len(f) == 17 {
				f[12] = "-"
				l[i] = strings.Join(f, ",")
			}
		}
		sort.Strings(l)
		return l
	}
	got, want := sortLines(round), sortLines(plain.Bytes())
	if len(got) != len(want) {
		t.Fatalf("row count mismatch: %d vs %d", len(got), len(want))
	}
	for i := range got {
		if got[i] != want[i] {
			t.Errorf("row %d mismatch:\nzstd:  %s\nplain: %s", i, got[i], want[i])
		}
	}
}

func TestWalkToFileZstSuffix(t *testing.T) {
	root := t.TempDir()
	mustWrite(t, filepath.Join(root, "a.txt"), 10)
	out := filepath.Join(t.TempDir(), "out.csv.zst")
	if _, err := WalkToFile(root, out, Options{Header: true}); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	// zstd magic number.
	if len(raw) < 4 || raw[0] != 0x28 || raw[1] != 0xb5 || raw[2] != 0x2f || raw[3] != 0xfd {
		t.Fatalf("output is not zstd-framed: % x", raw[:min(8, len(raw))])
	}
	dec, err := zstd.NewReader(bytes.NewReader(raw))
	if err != nil {
		t.Fatal(err)
	}
	defer dec.Close()
	content, err := io.ReadAll(dec)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(string(content), Header) {
		t.Error("decompressed output missing header")
	}
}

func TestRootLstatFailure(t *testing.T) {
	if _, err := Walk(filepath.Join(t.TempDir(), "does-not-exist"), io.Discard, Options{}); err == nil {
		t.Error("expected error for nonexistent root")
	}
}

func TestDirsHaveNoExtension(t *testing.T) {
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, "dir.with.ext"), 0o755); err != nil {
		t.Fatal(err)
	}
	_, rows, _ := walkSorted(t, root, Options{})
	d := fields(rowFor(t, rows, filepath.Join(root, "dir.with.ext")))
	if d[fldExt] != "" {
		t.Errorf("directory extension = %q, want empty (C pwalk never emits one)", d[fldExt])
	}
}
