package workflow

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
	"github.com/dirkpetersen/froster/go/internal/transfer"
)

// fakeGlacier scripts TriggerGlacierRestore results.
type fakeGlacier struct {
	res   GlacierResult
	err   error
	calls []struct {
		Bucket, Prefix, Tier string
		Days                 int32
	}
}

func (f *fakeGlacier) TriggerGlacierRestore(bucket, prefix string, days int32, tier string) (GlacierResult, error) {
	f.calls = append(f.calls, struct {
		Bucket, Prefix, Tier string
		Days                 int32
	}{bucket, prefix, tier, days})
	return f.res, f.err
}

// simulateArchiveRemote makes engine.Copy materialize a downloaded folder:
// data file + tar + hashfile-compatible content.
func downloadSimulator(t *testing.T, files map[string]string) func(src, dst string, opts transfer.CopyOptions) error {
	return func(src, dst string, opts transfer.CopyOptions) error {
		if !strings.HasPrefix(src, ":s3:") {
			return nil // upload, ignore
		}
		for name, content := range files {
			writeFile(t, filepath.Join(dst, name), content)
		}
		return nil
	}
}

func TestRestoreLeftoverFilesGate(t *testing.T) {
	w, engine := newTestWorkflow(t)
	dir := t.TempDir()
	// Folder was archived but never deleted: real files still present.
	writeFile(t, filepath.Join(dir, "data.bin"), "still here")
	writeFile(t, filepath.Join(dir, MD5SumFileName), "sums")
	upsertEntry(t, w, goldenEntry(dir))

	out := captureStdout(t, func() {
		if err := w.Restore(context.Background(), []string{dir}, RestoreOptions{Days: 30, RetrieveOpt: "Bulk"}); err != nil {
			t.Errorf("Restore: %v", err)
		}
	})
	for _, want := range []string{
		"\nWARNING: Folder " + dir + " \n", // trailing space is Python-exact
		"    contains files in addition to Froster meta data.\n",
		"Has this folder been deleted using \"froster delete\" command?.",
		"Please empty the folder before restoring.",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("output missing %q:\n%s", want, out)
		}
	}
	if len(engine.Copies) != 0 {
		t.Error("download happened despite leftover files")
	}

	// A leftover Froster.smallfiles.tar alone also triggers the gate
	// (it is not in dirmetafiles).
	dir2 := t.TempDir()
	writeFile(t, filepath.Join(dir2, SmallfilesTarFileName), "tar")
	upsertEntry(t, w, goldenEntry(dir2))
	out = captureStdout(t, func() {
		if err := w.Restore(context.Background(), []string{dir2}, RestoreOptions{}); err != nil {
			t.Errorf("Restore: %v", err)
		}
	})
	if !strings.Contains(out, "WARNING: Folder "+dir2) {
		t.Errorf("tar-only folder passed the gate:\n%s", out)
	}
}

func TestRestoreNotArchived(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()

	out := captureStdout(t, func() {
		if err := w.Restore(context.Background(), []string{dir}, RestoreOptions{}); err != nil {
			t.Errorf("Restore: %v", err)
		}
	})
	if !strings.Contains(out, "Folder "+dir+" is not archived") ||
		!strings.Contains(out, "No entry found in froster-archives.json") {
		t.Errorf("missing not-archived message:\n%s", out)
	}
}

func TestRestoreNonGlacierDownloadsAndVerifies(t *testing.T) {
	w, engine := newTestWorkflow(t)
	dir := t.TempDir()
	// Deleted state: only keepers on disk.
	writeFile(t, filepath.Join(dir, MD5SumFileName), "sums")
	writeFile(t, filepath.Join(dir, AllfilesCSVFileName), "csv")
	writeFile(t, filepath.Join(dir, WhereDidTheFilesGoFileName), "manifest")
	upsertEntry(t, w, goldenEntry(dir))

	// The "download" materializes a data file and a smallfiles tar.
	tarDir := t.TempDir()
	writeFile(t, filepath.Join(tarDir, "tiny.txt"), "tiny payload")
	wTmp := &Workflow{Log: w.Log}
	if err := wTmp.genAllfilesAndTar(tarDir, 1024, true); err != nil {
		t.Fatal(err)
	}
	tarBytes, err := os.ReadFile(filepath.Join(tarDir, SmallfilesTarFileName))
	if err != nil {
		t.Fatal(err)
	}
	engine.OnCopy = downloadSimulator(t, map[string]string{
		"restored.bin":        "restored contents",
		SmallfilesTarFileName: string(tarBytes),
	})

	out := captureStdout(t, func() {
		if err := w.Restore(context.Background(), []string{dir}, RestoreOptions{Days: 30, RetrieveOpt: "Bulk"}); err != nil {
			t.Errorf("Restore: %v", err)
		}
	})

	if !strings.Contains(out, "\nRESTORING \""+dir+"\"\n") ||
		!strings.Contains(out, "...no glacier restore needed") {
		t.Errorf("missing restore headers:\n%s", out)
	}

	// Download call: remote prefix ends with '/', MaxDepth 1, no Links.
	if len(engine.Copies) != 1 {
		t.Fatalf("Copy called %d times, want 1", len(engine.Copies))
	}
	dl := engine.Copies[0]
	wantSrc := ":s3:froster-golden/froster" + dir + "/"
	if dl.Src != wantSrc || dl.Dst != dir {
		t.Errorf("download = %s -> %s, want %s -> %s", dl.Src, dl.Dst, wantSrc, dir)
	}
	if dl.Opts.MaxDepth != 1 || dl.Opts.Links {
		t.Errorf("download opts = %+v", dl.Opts)
	}

	// Verification used a fresh .froster-restored.md5sum against the remote.
	if len(engine.Checks) != 1 {
		t.Fatalf("CheckMD5 called %d times, want 1", len(engine.Checks))
	}
	if chk := engine.Checks[0]; chk.MD5File != filepath.Join(dir, MD5SumRestoredFileName) || chk.Remote != wantSrc {
		t.Errorf("verify call = %+v", chk)
	}

	// Post-conditions: tar untarred + removed, manifest removed,
	// restored hashfile kept, completion message printed.
	mustExist(t, filepath.Join(dir, "restored.bin"))
	mustExist(t, filepath.Join(dir, "tiny.txt"))
	mustNotExist(t, filepath.Join(dir, SmallfilesTarFileName))
	mustNotExist(t, filepath.Join(dir, WhereDidTheFilesGoFileName))
	mustExist(t, filepath.Join(dir, MD5SumRestoredFileName))
	if !strings.Contains(out, "RESTORATION OF "+dir+" COMPLETED SUCCESSFULLY") {
		t.Errorf("missing completion message:\n%s", out)
	}
}

func TestRestoreGlacierPendingSchedulesRetries(t *testing.T) {
	w, engine := newTestWorkflow(t)
	w.StorageClass = "DEEP_ARCHIVE"
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, MD5SumFileName), "sums")
	entry := goldenEntry(dir)
	entry.S3StorageClass = "DEEP_ARCHIVE"
	upsertEntry(t, w, entry)

	glacier := &fakeGlacier{res: GlacierResult{Triggered: []string{"a", "b"}}}
	w.Glacier = glacier
	w.SlurmInstalled = func() bool { return true }
	var scheduled []string
	w.ScheduleRestore = func(s string) { scheduled = append(scheduled, s) }

	out := captureStdout(t, func() {
		if err := w.Restore(context.Background(), []string{dir}, RestoreOptions{Days: 30, RetrieveOpt: "Bulk"}); err != nil {
			t.Errorf("Restore: %v", err) // pending glacier still exits 0
		}
	})

	if len(glacier.calls) != 1 {
		t.Fatalf("TriggerGlacierRestore called %d times", len(glacier.calls))
	}
	call := glacier.calls[0]
	if call.Bucket != "froster-golden" || call.Prefix != "froster"+dir+"/" ||
		call.Days != 30 || call.Tier != "Bulk" {
		t.Errorf("glacier call = %+v", call)
	}

	for _, want := range []string{
		"    Triggered Glacier retrievals: 2",
		"    Currently retrieving from Glacier: 0",
		"    Retrieved from Glacier: 0",
		"    Not in Glacier: 0",
		"    Restore option not supported: 0",
		"Glacier retrievals pending. Depending on the storage class and restore mode run this command again in:",
		"        Expedited mode: ~ 5 minutes (DEEP_ARCHIVE not supported)",
		"        Standard mode: ~ 12 hours",
		"        Bulk mode: ~ 48 hours",
		"        NOTE: You can check more accurate times in the AWS S3 console",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("output missing %q:\n%s", want, out)
		}
	}

	if strings.Join(scheduled, ",") != "now+12hours,now+24hours,now+48hours" {
		t.Errorf("scheduled = %v", scheduled)
	}
	if len(engine.Copies) != 0 {
		t.Error("download happened despite pending glacier retrieval")
	}

	// With --no-slurm no retries are scheduled.
	scheduled = nil
	if err := w.Restore(context.Background(), []string{dir}, RestoreOptions{Days: 30, RetrieveOpt: "Bulk", NoSlurm: true}); err != nil {
		t.Fatal(err)
	}
	if len(scheduled) != 0 {
		t.Errorf("retries scheduled despite --no-slurm: %v", scheduled)
	}
}

func TestRestoreGlacierThawedNoDownloadFlag(t *testing.T) {
	w, engine := newTestWorkflow(t)
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, MD5SumFileName), "sums")
	entry := goldenEntry(dir)
	entry.S3StorageClass = "GLACIER"
	upsertEntry(t, w, entry)

	w.Glacier = &fakeGlacier{res: GlacierResult{Restored: []string{"x"}}}

	out := captureStdout(t, func() {
		// DOCUMENTED DEVIATION: Python exits 1 here despite success; Go
		// returns nil.
		if err := w.Restore(context.Background(), []string{dir}, RestoreOptions{Days: 30, RetrieveOpt: "Bulk", NoDownload: true}); err != nil {
			t.Errorf("Restore --no-download: %v", err)
		}
	})
	if !strings.Contains(out, "\nFolder restored but not downloaded (--no-download flag set)\n") {
		t.Errorf("missing no-download message:\n%s", out)
	}
	if len(engine.Copies) != 0 {
		t.Error("download happened despite --no-download")
	}
}

func TestRestoreRecursiveWalksSubfolders(t *testing.T) {
	w, engine := newTestWorkflow(t)
	parent := t.TempDir()
	sub := filepath.Join(parent, "sub_data")
	writeFile(t, filepath.Join(parent, MD5SumFileName), "sums")
	writeFile(t, filepath.Join(sub, MD5SumFileName), "sums")

	entry := goldenEntry(parent)
	entry.ArchiveMode = archivedb.ModeRecursive
	upsertEntry(t, w, entry)

	engine.OnCopy = downloadSimulator(t, map[string]string{"f.bin": "restored"})

	if err := w.Restore(context.Background(), []string{parent}, RestoreOptions{Recursive: true}); err != nil {
		t.Fatal(err)
	}

	if len(engine.Copies) != 2 {
		t.Fatalf("Copy called %d times, want 2 (parent + sub)", len(engine.Copies))
	}
	wantSub := ":s3:froster-golden/froster" + sub + "/"
	if engine.Copies[1].Src != wantSub {
		t.Errorf("sub download src = %s, want %s", engine.Copies[1].Src, wantSub)
	}
	mustExist(t, filepath.Join(sub, "f.bin"))
}

func TestRestoreCreatesMissingFolder(t *testing.T) {
	w, engine := newTestWorkflow(t)
	base := t.TempDir()
	dir := filepath.Join(base, "gone")
	upsertEntry(t, w, goldenEntry(dir))
	engine.OnCopy = downloadSimulator(t, map[string]string{"back.bin": "data"})

	if err := w.Restore(context.Background(), []string{dir}, RestoreOptions{}); err != nil {
		t.Fatal(err)
	}
	mustExist(t, filepath.Join(dir, "back.bin"))
}
