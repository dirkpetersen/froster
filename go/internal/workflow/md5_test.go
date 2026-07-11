package workflow

import (
	"crypto/md5" //nolint:gosec
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

func TestGenMD5SumsFormatAndExclusions(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()

	writeFile(t, filepath.Join(dir, "data.bin"), "some data")
	writeFile(t, filepath.Join(dir, SmallfilesTarFileName), "tar bytes")   // included
	writeFile(t, filepath.Join(dir, AllfilesCSVFileName), "csv bytes")     // included
	writeFile(t, filepath.Join(dir, MD5SumRestoredFileName), "old sums")   // excluded
	writeFile(t, filepath.Join(dir, WhereDidTheFilesGoFileName), "readme") // excluded
	// Broken symlink: skipped. Good symlink: hashed through the link.
	if err := os.Symlink("nowhere", filepath.Join(dir, "broken")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("data.bin", filepath.Join(dir, "good")); err != nil {
		t.Fatal(err)
	}
	// Subdirectory: never hashed.
	writeFile(t, filepath.Join(dir, "sub", "x"), "nested")

	if err := w.genMD5Sums(dir, MD5SumFileName); err != nil {
		t.Fatalf("genMD5Sums: %v", err)
	}

	lines := readLines(t, filepath.Join(dir, MD5SumFileName))
	got := map[string]string{}
	for _, line := range lines {
		// Exactly two spaces between hash and name (md5sum format).
		i := strings.Index(line, "  ")
		if i != 32 {
			t.Errorf("malformed md5 line %q (separator at %d, want 32)", line, i)
			continue
		}
		got[line[i+2:]] = line[:i]
	}

	var names []string
	for n := range got {
		names = append(names, n)
	}
	sort.Strings(names)
	want := []string{AllfilesCSVFileName, SmallfilesTarFileName, "data.bin", "good"}
	sort.Strings(want)
	if strings.Join(names, "|") != strings.Join(want, "|") {
		t.Errorf("hashed files = %v, want %v", names, want)
	}

	sum := md5.Sum([]byte("some data")) //nolint:gosec
	if got["data.bin"] != hex.EncodeToString(sum[:]) {
		t.Errorf("data.bin md5 = %s, want %s", got["data.bin"], hex.EncodeToString(sum[:]))
	}
	if got["good"] != got["data.bin"] {
		t.Error("symlink not hashed through the link")
	}
}

func TestGenMD5SumsEmptyIsFailure(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, WhereDidTheFilesGoFileName), "only meta")

	err := w.genMD5Sums(dir, MD5SumRestoredFileName)
	if !errors.Is(err, errEmptyMD5) {
		t.Fatalf("err = %v, want errEmptyMD5", err)
	}
	// The empty hash file is removed again (Python parity).
	mustNotExist(t, filepath.Join(dir, MD5SumRestoredFileName))
}

func TestGoldenMD5FixtureShape(t *testing.T) {
	// The golden .froster.md5sum must parse with our expectations:
	// two-space separator, tar and allfiles.csv included.
	path := filepath.Join(goldenDir(t), "archive", "root.froster.md5sum")
	if _, err := os.Stat(path); err != nil {
		t.Skipf("golden fixture unavailable: %v", err)
	}
	lines := readLines(t, path)
	names := map[string]bool{}
	for _, line := range lines {
		i := strings.Index(line, "  ")
		if i != 32 {
			t.Fatalf("golden md5 line %q has separator at %d", line, i)
		}
		names[line[i+2:]] = true
	}
	for _, want := range []string{SmallfilesTarFileName, AllfilesCSVFileName} {
		if !names[want] {
			t.Errorf("golden md5sum missing %s", want)
		}
	}
	for _, forbidden := range []string{MD5SumFileName, MD5SumRestoredFileName, WhereDidTheFilesGoFileName} {
		if names[forbidden] {
			t.Errorf("golden md5sum unexpectedly lists %s", forbidden)
		}
	}
}
