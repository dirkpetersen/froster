package workflow

import (
	"context"
	"crypto/md5" //nolint:gosec
	"encoding/hex"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/operations"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
	"github.com/dirkpetersen/froster/go/internal/logging"
	"github.com/dirkpetersen/froster/go/internal/transfer"
)

const (
	wfMinioContainer = "froster-go-workflow-minio"
	wfMinioPort      = "9401"
	wfMinioEndpoint  = "http://127.0.0.1:" + wfMinioPort
	wfMinioUser      = "minioadmin"
	wfMinioPass      = "minioadmin"
	wfMinioBucket    = "froster-workflow"
)

// startWorkflowMinio launches a throwaway Minio container, skipping when
// docker is unavailable. Any leftover container is removed first and the
// container is force-removed on cleanup.
func startWorkflowMinio(t *testing.T) {
	t.Helper()
	docker, err := exec.LookPath("docker")
	if err != nil {
		t.Skip("docker not available; skipping Minio workflow round-trip")
	}
	_ = exec.Command(docker, "rm", "-f", wfMinioContainer).Run()
	out, err := exec.Command(docker, "run", "-d", "--name", wfMinioContainer,
		"-p", wfMinioPort+":9000", "minio/minio", "server", "/data").CombinedOutput()
	if err != nil {
		t.Skipf("cannot start Minio container (%v): %s", err, out)
	}
	t.Cleanup(func() {
		if out, err := exec.Command(docker, "rm", "-f", wfMinioContainer).CombinedOutput(); err != nil {
			t.Logf("cleanup: docker rm -f %s: %v: %s", wfMinioContainer, err, out)
		}
	})
	deadline := time.Now().Add(60 * time.Second)
	for {
		resp, err := http.Get(wfMinioEndpoint + "/minio/health/live")
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				return
			}
		}
		if time.Now().After(deadline) {
			t.Skipf("Minio did not become healthy within 60s (last error: %v)", err)
		}
		time.Sleep(500 * time.Millisecond)
	}
}

// listRemoteObjects returns "relative path → size" for a froster remote.
func listRemoteObjects(t *testing.T, cfg transfer.S3Config, remote string) map[string]int64 {
	t.Helper()
	ctx := context.Background()
	target, err := transfer.ConnString(remote, cfg)
	if err != nil {
		t.Fatal(err)
	}
	f, err := fs.NewFs(ctx, target)
	if err != nil && err != fs.ErrorIsFile {
		t.Fatalf("NewFs(%s): %v", remote, err)
	}
	listing := map[string]int64{}
	err = operations.ListFn(ctx, f, func(o fs.Object) {
		listing[o.Remote()] = o.Size()
	})
	if err != nil {
		t.Fatalf("listing %s: %v", remote, err)
	}
	return listing
}

// md5OfFile hashes one local file.
func md5OfFile(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	sum := md5.Sum(data) //nolint:gosec
	return hex.EncodeToString(sum[:])
}

// TestMinioArchiveDeleteRestoreRoundTrip drives the real transfer engine
// through the full archive → verify → delete → restore cycle against a
// local Minio, asserting remote listings, artifact files, DB state, and
// bit-for-bit data equality after restore.
func TestMinioArchiveDeleteRestoreRoundTrip(t *testing.T) {
	if testing.Short() {
		t.Skip("short mode")
	}
	startWorkflowMinio(t)
	ctx := context.Background()

	s3cfg := transfer.S3Config{
		Provider:        "Minio",
		Endpoint:        wfMinioEndpoint,
		AccessKeyID:     wfMinioUser,
		SecretAccessKey: wfMinioPass,
		StorageClass:    "STANDARD",
	}
	db, err := archivedb.Load(filepath.Join(t.TempDir(), "froster-archives.json"))
	if err != nil {
		t.Fatal(err)
	}
	w := &Workflow{
		Log:          logging.New("", false),
		Engine:       transfer.New(s3cfg),
		DB:           db,
		Provider:     "Minio",
		Profile:      "profile minio",
		Credentials:  "minio",
		Endpoint:     wfMinioEndpoint,
		Bucket:       wfMinioBucket,
		ArchiveDir:   "froster",
		StorageClass: "STANDARD",
		Email:        "roundtrip@example.com",
		User:         "tester",
		Cores:        4,
	}

	// The golden-tree shape: big files, boundary files, tricky names, a
	// symlink, and a subfolder (recursive archive).
	root := filepath.Join(t.TempDir(), "tree")
	files := map[string]int{
		"big_alpha.dat":           2 * 1024 * 1024,
		"exactly_1mib.dat":        1024 * 1024,
		"just_under_1mib.dat":     1024*1024 - 1,
		"small_report.txt":        10240,
		"file with spaces.txt":    5120,
		"values,comma.csv":        4096,
		`quote"file.txt`:          3072,
		"sub_data/big_gamma.dat":  1536 * 1024,
		"sub_data/small_notes.md": 8192,
	}
	for name, size := range files {
		writeBytes(t, filepath.Join(root, name), size)
	}
	if err := os.Symlink("big_alpha.dat", filepath.Join(root, "sym.link")); err != nil {
		t.Fatal(err)
	}

	// Original checksums for the final bit-for-bit comparison.
	origSums := map[string]string{}
	for name := range files {
		origSums[name] = md5OfFile(t, filepath.Join(root, name))
	}

	// ---- ARCHIVE (recursive) --------------------------------------------
	if err := w.Archive(ctx, []string{root}, ArchiveOptions{Recursive: true}); err != nil {
		t.Fatalf("Archive: %v", err)
	}

	// DB: exactly one entry, keyed by the top folder.
	entries := w.DB.All()
	if len(entries) != 1 {
		t.Fatalf("DB has %d entries, want 1", len(entries))
	}
	entry := entries[0]
	wantArchiveFolder := ":s3:" + wfMinioBucket + "/froster" + root
	if entry.LocalFolder != root || entry.ArchiveFolder != wantArchiveFolder ||
		entry.ArchiveMode != archivedb.ModeRecursive || entry.S3StorageClass != "STANDARD" ||
		entry.Profile != "minio" || entry.Provider != "Minio" || entry.Endpoint != wfMinioEndpoint {
		t.Errorf("DB entry = %+v", entry)
	}

	// Remote layout: per-folder objects; small files only inside the tar;
	// md5sum files never uploaded; symlink as .rclonelink.
	rootListing := listRemoteObjects(t, s3cfg, wantArchiveFolder)
	var rootObjects []string
	for name := range rootListing {
		if !strings.Contains(name, "/") {
			rootObjects = append(rootObjects, name)
		}
	}
	sort.Strings(rootObjects)
	// Note: the symlink is tarred (its lstat size is tiny), so no
	// .rclonelink object appears — --links only matters for symlinks that
	// survive tarring.
	wantRootObjects := []string{
		AllfilesCSVFileName, SmallfilesTarFileName,
		"big_alpha.dat", "exactly_1mib.dat",
	}
	sort.Strings(wantRootObjects)
	if strings.Join(rootObjects, "|") != strings.Join(wantRootObjects, "|") {
		t.Errorf("root remote objects = %v, want %v", rootObjects, wantRootObjects)
	}
	if _, ok := rootListing["sub_data/big_gamma.dat"]; !ok {
		t.Error("recursive archive did not upload sub_data/big_gamma.dat")
	}
	if _, ok := rootListing["sub_data/"+SmallfilesTarFileName]; !ok {
		t.Error("recursive archive did not tar+upload sub_data small files")
	}
	if _, ok := rootListing[MD5SumFileName]; ok {
		t.Error(".froster.md5sum was uploaded (must stay local)")
	}

	// Local artifacts after archive: hashfile + allfiles.csv + tar remain,
	// small files gone.
	mustExist(t, filepath.Join(root, MD5SumFileName))
	mustExist(t, filepath.Join(root, AllfilesCSVFileName))
	mustExist(t, filepath.Join(root, SmallfilesTarFileName))
	mustNotExist(t, filepath.Join(root, "small_report.txt"))
	mustExist(t, filepath.Join(root, "exactly_1mib.dat")) // boundary: not tarred

	// Re-archiving without --force refuses (already archived).
	if err := w.Archive(ctx, []string{root}, ArchiveOptions{Recursive: true}); err == nil {
		t.Error("re-archive without --force succeeded, want refusal")
	}

	// ---- DELETE (recursive) ---------------------------------------------
	if err := w.Delete(ctx, []string{root}, true); err != nil {
		t.Fatalf("Delete: %v", err)
	}
	// Only the keepers survive locally, in both folders.
	for _, dir := range []string{root, filepath.Join(root, "sub_data")} {
		names, err := topFiles(dir)
		if err != nil {
			t.Fatal(err)
		}
		sort.Strings(names)
		want := []string{MD5SumFileName, AllfilesCSVFileName, WhereDidTheFilesGoFileName}
		sort.Strings(want)
		if strings.Join(names, "|") != strings.Join(want, "|") {
			t.Errorf("%s after delete = %v, want %v", dir, names, want)
		}
	}
	manifest, err := os.ReadFile(filepath.Join(root, WhereDidTheFilesGoFileName))
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{
		"The files in this folder have been moved to an AWS S3 archive!",
		"Archive location: " + wantArchiveFolder,
		"S3 storage class: STANDARD",
		"Archive aws profile: minio",
		"Archiver email: roundtrip@example.com",
		`Restore command: froster restore "` + root + `"`,
	} {
		if !strings.Contains(string(manifest), want) {
			t.Errorf("manifest missing %q:\n%s", want, manifest)
		}
	}

	// ---- RESTORE (recursive) --------------------------------------------
	if err := w.Restore(ctx, []string{root}, RestoreOptions{Recursive: true, Days: 30, RetrieveOpt: "Bulk"}); err != nil {
		t.Fatalf("Restore: %v", err)
	}

	// Every original file is back, bit for bit.
	for name, wantSum := range origSums {
		path := filepath.Join(root, name)
		if _, err := os.Stat(path); err != nil {
			t.Errorf("restored file missing: %s", name)
			continue
		}
		if got := md5OfFile(t, path); got != wantSum {
			t.Errorf("restored %s differs from original", name)
		}
	}
	// The symlink went through the tar and comes back as a real symlink.
	if target, err := os.Readlink(filepath.Join(root, "sym.link")); err != nil || target != "big_alpha.dat" {
		t.Errorf("restored symlink = %q, %v; want big_alpha.dat", target, err)
	}
	// Tar untarred + removed; manifest removed; both md5 files remain.
	mustNotExist(t, filepath.Join(root, SmallfilesTarFileName))
	mustNotExist(t, filepath.Join(root, WhereDidTheFilesGoFileName))
	mustNotExist(t, filepath.Join(root, "sub_data", WhereDidTheFilesGoFileName))
	mustExist(t, filepath.Join(root, MD5SumFileName))
	mustExist(t, filepath.Join(root, MD5SumRestoredFileName))
	mustExist(t, filepath.Join(root, "sub_data", MD5SumRestoredFileName))

	// The restored hash file covers the same set as the archive-side one.
	parse := func(path string) map[string]string {
		sums := map[string]string{}
		for _, line := range readLines(t, path) {
			if i := strings.Index(line, "  "); i > 0 {
				sums[line[i+2:]] = line[:i]
			}
		}
		return sums
	}
	arch := parse(filepath.Join(root, MD5SumFileName))
	rest := parse(filepath.Join(root, MD5SumRestoredFileName))
	for name, sum := range arch {
		if name == AllfilesCSVFileName {
			continue // its md5 embeds atimes; presence is enough
		}
		if rest[name] != sum {
			t.Errorf("restored md5 for %s = %s, want %s", name, rest[name], sum)
		}
	}
}
