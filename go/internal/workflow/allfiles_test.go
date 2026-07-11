package workflow

import (
	"archive/tar"
	"encoding/csv"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

// tarMembers lists the member names of a tar file.
func tarMembers(t *testing.T, tarPath string) []string {
	t.Helper()
	f, err := os.Open(tarPath)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	tr := tar.NewReader(f)
	var names []string
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		names = append(names, hdr.Name)
	}
	sort.Strings(names)
	return names
}

// readCSV parses a CSV file into records.
func readCSV(t *testing.T, path string) [][]string {
	t.Helper()
	f, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	recs, err := r.ReadAll()
	if err != nil {
		t.Fatal(err)
	}
	return recs
}

func TestGenAllfilesAndTarThresholdAndFormat(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()

	writeBytes(t, filepath.Join(dir, "exactly_1mib.dat"), 1024*1024)      // NOT tarred (strict <)
	writeBytes(t, filepath.Join(dir, "just_under_1mib.dat"), 1024*1024-1) // tarred
	writeBytes(t, filepath.Join(dir, "big.dat"), 2*1024*1024)             // NOT tarred
	writeFile(t, filepath.Join(dir, "small_report.txt"), "small stuff")   // tarred
	writeFile(t, filepath.Join(dir, "values,comma.csv"), "a,b")           // tarred, comma in name
	writeFile(t, filepath.Join(dir, `quote"file.txt`), "q")               // tarred, quote in name
	writeFile(t, filepath.Join(dir, "file with spaces.txt"), "sp")        // tarred
	if err := os.Symlink("big.dat", filepath.Join(dir, "link.dat")); err != nil {
		t.Fatal(err)
	}
	// Subdirectory contents must be ignored entirely.
	writeFile(t, filepath.Join(dir, "sub", "nested.txt"), "nested")

	if err := w.genAllfilesAndTar(dir, 1024, true); err != nil {
		t.Fatalf("genAllfilesAndTar: %v", err)
	}

	// Tarred members: everything strictly below 1 MiB plus the symlink.
	wantMembers := []string{"file with spaces.txt", "just_under_1mib.dat", "link.dat", `quote"file.txt`, "small_report.txt", "values,comma.csv"}
	got := tarMembers(t, filepath.Join(dir, SmallfilesTarFileName))
	if strings.Join(got, "|") != strings.Join(wantMembers, "|") {
		t.Errorf("tar members = %v, want %v", got, wantMembers)
	}

	// Originals of tarred files are deleted; boundary and big files stay.
	for _, name := range wantMembers {
		mustNotExist(t, filepath.Join(dir, name))
	}
	mustExist(t, filepath.Join(dir, "exactly_1mib.dat"))
	mustExist(t, filepath.Join(dir, "big.dat"))
	mustExist(t, filepath.Join(dir, "sub", "nested.txt"))

	// CSV: header + one row per top-level file (not the subdir), CRLF.
	raw, err := os.ReadFile(filepath.Join(dir, AllfilesCSVFileName))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), "\r\n") {
		t.Error("allfiles CSV does not use CRLF line endings (excel dialect)")
	}
	recs := readCSV(t, filepath.Join(dir, AllfilesCSVFileName))
	if want := "File,Size(bytes),Date-Modified,Date-Accessed,Owner,Group,Permissions,Tarred"; strings.Join(recs[0], ",") != want {
		t.Errorf("CSV header = %q, want %q", strings.Join(recs[0], ","), want)
	}
	rows := map[string][]string{}
	for _, rec := range recs[1:] {
		rows[rec[0]] = rec
	}
	if len(rows) != 8 {
		t.Errorf("CSV has %d data rows, want 8: %v", len(rows), rows)
	}
	check := func(name, wantSize, wantTarred, wantPermPrefix string) {
		t.Helper()
		rec, ok := rows[name]
		if !ok {
			t.Errorf("CSV row for %q missing", name)
			return
		}
		if rec[1] != wantSize {
			t.Errorf("%s size = %s, want %s", name, rec[1], wantSize)
		}
		if rec[7] != wantTarred {
			t.Errorf("%s Tarred = %s, want %s", name, rec[7], wantTarred)
		}
		if !strings.HasPrefix(rec[6], wantPermPrefix) {
			t.Errorf("%s Permissions = %s, want prefix %s", name, rec[6], wantPermPrefix)
		}
	}
	check("exactly_1mib.dat", "1048576", "No", "0o100")
	check("just_under_1mib.dat", "1048575", "Yes", "0o100")
	check("big.dat", "2097152", "No", "0o100644")
	check("small_report.txt", "11", "Yes", "0o100644")
	check("link.dat", "7", "Yes", "0o120") // symlink: lstat size = len("big.dat"), mode 0o120xxx
}

func TestGenAllfilesAndTarNoTarring(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, "tiny.txt"), "x")

	if err := w.genAllfilesAndTar(dir, 1024, false); err != nil {
		t.Fatal(err)
	}
	// --no-tar: no tar file, original kept, CSV row says No.
	mustNotExist(t, filepath.Join(dir, SmallfilesTarFileName))
	mustExist(t, filepath.Join(dir, "tiny.txt"))
	recs := readCSV(t, filepath.Join(dir, AllfilesCSVFileName))
	if recs[1][7] != "No" {
		t.Errorf("Tarred = %s, want No", recs[1][7])
	}
}

func TestGenAllfilesAndTarEmptyTarRemoved(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()
	writeBytes(t, filepath.Join(dir, "big.dat"), 1024*1024) // exactly 1 MiB: not tarred

	if err := w.genAllfilesAndTar(dir, 1024, true); err != nil {
		t.Fatal(err)
	}
	mustNotExist(t, filepath.Join(dir, SmallfilesTarFileName))
	mustExist(t, filepath.Join(dir, AllfilesCSVFileName))
}

func TestGenAllfilesAndTarIdempotentResume(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, "small.txt"), "payload")
	// A pre-existing tar makes the whole step a no-op (resume).
	writeFile(t, filepath.Join(dir, SmallfilesTarFileName), "pre-existing tar bytes")

	if err := w.genAllfilesAndTar(dir, 1024, true); err != nil {
		t.Fatal(err)
	}
	// Nothing regenerated: no CSV, small file kept, tar untouched.
	mustNotExist(t, filepath.Join(dir, AllfilesCSVFileName))
	mustExist(t, filepath.Join(dir, "small.txt"))
	data, _ := os.ReadFile(filepath.Join(dir, SmallfilesTarFileName))
	if string(data) != "pre-existing tar bytes" {
		t.Error("pre-existing tar was modified")
	}
}

func TestGenAllfilesAndTarRawByteNames(t *testing.T) {
	// A Latin-1 (non-UTF-8) file name must round-trip through the CSV and
	// the tar without corrupting state (Python bug Q5 — Go must handle it).
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()
	name := "caf\xe9.dat"
	writeFile(t, filepath.Join(dir, name), "latin1 content")

	if err := w.genAllfilesAndTar(dir, 1024, true); err != nil {
		t.Fatalf("genAllfilesAndTar with raw-byte name: %v", err)
	}
	members := tarMembers(t, filepath.Join(dir, SmallfilesTarFileName))
	if len(members) != 1 || members[0] != name {
		t.Errorf("tar members = %q, want [%q]", members, name)
	}
	raw, err := os.ReadFile(filepath.Join(dir, AllfilesCSVFileName))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), name) {
		t.Error("allfiles CSV does not contain the raw-byte file name")
	}
	// Round-trip: untar restores the file byte-for-byte.
	if err := untar(filepath.Join(dir, SmallfilesTarFileName), dir); err != nil {
		t.Fatal(err)
	}
	content, err := os.ReadFile(filepath.Join(dir, name))
	if err != nil {
		t.Fatal(err)
	}
	if string(content) != "latin1 content" {
		t.Error("untarred content differs")
	}
}

// TestTarMembersMatchGoldenFixture reconstructs the golden tree's root
// folder (names and sizes from testdata/golden/MANIFEST.md) and asserts
// that the exact same member set is tarred as Python froster produced
// (root.smallfiles-tar-members.txt).
func TestTarMembersMatchGoldenFixture(t *testing.T) {
	golden := filepath.Join(goldenDir(t), "archive", "root.smallfiles-tar-members.txt")
	listing, err := os.ReadFile(golden)
	if err != nil {
		t.Skipf("golden fixture unavailable: %v", err)
	}
	var want []string
	for _, line := range strings.Split(strings.TrimSpace(string(listing)), "\n") {
		// tar -tvf: perms owner size date time NAME (name may contain spaces:
		// fields 0-5 are fixed, the rest is the name).
		fields := strings.Fields(line)
		if len(fields) < 6 {
			continue
		}
		name := strings.Join(fields[5:], " ")
		want = append(want, name)
	}
	sort.Strings(want)

	w, _ := newTestWorkflow(t)
	dir := t.TempDir()
	sizes := map[string]int{
		"big_alpha.dat":        2 * 1024 * 1024,
		"big_beta.dat":         3670016,
		"exactly_1mib.dat":     1048576,
		"just_under_1mib.dat":  1048575,
		"small_report.txt":     10240,
		"file with spaces.txt": 5120,
		"values,comma.csv":     4096,
		`quote"file.txt`:       3072,
	}
	for name, size := range sizes {
		writeBytes(t, filepath.Join(dir, name), size)
	}
	if err := os.Mkdir(filepath.Join(dir, "sub_data"), 0o755); err != nil {
		t.Fatal(err)
	}

	if err := w.genAllfilesAndTar(dir, 1024, true); err != nil {
		t.Fatal(err)
	}
	got := tarMembers(t, filepath.Join(dir, SmallfilesTarFileName))
	if strings.Join(got, "|") != strings.Join(want, "|") {
		t.Errorf("tar members = %v\nwant (golden) %v", got, want)
	}
}

// TestGoldenTarReadable proves Go's archive/tar can read the PAX tars the
// Python implementation produced (committed fixture), listing the same
// members.
func TestGoldenTarReadable(t *testing.T) {
	tarPath := filepath.Join(goldenDir(t), "archive", "root.Froster.smallfiles.tar")
	if _, err := os.Stat(tarPath); err != nil {
		t.Skipf("golden fixture unavailable: %v", err)
	}
	got := tarMembers(t, tarPath)
	want := []string{"file with spaces.txt", "just_under_1mib.dat", `quote"file.txt`, "small_report.txt", "values,comma.csv"}
	sort.Strings(want)
	if strings.Join(got, "|") != strings.Join(want, "|") {
		t.Errorf("golden tar members = %v, want %v", got, want)
	}
}

// goldenDir locates go/testdata/golden from the package directory.
func goldenDir(t *testing.T) string {
	t.Helper()
	dir, err := filepath.Abs(filepath.Join("..", "..", "testdata", "golden"))
	if err != nil {
		t.Fatal(err)
	}
	return dir
}
