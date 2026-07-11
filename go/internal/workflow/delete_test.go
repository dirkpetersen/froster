package workflow

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
)

// TestManifestBodyMatchesGoldenFixture renders the deletion manifest with
// the exact inputs of the golden run and compares byte-for-byte with the
// Where-did-the-files-go.txt Python froster wrote.
func TestManifestBodyMatchesGoldenFixture(t *testing.T) {
	goldenPath := filepath.Join(goldenDir(t), "delete", "root.Where-did-the-files-go.txt")
	want, err := os.ReadFile(goldenPath)
	if err != nil {
		t.Skipf("golden fixture unavailable: %v", err)
	}

	w, _ := newTestWorkflow(t)
	db, err := archivedb.Load("/tmp/froster-golden/home/.local/share/froster/froster-archives.json")
	if err != nil {
		t.Fatal(err)
	}
	w.DB = db // Path() only; never written

	folder := "/tmp/froster-golden/data/golden-tree"
	entry := goldenEntry(folder)
	entry.ArchiveMode = archivedb.ModeRecursive
	deleted := []string{"big_beta.dat", "Froster.smallfiles.tar", "big_alpha.dat", "exactly_1mib.dat"}

	got := w.manifestBody(entry, folder, entry.ArchiveFolder, deleted)

	if got != string(want) {
		t.Errorf("manifest differs from golden fixture:\n--- got ---\n%s\n--- want ---\n%s", got, want)
	}
}

// TestManifestBodySubfolderMatchesGolden checks the recursive-subfolder
// variant (parent DB entry, sub_data folder).
func TestManifestBodySubfolderMatchesGolden(t *testing.T) {
	goldenPath := filepath.Join(goldenDir(t), "delete", "sub_data.Where-did-the-files-go.txt")
	want, err := os.ReadFile(goldenPath)
	if err != nil {
		t.Skipf("golden fixture unavailable: %v", err)
	}

	w, _ := newTestWorkflow(t)
	db, err := archivedb.Load("/tmp/froster-golden/home/.local/share/froster/froster-archives.json")
	if err != nil {
		t.Fatal(err)
	}
	w.DB = db

	parent := "/tmp/froster-golden/data/golden-tree"
	folder := parent + "/sub_data"
	entry := goldenEntry(parent)
	entry.ArchiveMode = archivedb.ModeRecursive
	s3Dest := entry.ArchiveFolder + strings.ReplaceAll(folder, entry.LocalFolder, "")

	// Golden run deleted these two (walk order).
	deleted := []string{"big_gamma.dat", "Froster.smallfiles.tar"}

	got := w.manifestBody(entry, folder, s3Dest, deleted)

	// The first-10 list order and the deletion timestamp are
	// non-deterministic in Python; normalize both sides.
	normalize := func(s string) string {
		lines := strings.Split(s, "\n")
		for i, line := range lines {
			if i > 0 && strings.HasPrefix(lines[i-1], "First 10 files deleted this time:") {
				parts := strings.Split(line, ", ")
				sortStrings(parts)
				lines[i] = strings.Join(parts, ", ")
			}
			if strings.HasPrefix(line, "Deletion date: ") {
				lines[i] = "Deletion date: <TS>"
			}
		}
		return strings.Join(lines, "\n")
	}
	if normalize(got) != normalize(string(want)) {
		t.Errorf("subfolder manifest differs:\n--- got ---\n%s\n--- want ---\n%s", got, want)
	}
}

func sortStrings(s []string) {
	for i := 1; i < len(s); i++ {
		for j := i; j > 0 && s[j] < s[j-1]; j-- {
			s[j], s[j-1] = s[j-1], s[j]
		}
	}
}

func TestDeleteKeeperSet(t *testing.T) {
	w, engine := newTestWorkflow(t)
	dir := t.TempDir()

	// Archived folder with data + all artifacts.
	writeFile(t, filepath.Join(dir, "data1.bin"), "d1")
	writeFile(t, filepath.Join(dir, "data2.bin"), "d2")
	writeFile(t, filepath.Join(dir, SmallfilesTarFileName), "tar")
	writeFile(t, filepath.Join(dir, AllfilesCSVFileName), "csv")
	writeFile(t, filepath.Join(dir, MD5SumFileName), "sums")
	writeFile(t, filepath.Join(dir, MD5SumRestoredFileName), "rsums")
	writeFile(t, filepath.Join(dir, "sub", "keepme"), "nested")
	upsertEntry(t, w, goldenEntry(dir))

	if err := w.Delete(context.Background(), []string{dir}, false); err != nil {
		t.Fatalf("Delete: %v", err)
	}

	// Keepers stay; data files and the tar are gone; subdirs untouched.
	mustExist(t, filepath.Join(dir, MD5SumFileName))
	mustExist(t, filepath.Join(dir, MD5SumRestoredFileName))
	mustExist(t, filepath.Join(dir, AllfilesCSVFileName))
	mustExist(t, filepath.Join(dir, WhereDidTheFilesGoFileName))
	mustNotExist(t, filepath.Join(dir, "data1.bin"))
	mustNotExist(t, filepath.Join(dir, "data2.bin"))
	mustNotExist(t, filepath.Join(dir, SmallfilesTarFileName))
	mustExist(t, filepath.Join(dir, "sub", "keepme"))

	// Verification used the local hashfile against the entry's S3 path.
	if len(engine.Checks) != 1 {
		t.Fatalf("CheckMD5 called %d times, want 1", len(engine.Checks))
	}
	chk := engine.Checks[0]
	if chk.MD5File != filepath.Join(dir, MD5SumFileName) {
		t.Errorf("verify hashfile = %s", chk.MD5File)
	}
	if chk.Remote != ":s3:froster-golden/froster"+dir {
		t.Errorf("verify remote = %s", chk.Remote)
	}
	if chk.Opts.MaxDepth != 1 {
		t.Errorf("verify MaxDepth = %d, want 1", chk.Opts.MaxDepth)
	}

	// Manifest content lists the deleted files.
	manifest, err := os.ReadFile(filepath.Join(dir, WhereDidTheFilesGoFileName))
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"data1.bin", "data2.bin", SmallfilesTarFileName} {
		if !strings.Contains(string(manifest), name) {
			t.Errorf("manifest missing deleted file %s", name)
		}
	}

	// Second run: "...already deleted", nothing more verified.
	if err := w.Delete(context.Background(), []string{dir}, false); err != nil {
		t.Fatal(err)
	}
	if len(engine.Checks) != 1 {
		t.Error("delete on already-deleted folder ran verification again")
	}
}

func TestDeleteVerificationFailureDeletesNothing(t *testing.T) {
	w, engine := newTestWorkflow(t)
	engine.CheckErr = func(string, string) error { return errors.New("1 differences found") }
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, "data.bin"), "d")
	writeFile(t, filepath.Join(dir, MD5SumFileName), "sums")
	upsertEntry(t, w, goldenEntry(dir))

	// Failure is silent for the exit code (Python returns True).
	if err := w.Delete(context.Background(), []string{dir}, false); err != nil {
		t.Fatalf("Delete: %v", err)
	}
	mustExist(t, filepath.Join(dir, "data.bin"))
	mustNotExist(t, filepath.Join(dir, WhereDidTheFilesGoFileName))
}

func TestDeleteUnarchivedAndNoHashfile(t *testing.T) {
	w, engine := newTestWorkflow(t)
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, "data.bin"), "d")

	out := captureStdout(t, func() {
		// Not in DB at all.
		if err := w.Delete(context.Background(), []string{dir}, false); err != nil {
			t.Errorf("Delete: %v", err)
		}
	})
	if !strings.Contains(out, "Folder "+dir+" is not archived") ||
		!strings.Contains(out, "No entry found in froster-archives.json") {
		t.Errorf("missing not-archived message, got:\n%s", out)
	}

	// In DB but no hashfile (e.g. empty dir of a recursive archive).
	upsertEntry(t, w, goldenEntry(dir))
	out = captureStdout(t, func() {
		if err := w.Delete(context.Background(), []string{dir}, false); err != nil {
			t.Errorf("Delete: %v", err)
		}
	})
	if !strings.Contains(out, "There is no hashfile therefore cannot delete files in "+dir) {
		t.Errorf("missing no-hashfile message, got:\n%s", out)
	}
	if len(engine.Checks) != 0 {
		t.Error("verification ran despite missing prerequisites")
	}
	mustExist(t, filepath.Join(dir, "data.bin"))
}

func TestDeleteRecursiveSubfolderUsesParentEntry(t *testing.T) {
	w, engine := newTestWorkflow(t)
	parent := t.TempDir()
	sub := filepath.Join(parent, "sub")

	writeFile(t, filepath.Join(parent, "p.bin"), "p")
	writeFile(t, filepath.Join(parent, MD5SumFileName), "sums")
	writeFile(t, filepath.Join(sub, "s.bin"), "s")
	writeFile(t, filepath.Join(sub, MD5SumFileName), "sums")

	entry := goldenEntry(parent)
	entry.ArchiveMode = archivedb.ModeRecursive
	upsertEntry(t, w, entry)

	if err := w.Delete(context.Background(), []string{parent}, true); err != nil {
		t.Fatal(err)
	}

	if len(engine.Checks) != 2 {
		t.Fatalf("CheckMD5 called %d times, want 2", len(engine.Checks))
	}
	wantSubRemote := ":s3:froster-golden/froster" + parent + "/sub"
	if engine.Checks[1].Remote != wantSubRemote {
		t.Errorf("subfolder remote = %s, want %s", engine.Checks[1].Remote, wantSubRemote)
	}
	mustNotExist(t, filepath.Join(sub, "s.bin"))
	mustExist(t, filepath.Join(sub, WhereDidTheFilesGoFileName))

	manifest, _ := os.ReadFile(filepath.Join(sub, WhereDidTheFilesGoFileName))
	if !strings.Contains(string(manifest), `Restore command: froster restore "`+sub+`"`) {
		t.Errorf("subfolder manifest restore command wrong:\n%s", manifest)
	}
}
