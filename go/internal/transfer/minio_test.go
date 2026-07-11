package transfer

import (
	"context"
	"crypto/md5"
	"crypto/rand"
	"fmt"
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
)

const (
	minioContainer = "froster-go-transfer-minio"
	minioPort      = "9101"
	minioEndpoint  = "http://127.0.0.1:" + minioPort
	minioUser      = "minioadmin"
	minioPass      = "minioadmin"
)

// startMinio launches a throwaway Minio container for the test, skipping
// the test when docker (or the Minio image/registry) is unavailable. The
// container is force-removed on cleanup and any leftover from a prior run
// is removed first.
func startMinio(t *testing.T) {
	t.Helper()
	docker, err := exec.LookPath("docker")
	if err != nil {
		t.Skip("docker not available; skipping Minio integration test")
	}

	// Remove any leftover container from a previous (crashed) run.
	_ = exec.Command(docker, "rm", "-f", minioContainer).Run()

	out, err := exec.Command(docker, "run", "-d", "--name", minioContainer,
		"-p", minioPort+":9000", "minio/minio", "server", "/data").CombinedOutput()
	if err != nil {
		t.Skipf("cannot start Minio container (%v): %s", err, out)
	}
	t.Cleanup(func() {
		if out, err := exec.Command(docker, "rm", "-f", minioContainer).CombinedOutput(); err != nil {
			t.Logf("cleanup: docker rm -f %s: %v: %s", minioContainer, err, out)
		}
	})

	// Wait for the S3 API to come up.
	deadline := time.Now().Add(60 * time.Second)
	for {
		resp, err := http.Get(minioEndpoint + "/minio/health/live")
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

func minioConfig() S3Config {
	return S3Config{
		Provider:        "Minio",
		Endpoint:        minioEndpoint,
		AccessKeyID:     minioUser,
		SecretAccessKey: minioPass,
	}
}

// listRemote returns the recursive "path → size" listing of a remote.
func listRemote(t *testing.T, e *Rclone, remote string) map[string]int64 {
	t.Helper()
	ctx := context.Background()
	target, err := ConnString(remote, e.cfg)
	if err != nil {
		t.Fatal(err)
	}
	f, err := fs.NewFs(ctx, target)
	if err != nil {
		t.Fatal(err)
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

func TestMinioEndToEnd(t *testing.T) {
	if testing.Short() {
		t.Skip("short mode")
	}
	startMinio(t)
	ctx := context.Background()
	e := New(minioConfig())

	// Build a source tree resembling a froster archive folder: text
	// files, a multi-MiB binary, a symlink, a subdirectory, and the
	// artifacts froster excludes from upload.
	src := t.TempDir()
	binary := make([]byte, 3<<20)
	if _, err := rand.Read(binary); err != nil {
		t.Fatal(err)
	}
	files := map[string]string{
		"a.txt":      "alpha contents",
		"b.dat":      string(binary),
		"sub/c.txt":  "nested contents",
		"linked.txt": "link target contents",
	}
	for name, content := range files {
		writeFile(t, filepath.Join(src, name), content)
	}
	if err := os.Symlink("linked.txt", filepath.Join(src, "sym")); err != nil {
		t.Fatal(err)
	}
	writeFile(t, filepath.Join(src, ".froster.md5sum"), "local only")
	writeFile(t, filepath.Join(src, "Froster.allfiles.csv"), "csv,data")
	writeFile(t, filepath.Join(src, "Where-did-the-files-go.txt"), "manifest")

	remote := ":s3:froster-spike/archive/test1"

	// Upload with froster's real flag set: storage class, --links,
	// --transfers/--checkers/--multi-thread-streams, excludes. (No
	// MaxDepth here so the whole tree goes up in one call; froster
	// itself recurses per directory with MaxDepth 1, covered below.)
	var progressSeen bool
	stats, err := e.Copy(ctx, src, remote, CopyOptions{
		StorageClass:       "STANDARD",
		Links:              true,
		Transfers:          4,
		Checkers:           2,
		MultiThreadStreams: 4,
		Exclude: []string{
			".froster.md5sum", ".froster-restored.md5sum",
			"Froster.allfiles.csv", "Where-did-the-files-go.txt",
		},
		Progress:         func(Stats) { progressSeen = true },
		ProgressInterval: 50 * time.Millisecond,
	})
	if err != nil {
		t.Fatalf("Copy to Minio: %v", err)
	}
	if stats.Errors != 0 {
		t.Errorf("copy stats report %d errors (last: %s)", stats.Errors, stats.LastError)
	}
	if !progressSeen {
		t.Error("no progress callback during upload")
	}

	// List the remote and verify exactly the expected objects arrived
	// (symlink as sym.rclonelink, excluded artifacts absent).
	listing := listRemote(t, e, remote)
	wantObjects := []string{"a.txt", "b.dat", "linked.txt", "sub/c.txt", "sym.rclonelink"}
	var gotObjects []string
	for name := range listing {
		gotObjects = append(gotObjects, name)
	}
	sort.Strings(gotObjects)
	if strings.Join(gotObjects, ",") != strings.Join(wantObjects, ",") {
		t.Errorf("remote listing = %v, want %v", gotObjects, wantObjects)
	}
	if listing["b.dat"] != int64(len(binary)) {
		t.Errorf("b.dat size = %d, want %d", listing["b.dat"], len(binary))
	}

	// The separate Froster.allfiles.csv upload froster performs (single
	// local file, different storage class).
	if _, err := e.Copy(ctx, filepath.Join(src, "Froster.allfiles.csv"), remote, CopyOptions{
		StorageClass: "STANDARD", // INTELLIGENT_TIERING on AWS; Minio only accepts STANDARD/REDUCED_REDUNDANCY
	}); err != nil {
		t.Fatalf("Copy Froster.allfiles.csv: %v", err)
	}
	if listing := listRemote(t, e, remote); listing["Froster.allfiles.csv"] == 0 {
		t.Error("Froster.allfiles.csv missing after single-file copy")
	}

	// CheckMD5 must pass against correct expectations. The .rclonelink
	// object's content is the symlink target path.
	sums := map[string]string{}
	for name, content := range files {
		sums[name] = content
	}
	sums["sym.rclonelink"] = "linked.txt"
	sums["Froster.allfiles.csv"] = "csv,data"
	sumsDir := t.TempDir()
	good := filepath.Join(sumsDir, "good.md5")
	writeMD5SumFile(t, good, sums)
	if err := e.CheckMD5(ctx, good, remote, CheckOptions{Checkers: 2}); err != nil {
		t.Errorf("CheckMD5 against Minio with correct sums: %v", err)
	}

	// Corrupt one expectation: CheckMD5 must fail.
	sums["a.txt"] = "corrupted expectation"
	bad := filepath.Join(sumsDir, "bad.md5")
	writeMD5SumFile(t, bad, sums)
	if err := e.CheckMD5(ctx, bad, remote, CheckOptions{}); err == nil {
		t.Error("CheckMD5 with corrupted sum passed, want error")
	} else {
		t.Logf("CheckMD5 corrupt-expectation error (expected): %v", err)
	}

	// froster's actual per-directory pattern: MaxDepth 1 upload and
	// MaxDepth 1 verification of a prefix.
	remoteTop := ":s3:froster-spike/archive/test2"
	if _, err := e.Copy(ctx, src, remoteTop, CopyOptions{
		StorageClass: "STANDARD",
		MaxDepth:     1,
		Exclude:      []string{".froster.md5sum", "Froster.allfiles.csv", "Where-did-the-files-go.txt"},
	}); err != nil {
		t.Fatalf("Copy MaxDepth 1: %v", err)
	}
	topListing := listRemote(t, e, remoteTop)
	if _, ok := topListing["sub/c.txt"]; ok {
		t.Error("sub/c.txt uploaded despite MaxDepth 1")
	}
	topSums := filepath.Join(sumsDir, "top.md5")
	writeMD5SumFile(t, topSums, map[string]string{
		"a.txt":      "alpha contents",
		"b.dat":      string(binary),
		"linked.txt": "link target contents",
	})
	if err := e.CheckMD5(ctx, topSums, remoteTop, CheckOptions{MaxDepth: 1, Checkers: 1}); err != nil {
		t.Errorf("CheckMD5 MaxDepth 1: %v", err)
	}

	// Round-trip: restore (download) without Links, then compare bytes.
	restored := t.TempDir()
	if _, err := e.Copy(ctx, remote, restored, CopyOptions{Transfers: 4}); err != nil {
		t.Fatalf("Copy from Minio: %v", err)
	}
	for name, content := range files {
		got, err := os.ReadFile(filepath.Join(restored, name))
		if err != nil {
			t.Errorf("restored %s: %v", name, err)
			continue
		}
		if fmt.Sprintf("%x", md5.Sum(got)) != fmt.Sprintf("%x", md5.Sum([]byte(content))) {
			t.Errorf("restored %s differs from original", name)
		}
	}
	// Without Links on download, the symlink comes back as a literal
	// .rclonelink file — matching Python froster, which restores
	// without --links.
	if _, err := os.Lstat(filepath.Join(restored, "sym.rclonelink")); err != nil {
		t.Errorf("expected literal sym.rclonelink after restore without Links: %v", err)
	}
}
