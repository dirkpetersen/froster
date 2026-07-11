package workflow

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestIndexProducesHotspotCSVAndSummary(t *testing.T) {
	w, _ := newTestWorkflow(t)
	hotspotsDir := t.TempDir()
	tree := t.TempDir()
	// Small files only: no hotspot rows (thresholds 1 GiB / 10 MiB avg),
	// but the CSV with the header must exist and the summary must print.
	writeBytes(t, filepath.Join(tree, "a.dat"), 4096)
	writeBytes(t, filepath.Join(tree, "sub", "b.dat"), 4096)

	opts := IndexOptions{HotspotsDir: hotspotsDir}
	out := captureStdout(t, func() {
		if err := w.Index([]string{tree}, opts); err != nil {
			t.Errorf("Index: %v", err)
		}
	})

	csvPath := filepath.Join(hotspotsDir, strings.ReplaceAll(tree, "/", "+")+".csv")
	data, err := os.ReadFile(csvPath)
	if err != nil {
		t.Fatalf("hotspot CSV missing: %v", err)
	}
	if !strings.HasPrefix(string(data), "User,AccD,ModD,GiB,MiBAvg,Folder,Group,TiB,FileCount,DirSize\r\n") {
		t.Errorf("hotspot CSV header wrong:\n%q", string(data))
	}

	for _, want := range []string{
		"  Running pwalk filesystem scan on \"" + tree + "\"...\n    ...pwalk scan complete.\n",
		"  Filtering pwalk output (removing directories)...\n    ...filtering complete.\n",
		"  Converting character encoding...\n    ...conversion complete.\n",
		"  Analyzing folder data with DuckDB...\n    ...analysis complete.\n",
		"  Processing and writing hotspots CSV (" + csvPath + ")...\n    ...hotspots CSV written.\n",
		"\nHotspots file: " + csvPath + "\n    with 0 hotspots >= 1 GiB\n    with a total disk use of 0.0 TiB\n",
		"Total folders processed: 2\n",
		"\nINDEXING SUCCESSFULLY COMPLETED\n",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("index output missing %q:\n%s", want, out)
		}
	}
	// The Python "\nINDEXING {folder}" line never prints (silent TypeError
	// in Python's log(flush=True) call) — reproduced.
	if strings.Contains(out, "INDEXING "+tree) {
		t.Error("output contains the INDEXING line that Python never prints")
	}

	// Second run: already indexed.
	out = captureStdout(t, func() {
		if err := w.Index([]string{tree}, opts); err != nil {
			t.Errorf("Index (again): %v", err)
		}
	})
	if !strings.Contains(out, "FOLDER ALREADY INDEXED at "+csvPath) ||
		!strings.Contains(out, "Use \"-f\" or \"--force\" flag to force indexing again.") {
		t.Errorf("missing already-indexed message:\n%s", out)
	}

	// --force re-indexes.
	opts.Force = true
	out = captureStdout(t, func() {
		if err := w.Index([]string{tree}, opts); err != nil {
			t.Errorf("Index --force: %v", err)
		}
	})
	if !strings.Contains(out, "INDEXING SUCCESSFULLY COMPLETED") {
		t.Errorf("--force did not re-index:\n%s", out)
	}
}

func TestIndexPwalkCopy(t *testing.T) {
	w, _ := newTestWorkflow(t)
	hotspotsDir := t.TempDir()
	copyDir := t.TempDir()
	tree := t.TempDir()
	writeBytes(t, filepath.Join(tree, "a.dat"), 128)

	if err := w.Index([]string{tree}, IndexOptions{HotspotsDir: hotspotsDir, PwalkCopy: copyDir}); err != nil {
		t.Fatalf("Index --pwalk-copy: %v", err)
	}
	copyPath := filepath.Join(copyDir, strings.ReplaceAll(tree, "/", "+")+".csv")
	data, err := os.ReadFile(copyPath)
	if err != nil {
		t.Fatalf("pwalk copy missing: %v", err)
	}
	// Raw pwalk CSV: header plus directory AND file rows.
	if !strings.HasPrefix(string(data), "inode,parent-inode,directory-depth,") {
		t.Errorf("pwalk copy header wrong:\n%.100s", string(data))
	}
	if !strings.Contains(string(data), "a.dat") {
		t.Error("pwalk copy is missing the file row")
	}
}

func TestIndexCollision(t *testing.T) {
	w, _ := newTestWorkflow(t)
	parent := t.TempDir()
	child := filepath.Join(parent, "inner")
	if err := os.MkdirAll(child, 0o755); err != nil {
		t.Fatal(err)
	}
	out := captureStdout(t, func() {
		if !w.IndexCollision([]string{parent, child}) {
			t.Error("collision not detected")
		}
	})
	if !strings.Contains(out, "You cannot index folders if there is a dependency between them. Specify only the parent folder.") {
		t.Errorf("missing collision message:\n%s", out)
	}
}

func TestTranscodeLatin1File(t *testing.T) {
	src := filepath.Join(t.TempDir(), "in.csv")
	dst := filepath.Join(t.TempDir(), "out.csv")
	if err := os.WriteFile(src, []byte("caf\xe9,1\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := transcodeLatin1File(src, dst); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(dst)
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "café,1\n" {
		t.Errorf("transcoded = %q, want %q", data, "café,1\n")
	}
}
