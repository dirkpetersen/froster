// Package mount provides read-only FUSE mounts of froster remotes using
// rclone's VFS and cmd/mountlib with the pure-Go go-fuse backend (mount2).
// It reproduces the Python implementation's invocation
//
//	rclone mount --allow-non-empty --default-permissions --read-only --no-checksum <remote> <mountpoint>
//
// in-process. Like the CLI, it requires /dev/fuse and (for Unmount of
// foreign mounts) the fusermount3 helper at runtime.
package mount

import (
	"context"
	"errors"
	"fmt"
	"os/exec"
	"time"

	"github.com/rclone/rclone/cmd/mountlib"
	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/vfs/vfscommon"

	// Register the go-fuse (pure Go, no CGO) mount backend as "mount2".
	_ "github.com/rclone/rclone/cmd/mount2"

	"github.com/dirkpetersen/froster/go/internal/transfer"
)

// mountMethod is the rclone mount backend to use; "mount2" is the go-fuse
// implementation registered by the cmd/mount2 import above.
const mountMethod = "mount2"

// defaultReadyTimeout bounds how long Mount waits for the kernel mount to
// appear in /proc/self/mountinfo before giving up.
const defaultReadyTimeout = 10 * time.Second

// Options configures Mount. The froster flag set (--allow-non-empty,
// --default-permissions, --read-only, --no-checksum) is always applied and
// is not configurable, matching the Python implementation.
type Options struct {
	// S3 supplies the credentials/endpoint/provider for ":s3:bucket/prefix"
	// remotes. It is unused for local-path remotes.
	S3 transfer.S3Config
	// ReadyTimeout is how long to wait for the mount to become ready;
	// zero means 10s.
	ReadyTimeout time.Duration
}

// Handle is a live in-process FUSE mount.
type Handle struct {
	mp *mountlib.MountPoint
}

// Mount mounts remote (a froster ":s3:bucket/prefix" remote or a local
// path) read-only at mountpoint and returns once the kernel mount is ready.
// The serving loop runs on background goroutines; call Handle.Unmount to
// stop it, or Handle.Wait to block until it is unmounted externally.
func Mount(ctx context.Context, remote, mountpoint string, opts Options) (*Handle, error) {
	transfer.Initialize()

	target, err := transfer.ConnString(remote, opts.S3)
	if err != nil {
		return nil, err
	}
	f, err := fs.NewFs(ctx, target)
	if err != nil {
		return nil, fmt.Errorf("remote %q: %w", remote, err)
	}

	_, mountFn := mountlib.ResolveMountMethod(mountMethod)
	if mountFn == nil {
		return nil, errors.New("no FUSE mount backend available (mount2 not registered)")
	}

	// Start from the registered defaults (which include RCLONE_* env
	// overrides), then apply froster's fixed flag set.
	mountOpt := mountlib.Opt
	mountOpt.AllowNonEmpty = true      // --allow-non-empty
	mountOpt.DefaultPermissions = true // --default-permissions

	vfsOpt := vfscommon.Opt
	vfsOpt.ReadOnly = true   // --read-only
	vfsOpt.NoChecksum = true // --no-checksum

	mp := mountlib.NewMountPoint(mountFn, mountpoint, f, &mountOpt, &vfsOpt)
	if _, err := mp.Mount(); err != nil {
		return nil, fmt.Errorf("mount %q at %q: %w", remote, mountpoint, err)
	}

	timeout := opts.ReadyTimeout
	if timeout <= 0 {
		timeout = defaultReadyTimeout
	}
	if err := waitReady(mp.MountPoint, timeout); err != nil {
		_ = mp.Unmount()
		return nil, fmt.Errorf("mount %q at %q: %w", remote, mountpoint, err)
	}
	return &Handle{mp: mp}, nil
}

// Mountpoint returns the path the remote is mounted on.
func (h *Handle) Mountpoint() string {
	return h.mp.MountPoint
}

// Unmount detaches the FUSE mount and shuts down the VFS.
func (h *Handle) Unmount() error {
	err := h.mp.Unmount()
	if h.mp.VFS != nil {
		h.mp.VFS.Shutdown()
	}
	return err
}

// Wait blocks until the mount ends (Unmount from another goroutine, or an
// external `fusermount3 -u`) and returns the serving error, if any.
func (h *Handle) Wait() error {
	return h.mp.Wait()
}

// waitReady polls until mountpoint shows up as mounted, mirroring
// mountlib.WaitMountReady (which cannot be used directly without a daemon
// process handle).
func waitReady(mountpoint string, timeout time.Duration) error {
	if !mountlib.CanCheckMountReady {
		return nil
	}
	deadline := time.Now().Add(timeout)
	for {
		err := mountlib.CheckMountReady(mountpoint)
		if err == nil {
			return nil
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("mount did not become ready within %s: %w", timeout, err)
		}
		time.Sleep(100 * time.Millisecond)
	}
}

// Unmount unmounts an rclone FUSE mount at mountpoint that may have been
// created by another process, by invoking `fusermount3 -u` exactly like the
// Python implementation. For mounts created in-process prefer
// Handle.Unmount.
func Unmount(mountpoint string) error {
	fusermount, err := exec.LookPath("fusermount3")
	if err != nil {
		return errors.New(`could not find "fusermount3": please install the "fuse3" OS package`)
	}
	out, err := exec.Command(fusermount, "-u", mountpoint).CombinedOutput()
	if err != nil {
		return fmt.Errorf("fusermount3 -u %s: %v: %s", mountpoint, err, out)
	}
	return nil
}
