package workflow

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
)

func TestArchiveSingleHappyPath(t *testing.T) {
	w, engine := newTestWorkflow(t)
	w.Provider = "AWS" // exercise the INTELLIGENT_TIERING branch
	dir := t.TempDir()
	writeBytes(t, filepath.Join(dir, "big.dat"), 2*1024*1024)
	writeFile(t, filepath.Join(dir, "small.txt"), "small")
	writeFile(t, filepath.Join(dir, "sub", "nested.txt"), "nested") // silently ignored (Single mode)

	out := captureStdout(t, func() {
		if err := w.Archive(context.Background(), []string{dir}, ArchiveOptions{}); err != nil {
			t.Errorf("Archive: %v", err)
		}
	})

	// Artifacts.
	mustExist(t, filepath.Join(dir, AllfilesCSVFileName))
	mustExist(t, filepath.Join(dir, MD5SumFileName))
	mustExist(t, filepath.Join(dir, SmallfilesTarFileName))
	mustNotExist(t, filepath.Join(dir, "small.txt")) // tarred + removed

	// Engine call sequence: allfiles.csv first, then the main copy.
	if len(engine.Copies) != 2 {
		t.Fatalf("Copy called %d times, want 2", len(engine.Copies))
	}
	s3Dest := ":s3:froster-golden/froster" + dir

	csvCopy := engine.Copies[0]
	if csvCopy.Src != filepath.Join(dir, AllfilesCSVFileName) || csvCopy.Dst != s3Dest {
		t.Errorf("allfiles copy = %s -> %s", csvCopy.Src, csvCopy.Dst)
	}
	if csvCopy.Opts.StorageClass != "INTELLIGENT_TIERING" {
		t.Errorf("allfiles storage class = %q, want INTELLIGENT_TIERING (provider AWS)", csvCopy.Opts.StorageClass)
	}
	if csvCopy.Opts.MaxDepth != 1 || !csvCopy.Opts.Links {
		t.Errorf("allfiles copy opts = %+v", csvCopy.Opts)
	}

	mainCopy := engine.Copies[1]
	if mainCopy.Src != dir || mainCopy.Dst != s3Dest {
		t.Errorf("main copy = %s -> %s", mainCopy.Src, mainCopy.Dst)
	}
	if mainCopy.Opts.StorageClass != "" {
		t.Errorf("main copy storage class override = %q, want none", mainCopy.Opts.StorageClass)
	}
	if mainCopy.Opts.MaxDepth != 1 || !mainCopy.Opts.Links ||
		mainCopy.Opts.Transfers != 4 || mainCopy.Opts.Checkers != 2 ||
		mainCopy.Opts.MultiThreadStreams != 4 {
		t.Errorf("main copy opts = %+v", mainCopy.Opts)
	}
	wantExcludes := strings.Join([]string{MD5SumFileName, MD5SumRestoredFileName, AllfilesCSVFileName, WhereDidTheFilesGoFileName}, "|")
	if strings.Join(mainCopy.Opts.Exclude, "|") != wantExcludes {
		t.Errorf("main copy excludes = %v", mainCopy.Opts.Exclude)
	}

	// Verification.
	if len(engine.Checks) != 1 {
		t.Fatalf("CheckMD5 called %d times, want 1", len(engine.Checks))
	}
	if chk := engine.Checks[0]; chk.MD5File != filepath.Join(dir, MD5SumFileName) ||
		chk.Remote != s3Dest || chk.Opts.MaxDepth != 1 || chk.Opts.Checkers != 2 {
		t.Errorf("verify call = %+v", chk)
	}

	// DB entry with the exact key set.
	entry := w.DB.Get(dir)
	if entry == nil {
		t.Fatal("no DB entry written")
	}
	if entry.ArchiveFolder != s3Dest || entry.ArchiveMode != archivedb.ModeSingle ||
		entry.Profile != "minio" || entry.Provider != "AWS" ||
		entry.S3StorageClass != "STANDARD" || entry.User != "dp" ||
		entry.Timestamp == "" || entry.Timestamp != entry.TimestampArchive {
		t.Errorf("DB entry = %+v", entry)
	}
	if entry.TimestampDeleted != "" || entry.TimestampRestored != "" {
		t.Error("archive wrote timestamp_deleted/timestamp_restored (Python never does)")
	}

	// Message shape: banner and per-step done lines.
	for _, want := range []string{
		"\nARCHIVING " + dir + "\n",
		"\n    Generating Froster.allfiles.csv and tar small files...\n        ...done\n",
		"\n    Generating checksums...\n\n        ...done\n",
		"\n    Uploading Froster.allfiles.csv file...\n        ...done\n",
		"\n    Uploading files...\n        ...done\n",
		"\n    Verifying checksums...\n        ...done\n",
		"\nARCHIVING SUCCESSFULLY COMPLETED\n",
		"    PROVIDER:           \"AWS\"\n",
		"    PROFILE:            \"profile minio\"\n",
		"    LOCAL SOURCE:       \"" + dir + "\"\n",
		"    S3 DESTINATION:     \"" + s3Dest + "\"\n",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("output missing %q, got:\n%s", want, out)
		}
	}
}

// TestArchiveDBFileMatchesGoldenShape writes an entry through the real DB
// code with golden values and compares the file against the golden
// froster-archives.json modulo the timestamps.
func TestArchiveDBFileMatchesGoldenShape(t *testing.T) {
	golden, err := os.ReadFile(filepath.Join(goldenDir(t), "archive", "froster-archives.json"))
	if err != nil {
		t.Skipf("golden fixture unavailable: %v", err)
	}

	w, engine := newTestWorkflow(t)
	w.Provider = "Minio"
	base := t.TempDir()
	dir := filepath.Join(base, "golden-tree")
	writeBytes(t, filepath.Join(dir, "big_alpha.dat"), 2*1024*1024)
	_ = engine

	if err := w.Archive(context.Background(), []string{dir}, ArchiveOptions{Recursive: true}); err != nil {
		t.Fatalf("Archive: %v", err)
	}

	got, err := os.ReadFile(w.DB.Path())
	if err != nil {
		t.Fatal(err)
	}

	normalize := func(data []byte, folder, user string) string {
		s := string(data)
		s = strings.ReplaceAll(s, folder, "<FOLDER>")
		s = regexp.MustCompile(`"timestamp(_archive)?": "[^"]*"`).ReplaceAllString(s, `"timestamp$1": "<TS>"`)
		s = strings.ReplaceAll(s, `"user": "`+user+`"`, `"user": "<USER>"`)
		return s
	}
	gotN := normalize(got, dir, "dp")
	wantN := normalize(golden, "/tmp/froster-golden/data/golden-tree", "dp")
	if gotN != wantN {
		t.Errorf("DB file shape differs from golden:\n--- got ---\n%s\n--- want ---\n%s", gotN, wantN)
	}
}

func TestArchiveRecursiveEmptyLastSubfolderStillWritesDB(t *testing.T) {
	// DOCUMENTED DEVIATION test (Python bug Q6): the empty dir walked last
	// must not suppress the DB entry.
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()
	writeBytes(t, filepath.Join(dir, "data.bin"), 2048)
	if err := os.MkdirAll(filepath.Join(dir, "zz-empty-dir"), 0o755); err != nil {
		t.Fatal(err)
	}

	if err := w.Archive(context.Background(), []string{dir}, ArchiveOptions{Recursive: true}); err != nil {
		t.Fatalf("Archive: %v", err)
	}
	entry := w.DB.Get(dir)
	if entry == nil {
		t.Fatal("recursive archive with trailing empty dir wrote no DB entry")
	}
	if entry.ArchiveMode != archivedb.ModeRecursive {
		t.Errorf("archive_mode = %s", entry.ArchiveMode)
	}
	// The subfolder gets no entry of its own.
	if len(w.DB.All()) != 1 {
		t.Errorf("DB has %d entries, want 1", len(w.DB.All()))
	}
}

func TestArchiveSkipsEmptyFolderEntirely(t *testing.T) {
	w, engine := newTestWorkflow(t)
	dir := t.TempDir() // empty

	out := captureStdout(t, func() {
		if err := w.Archive(context.Background(), []string{dir}, ArchiveOptions{}); err != nil {
			t.Errorf("Archive: %v", err)
		}
	})
	if !strings.Contains(out, "contains no files or symlinks to archive (only subdirectories and/or metadata), skipping.") {
		t.Errorf("missing skip message:\n%s", out)
	}
	if len(engine.Copies) != 0 {
		t.Error("uploads happened for an empty folder")
	}
	if w.DB.Get(dir) != nil {
		t.Error("DB entry written for a skipped folder")
	}
}

func TestArchiveExistingHashfileRefusals(t *testing.T) {
	w, engine := newTestWorkflow(t)
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, "data.bin"), "d")
	writeFile(t, filepath.Join(dir, MD5SumFileName), "sums")

	// Case: no DB entry → "hashfile already exists" + force hint (sic "us").
	out := captureStdout(t, func() {
		err := w.Archive(context.Background(), []string{dir}, ArchiveOptions{})
		if !errors.Is(err, ErrReported) {
			t.Errorf("err = %v, want ErrReported", err)
		}
	})
	if !strings.Contains(out, `The hashfile ".froster.md5sum" already exists in `+dir) ||
		!strings.Contains(out, "please us the -f or --force flag") {
		t.Errorf("missing hashfile-exists message:\n%s", out)
	}

	// Case: DB entry + checksum OK → "already archived".
	upsertEntry(t, w, goldenEntry(dir))
	out = captureStdout(t, func() {
		err := w.Archive(context.Background(), []string{dir}, ArchiveOptions{})
		if !errors.Is(err, ErrReported) {
			t.Errorf("err = %v, want ErrReported", err)
		}
	})
	if !strings.Contains(out, "The folder "+dir+" is already archived in S3 bucket.") {
		t.Errorf("missing already-archived message:\n%s", out)
	}
	if !strings.Contains(out, "'local_folder': '"+dir+"'") {
		t.Errorf("missing dict-repr of the entry:\n%s", out)
	}

	// Case: DB entry + checksum mismatch.
	engine.CheckErr = func(string, string) error { return errors.New("2 differences found") }
	out = captureStdout(t, func() {
		err := w.Archive(context.Background(), []string{dir}, ArchiveOptions{})
		if !errors.Is(err, ErrReported) {
			t.Errorf("err = %v, want ErrReported", err)
		}
	})
	if !strings.Contains(out, "already archived in our database but checksums do not match in the S3 bucket.") {
		t.Errorf("missing checksum-mismatch message:\n%s", out)
	}
}

func TestArchiveForceResetsFirst(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()
	writeBytes(t, filepath.Join(dir, "big.dat"), 2*1024*1024)
	writeFile(t, filepath.Join(dir, MD5SumFileName), "stale sums")
	writeFile(t, filepath.Join(dir, AllfilesCSVFileName), "stale csv")

	if err := w.Archive(context.Background(), []string{dir}, ArchiveOptions{Force: true}); err != nil {
		t.Fatalf("Archive --force: %v", err)
	}
	// Fresh artifacts got generated after the reset.
	data, _ := os.ReadFile(filepath.Join(dir, AllfilesCSVFileName))
	if strings.Contains(string(data), "stale csv") {
		t.Error("allfiles.csv was not regenerated")
	}
	if w.DB.Get(dir) == nil {
		t.Error("no DB entry after forced archive")
	}
}

func TestArchiveUploadFailureStopsAndReports(t *testing.T) {
	w, engine := newTestWorkflow(t)
	engine.CopyErr = func(src, dst string) error {
		if strings.HasSuffix(src, AllfilesCSVFileName) {
			return nil
		}
		return errors.New("connection reset")
	}
	dir := t.TempDir()
	writeBytes(t, filepath.Join(dir, "big.dat"), 2*1024*1024)

	out := captureStdout(t, func() {
		err := w.Archive(context.Background(), []string{dir}, ArchiveOptions{})
		if !errors.Is(err, ErrReported) {
			t.Errorf("err = %v, want ErrReported", err)
		}
	})
	if !strings.Contains(out, "    Uploading files...\n        ...FAILED\n") {
		t.Errorf("missing FAILED marker:\n%s", out)
	}
	if w.DB.Get(dir) != nil {
		t.Error("DB entry written despite upload failure")
	}
}

func TestArchiveRecursiveCollision(t *testing.T) {
	w, _ := newTestWorkflow(t)
	parent := t.TempDir()
	child := filepath.Join(parent, "sub")
	if err := os.MkdirAll(child, 0o755); err != nil {
		t.Fatal(err)
	}

	out := captureStdout(t, func() {
		err := w.Archive(context.Background(), []string{parent, child}, ArchiveOptions{Recursive: true})
		if !errors.Is(err, ErrReported) {
			t.Errorf("err = %v, want ErrReported", err)
		}
	})
	if !strings.Contains(out, "You cannot archive folders recursively if there is a dependency between them.") {
		t.Errorf("missing collision message:\n%s", out)
	}
}

func TestResetFolder(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, "small.txt"), "payload")
	sub := filepath.Join(dir, "sub")
	writeFile(t, filepath.Join(sub, "tiny.txt"), "nested payload")

	// Archive-like state: tar the small files.
	if err := w.genAllfilesAndTar(dir, 1024, true); err != nil {
		t.Fatal(err)
	}
	if err := w.genAllfilesAndTar(sub, 1024, true); err != nil {
		t.Fatal(err)
	}
	if err := w.genMD5Sums(dir, MD5SumFileName); err != nil {
		t.Fatal(err)
	}
	mustNotExist(t, filepath.Join(dir, "small.txt"))

	// Non-recursive reset touches only the top folder.
	if err := w.ResetFolders([]string{dir}, false); err != nil {
		t.Fatal(err)
	}
	mustExist(t, filepath.Join(dir, "small.txt"))
	mustNotExist(t, filepath.Join(dir, SmallfilesTarFileName))
	mustNotExist(t, filepath.Join(dir, AllfilesCSVFileName))
	mustNotExist(t, filepath.Join(dir, MD5SumFileName))
	mustExist(t, filepath.Join(sub, SmallfilesTarFileName)) // untouched

	// Recursive reset also handles the subfolder. (DOCUMENTED DEVIATION:
	// Python's reset_folder returns from inside the walk loop and never
	// reaches the second directory even with recursive=True.)
	if err := w.ResetFolders([]string{dir}, true); err != nil {
		t.Fatal(err)
	}
	mustExist(t, filepath.Join(sub, "tiny.txt"))
	mustNotExist(t, filepath.Join(sub, SmallfilesTarFileName))
}
