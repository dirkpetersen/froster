package mount

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

// requireFuse skips the test unless the FUSE prerequisites (/dev/fuse and
// the fusermount3 helper) are present — the same runtime requirements as
// the rclone CLI and the Python implementation.
func requireFuse(t *testing.T) {
	t.Helper()
	if _, err := os.Stat("/dev/fuse"); err != nil {
		t.Skipf("/dev/fuse not available: %v", err)
	}
	if _, err := exec.LookPath("fusermount3"); err != nil {
		t.Skip("fusermount3 not in PATH")
	}
}

func TestMountLocalReadOnly(t *testing.T) {
	requireFuse(t)
	ctx := context.Background()

	src := t.TempDir()
	if err := os.WriteFile(filepath.Join(src, "hello.txt"), []byte("hello from fuse"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(src, "sub"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(src, "sub", "nested.txt"), []byte("nested"), 0o644); err != nil {
		t.Fatal(err)
	}
	mnt := t.TempDir()

	h, err := Mount(ctx, src, mnt, Options{})
	if err != nil {
		t.Fatalf("Mount: %v", err)
	}
	mounted := true
	defer func() {
		if mounted {
			_ = h.Unmount()
		}
	}()

	// Read a file through the FUSE mount.
	got, err := os.ReadFile(filepath.Join(mnt, "hello.txt"))
	if err != nil {
		t.Fatalf("read through mount: %v", err)
	}
	if string(got) != "hello from fuse" {
		t.Errorf("read %q, want %q", got, "hello from fuse")
	}
	if got, err := os.ReadFile(filepath.Join(mnt, "sub", "nested.txt")); err != nil || string(got) != "nested" {
		t.Errorf("nested read = %q, %v", got, err)
	}

	// The mount is read-only: writes must fail.
	if err := os.WriteFile(filepath.Join(mnt, "new.txt"), []byte("nope"), 0o644); err == nil {
		t.Error("write through read-only mount succeeded")
	}
	if err := os.Remove(filepath.Join(mnt, "hello.txt")); err == nil {
		t.Error("remove through read-only mount succeeded")
	}

	// Unmount and verify the mountpoint is empty again.
	if err := h.Unmount(); err != nil {
		t.Fatalf("Unmount: %v", err)
	}
	mounted = false
	if _, err := os.Stat(filepath.Join(mnt, "hello.txt")); err == nil {
		t.Error("hello.txt still visible after unmount")
	}
}

func TestExternalUnmount(t *testing.T) {
	requireFuse(t)
	ctx := context.Background()

	src := t.TempDir()
	if err := os.WriteFile(filepath.Join(src, "f"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	mnt := t.TempDir()

	h, err := Mount(ctx, src, mnt, Options{})
	if err != nil {
		t.Fatalf("Mount: %v", err)
	}

	// Unmount via the package-level fusermount3 path (what froster's
	// `umount` subcommand does for mounts owned by other processes),
	// and make sure the serving loop observes it.
	done := make(chan error, 1)
	go func() { done <- h.Wait() }()

	if err := Unmount(mnt); err != nil {
		_ = h.Unmount()
		t.Fatalf("Unmount(%s): %v", mnt, err)
	}
	select {
	case err := <-done:
		if err != nil {
			t.Errorf("Wait returned error after external unmount: %v", err)
		}
	case <-time.After(10 * time.Second):
		_ = h.Unmount()
		t.Fatal("Wait did not return within 10s of external unmount")
	}
}
