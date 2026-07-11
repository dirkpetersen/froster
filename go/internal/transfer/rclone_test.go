package transfer

import (
	"context"
	"crypto/md5"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// writeFile creates path (and parent dirs) with the given content.
func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

// writeMD5SumFile writes a md5sum-format file listing the given
// relative-path → content pairs.
func writeMD5SumFile(t *testing.T, path string, files map[string]string) {
	t.Helper()
	var sb strings.Builder
	for name, content := range files {
		fmt.Fprintf(&sb, "%x  %s\n", md5.Sum([]byte(content)), name)
	}
	writeFile(t, path, sb.String())
}

func TestVersion(t *testing.T) {
	v := New(S3Config{}).Version()
	if !strings.HasPrefix(v, "v1.") {
		t.Errorf("unexpected rclone version %q", v)
	}
}

func TestCopyDirLocal(t *testing.T) {
	ctx := context.Background()
	src, dst := t.TempDir(), t.TempDir()
	writeFile(t, filepath.Join(src, "a.txt"), "hello")
	writeFile(t, filepath.Join(src, "sub", "b.txt"), "world!")

	e := New(S3Config{})
	var progressCalls int
	stats, err := e.Copy(ctx, src, dst, CopyOptions{
		Transfers: 2,
		Checkers:  1,
		Progress:  func(Stats) { progressCalls++ },
	})
	if err != nil {
		t.Fatalf("Copy: %v", err)
	}
	if stats.Transfers != 2 {
		t.Errorf("Transfers = %d, want 2", stats.Transfers)
	}
	if stats.Bytes != int64(len("hello")+len("world!")) {
		t.Errorf("Bytes = %d, want 11", stats.Bytes)
	}
	if progressCalls == 0 {
		t.Error("Progress callback never invoked")
	}
	for name, want := range map[string]string{"a.txt": "hello", "sub/b.txt": "world!"} {
		got, err := os.ReadFile(filepath.Join(dst, name))
		if err != nil || string(got) != want {
			t.Errorf("dst/%s = %q, %v; want %q", name, got, err, want)
		}
	}
}

func TestCopyMaxDepth(t *testing.T) {
	ctx := context.Background()
	src, dst := t.TempDir(), t.TempDir()
	writeFile(t, filepath.Join(src, "top.txt"), "top")
	writeFile(t, filepath.Join(src, "sub", "deep.txt"), "deep")

	if _, err := New(S3Config{}).Copy(ctx, src, dst, CopyOptions{MaxDepth: 1}); err != nil {
		t.Fatalf("Copy: %v", err)
	}
	if _, err := os.Stat(filepath.Join(dst, "top.txt")); err != nil {
		t.Errorf("top.txt missing: %v", err)
	}
	if _, err := os.Stat(filepath.Join(dst, "sub", "deep.txt")); err == nil {
		t.Error("sub/deep.txt copied despite MaxDepth 1")
	}
}

func TestCopyExcludes(t *testing.T) {
	ctx := context.Background()
	src, dst := t.TempDir(), t.TempDir()
	writeFile(t, filepath.Join(src, "data.bin"), "data")
	writeFile(t, filepath.Join(src, ".froster.md5sum"), "sums")
	writeFile(t, filepath.Join(src, "Where-did-the-files-go.txt"), "manifest")

	_, err := New(S3Config{}).Copy(ctx, src, dst, CopyOptions{
		Exclude: []string{".froster.md5sum", "Where-did-the-files-go.txt"},
	})
	if err != nil {
		t.Fatalf("Copy: %v", err)
	}
	if _, err := os.Stat(filepath.Join(dst, "data.bin")); err != nil {
		t.Errorf("data.bin missing: %v", err)
	}
	for _, name := range []string{".froster.md5sum", "Where-did-the-files-go.txt"} {
		if _, err := os.Stat(filepath.Join(dst, name)); err == nil {
			t.Errorf("%s copied despite exclude", name)
		}
	}
}

func TestCopySingleFile(t *testing.T) {
	ctx := context.Background()
	src, dst := t.TempDir(), t.TempDir()
	writeFile(t, filepath.Join(src, "only.csv"), "1,2,3")

	if _, err := New(S3Config{}).Copy(ctx, filepath.Join(src, "only.csv"), dst, CopyOptions{}); err != nil {
		t.Fatalf("Copy: %v", err)
	}
	got, err := os.ReadFile(filepath.Join(dst, "only.csv"))
	if err != nil || string(got) != "1,2,3" {
		t.Errorf("dst/only.csv = %q, %v", got, err)
	}
}

func TestCopyLinks(t *testing.T) {
	ctx := context.Background()
	src := t.TempDir()
	writeFile(t, filepath.Join(src, "real.txt"), "real")
	if err := os.Symlink("real.txt", filepath.Join(src, "link.txt")); err != nil {
		t.Fatal(err)
	}

	// Without Links symlinks are skipped (like rclone without --links).
	dst1 := t.TempDir()
	if _, err := New(S3Config{}).Copy(ctx, src, dst1, CopyOptions{}); err != nil {
		t.Fatalf("Copy: %v", err)
	}
	if _, err := os.Lstat(filepath.Join(dst1, "link.txt")); err == nil {
		t.Error("symlink copied without Links option")
	}

	// With Links the symlink is transferred (local→local round-trips the
	// .rclonelink representation back to a symlink).
	dst2 := t.TempDir()
	if _, err := New(S3Config{}).Copy(ctx, src, dst2, CopyOptions{Links: true}); err != nil {
		t.Fatalf("Copy with Links: %v", err)
	}
	fi, err := os.Lstat(filepath.Join(dst2, "link.txt"))
	if err != nil {
		t.Fatalf("link.txt missing with Links option: %v", err)
	}
	if fi.Mode()&os.ModeSymlink == 0 {
		t.Errorf("link.txt is not a symlink: mode %v", fi.Mode())
	}
}

func TestCheckMD5Local(t *testing.T) {
	ctx := context.Background()
	dir := t.TempDir()
	files := map[string]string{
		"f1.dat":     "contents one",
		"sub/f2.dat": "contents two",
	}
	for name, content := range files {
		writeFile(t, filepath.Join(dir, name), content)
	}
	sumsDir := t.TempDir()

	e := New(S3Config{})

	good := filepath.Join(sumsDir, "good.md5")
	writeMD5SumFile(t, good, files)
	if err := e.CheckMD5(ctx, good, dir, CheckOptions{Checkers: 2}); err != nil {
		t.Errorf("CheckMD5 with matching sums: %v", err)
	}

	// A corrupted expectation must fail.
	bad := filepath.Join(sumsDir, "bad.md5")
	writeMD5SumFile(t, bad, map[string]string{
		"f1.dat":     "contents one",
		"sub/f2.dat": "CORRUPTED expectation",
	})
	if err := e.CheckMD5(ctx, bad, dir, CheckOptions{}); err == nil {
		t.Error("CheckMD5 with corrupted sum succeeded, want error")
	}

	// A file listed in the sums but missing from the remote must fail.
	missing := filepath.Join(sumsDir, "missing.md5")
	writeMD5SumFile(t, missing, map[string]string{
		"f1.dat":     "contents one",
		"sub/f2.dat": "contents two",
		"ghost.dat":  "not there",
	})
	if err := e.CheckMD5(ctx, missing, dir, CheckOptions{}); err == nil {
		t.Error("CheckMD5 with missing file succeeded, want error")
	}

	// MaxDepth 1 restricts the check to top-level files (froster's usage).
	top := filepath.Join(sumsDir, "top.md5")
	writeMD5SumFile(t, top, map[string]string{"f1.dat": "contents one"})
	if err := e.CheckMD5(ctx, top, dir, CheckOptions{MaxDepth: 1, Checkers: 1}); err != nil {
		t.Errorf("CheckMD5 with MaxDepth 1: %v", err)
	}
	// ...and without MaxDepth the same sums file fails (sub/f2.dat is
	// on the remote but not in the sums).
	if err := e.CheckMD5(ctx, top, dir, CheckOptions{}); err == nil {
		t.Error("CheckMD5 without MaxDepth ignored extra remote file, want error")
	}
}
