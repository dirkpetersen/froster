package walker

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"golang.org/x/sys/unix"
)

// cPwalkBin locates the reference C pwalk binary. Golden tests are skipped
// when it is unavailable. Override with the PWALK_C_BIN environment
// variable.
func cPwalkBin(t *testing.T) string {
	t.Helper()
	if p := os.Getenv("PWALK_C_BIN"); p != "" {
		return p
	}
	home, err := os.UserHomeDir()
	if err != nil {
		t.Skip("no home directory; cannot locate C pwalk")
	}
	p := filepath.Join(home, "gh", "python-pwalk", "filesystem-reporting-tools", "pwalk")
	if _, err := os.Stat(p); err != nil {
		t.Skipf("C pwalk binary not found at %s (set PWALK_C_BIN to override)", p)
	}
	return p
}

// buildGoldenTree creates the edge-case tree used for the byte-level
// comparison against the C binary. It mirrors the fixture captured in
// testdata/golden-pwalk-reference.csv.
func buildGoldenTree(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	w := func(rel string, size int) {
		t.Helper()
		if err := os.WriteFile(filepath.Join(root, rel), bytes.Repeat([]byte{'x'}, size), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	for _, d := range []string{"a/b/c", "emptydir", "dir.with.ext", ".snapshot"} {
		if err := os.MkdirAll(filepath.Join(root, d), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	w(".snapshot/hidden_snap.txt", 50)
	w("plain.txt", 1234)
	w("file with spaces.dat", 10)
	w(`quo"te.txt`, 20)
	w("com,ma.csv", 30)
	w("a/nested.bin", 4096)
	w("a/b/deep.log", 777)
	w("a/b/c/deepest", 1)
	w(".bashrc", 5)
	w("noext", 7)
	w("multi.part.tar.gz", 8)
	w("..leadingdots.txt", 9)
	// Latin-1 (non-UTF-8) filename byte: caf\xe9.txt.
	w(string([]byte{'c', 'a', 'f', 0xe9, '.', 't', 'x', 't'}), 11)
	// Control characters in the name (stripped by pwalk's escaping).
	w("bad\nname\tfile.txt", 12)
	// A trailing-dot name: C pwalk prints uninitialized memory as the
	// extension; we deliberately emit "". The comparison masks this field.
	w("trailing.", 6)
	if err := os.Link(filepath.Join(root, "plain.txt"), filepath.Join(root, "hardlink-to-plain.txt")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("plain.txt", filepath.Join(root, "link-to-plain")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("/nonexistent/target.foo", filepath.Join(root, "dangling.link")); err != nil {
		t.Fatal(err)
	}
	if err := unix.Mkfifo(filepath.Join(root, "pipe.fifo"), 0o644); err != nil {
		t.Fatal(err)
	}
	return root
}

// warmUpAtimes reads every directory once so that relatime updates happen
// before either walker runs; otherwise the first walker's readdir bumps
// directory atimes and the second sees different st_atime values.
func warmUpAtimes(t *testing.T, root string) {
	t.Helper()
	err := filepath.WalkDir(root, func(string, os.DirEntry, error) error { return nil })
	if err != nil {
		t.Fatal(err)
	}
}

// maskGarbageExt blanks the fileExtension field of rows whose filename
// ends in '.', where C pwalk emits uninitialized memory (see package doc).
func maskGarbageExt(row string) string {
	f := splitPwalkRow(row)
	if len(f) == 17 && strings.HasSuffix(f[fldFilename], ".") && f[fldFcount] == "-1" {
		needle := `","` + f[fldExt] + `",`
		return strings.Replace(row, needle, `","",`, 1)
	}
	return row
}

// TestGoldenAgainstCPwalk runs the reference C binary and this package on
// the same tree with froster's exact flags (--NoSnap --one-file-system
// --header) and requires the sorted row sets to be identical in every
// field.
func TestGoldenAgainstCPwalk(t *testing.T) {
	bin := cPwalkBin(t)
	root := buildGoldenTree(t)
	warmUpAtimes(t, root)

	// C pwalk with froster's flags. It prints "unable to setuid root" and
	// "Bad File" diagnostics on stderr; only stdout matters.
	var cOut, cErr bytes.Buffer
	cmd := exec.Command(bin, "--NoSnap", "--one-file-system", "--header", root)
	cmd.Stdout = &cOut
	cmd.Stderr = &cErr
	if err := cmd.Run(); err != nil {
		t.Fatalf("C pwalk failed: %v\nstderr: %s", err, cErr.String())
	}

	var goOut bytes.Buffer
	sum, err := Walk(root, &goOut, Options{NoSnap: true, OneFS: true, Header: true})
	if err != nil {
		t.Fatal(err)
	}

	cLines := strings.Split(strings.TrimSuffix(cOut.String(), "\n"), "\n")
	goLines := strings.Split(strings.TrimSuffix(goOut.String(), "\n"), "\n")

	// The header must be byte-identical and come first in both.
	if cLines[0] != strings.TrimSuffix(Header, "\n") {
		t.Errorf("C pwalk header mismatch:\nC:  %q\nGo: %q", cLines[0], Header)
	}
	if goLines[0] != strings.TrimSuffix(Header, "\n") {
		t.Errorf("Go header mismatch: %q", goLines[0])
	}

	// Row order is nondeterministic in both implementations: compare
	// sorted row sets, masking the known uninitialized-memory field.
	cRows, goRows := cLines[1:], goLines[1:]
	for i, r := range cRows {
		cRows[i] = maskGarbageExt(r)
	}
	sort.Strings(cRows)
	sort.Strings(goRows)

	if len(cRows) != len(goRows) {
		t.Fatalf("row count: C=%d Go=%d\nC:\n%s\nGo:\n%s",
			len(cRows), len(goRows), strings.Join(cRows, "\n"), strings.Join(goRows, "\n"))
	}
	for i := range cRows {
		if cRows[i] != goRows[i] {
			t.Errorf("row %d differs:\nC:  %s\nGo: %s", i, cRows[i], goRows[i])
		}
	}

	// Cross-check the per-directory rollups froster's hotspot query
	// consumes: directory rows (pw_fcount > -1) keyed by filename.
	type rollup struct{ fcount, dirsum string }
	dirRollups := func(rows []string) map[string]rollup {
		m := map[string]rollup{}
		for _, r := range rows {
			f := splitPwalkRow(r)
			if f[fldFcount] != "-1" {
				m[f[fldFilename]] = rollup{f[fldFcount], f[fldDirsum]}
			}
		}
		return m
	}
	cDirs, goDirs := dirRollups(cRows), dirRollups(goRows)
	if len(cDirs) != len(goDirs) {
		t.Errorf("directory row count: C=%d Go=%d", len(cDirs), len(goDirs))
	}
	for name, cr := range cDirs {
		if gr, ok := goDirs[name]; !ok {
			t.Errorf("missing Go directory row for %q", name)
		} else if gr != cr {
			t.Errorf("rollup mismatch for %q: C=%+v Go=%+v", name, cr, gr)
		}
	}

	if sum.DirRows+sum.FileRows != int64(len(goRows)) {
		t.Errorf("summary rows %d+%d != emitted rows %d", sum.DirRows, sum.FileRows, len(goRows))
	}
	if sum.BadNames == 0 {
		t.Error("expected BadNames > 0 for the control-character fixture")
	}
}
