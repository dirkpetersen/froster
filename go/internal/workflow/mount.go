package workflow

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/dirkpetersen/froster/go/internal/mount"
	"github.com/dirkpetersen/froster/go/internal/transfer"
)

// Environment protocol for the background mount daemon. `froster mount`
// cannot serve a FUSE mount in-process and also return to the shell (the
// Python version left a detached rclone process behind), so the parent
// re-executes its own binary with these variables set; main() diverts such
// a process into RunMountDaemon before any CLI parsing.
const (
	envMountDaemon = "FROSTER_MOUNT_DAEMON"
	envMountRemote = "FROSTER_MOUNT_REMOTE"
	envMountPoint  = "FROSTER_MOUNT_POINT"
	envMountS3     = "FROSTER_MOUNT_S3"
)

// IsMountDaemon reports whether this process was spawned as a background
// mount daemon and should call RunMountDaemon instead of the CLI.
func IsMountDaemon() bool {
	return os.Getenv(envMountDaemon) == "1"
}

// RunMountDaemon serves one FUSE mount described by the daemon environment
// variables until it is unmounted externally (fusermount3 -u). It is the
// child side of the default MountFn.
func RunMountDaemon() error {
	remote := os.Getenv(envMountRemote)
	mountpoint := os.Getenv(envMountPoint)
	if remote == "" || mountpoint == "" {
		return errors.New("mount daemon: missing FROSTER_MOUNT_REMOTE / FROSTER_MOUNT_POINT")
	}
	var s3cfg transfer.S3Config
	if raw := os.Getenv(envMountS3); raw != "" {
		if err := json.Unmarshal([]byte(raw), &s3cfg); err != nil {
			return fmt.Errorf("mount daemon: parsing FROSTER_MOUNT_S3: %w", err)
		}
	}
	h, err := mount.Mount(context.Background(), remote, mountpoint, mount.Options{S3: s3cfg})
	if err != nil {
		return err
	}
	return h.Wait()
}

// spawnMountDaemon is the default MountFn: it re-executes the current
// binary as a detached daemon serving the mount and waits until the mount
// appears in /proc/mounts (or the daemon dies).
func (w *Workflow) spawnMountDaemon(s3cfg transfer.S3Config) func(remote, mountpoint string) error {
	return func(remote, mountpoint string) error {
		exe, err := os.Executable()
		if err != nil {
			return err
		}
		raw, err := json.Marshal(s3cfg)
		if err != nil {
			return err
		}

		devnull, err := os.OpenFile(os.DevNull, os.O_RDWR, 0)
		if err != nil {
			return err
		}
		defer devnull.Close()

		cmd := exec.Command(exe)
		cmd.Env = append(os.Environ(),
			envMountDaemon+"=1",
			envMountRemote+"="+remote,
			envMountPoint+"="+mountpoint,
			envMountS3+"="+string(raw),
		)
		// Detach: new session, all stdio to /dev/null (Python pipes the
		// background rclone's output to /dev/null too).
		cmd.Stdin, cmd.Stdout, cmd.Stderr = devnull, devnull, devnull
		cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
		if err := cmd.Start(); err != nil {
			return err
		}

		// Reap the child in the background so a failing daemon does not
		// linger as a zombie while we poll.
		exited := make(chan error, 1)
		go func() { exited <- cmd.Wait() }()

		deadline := time.Now().Add(15 * time.Second)
		for {
			for _, mp := range w.getMounts() {
				if mp == mountpoint {
					return nil
				}
			}
			select {
			case err := <-exited:
				if err == nil {
					err = errors.New("mount daemon exited")
				}
				return fmt.Errorf("mount daemon failed: %w", err)
			default:
			}
			if time.Now().After(deadline) {
				return errors.New("mount did not appear within 15s")
			}
			time.Sleep(200 * time.Millisecond)
		}
	}
}

// DefaultMountFn returns the daemon-spawning mount function for the given
// S3 configuration; the app layer assigns it to Workflow.MountFn.
func (w *Workflow) DefaultMountFn(s3cfg transfer.S3Config) func(remote, mountpoint string) error {
	return w.spawnMountDaemon(s3cfg)
}

// getMounts returns the current fuse.rclone mount points, via the injected
// GetMounts or /proc/mounts (Python Rclone.get_mounts, spec §0.5).
func (w *Workflow) getMounts() []string {
	if w.GetMounts != nil {
		return w.GetMounts()
	}
	return ProcMounts()
}

// ProcMounts parses /proc/mounts and returns the mount points whose
// filesystem type starts with "fuse.rclone", exactly like Python (which
// does not unescape the octal-escaped mount paths either).
func ProcMounts() []string {
	f, err := os.Open("/proc/mounts")
	if err != nil {
		return nil
	}
	defer f.Close()

	var mounts []string
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		parts := strings.Fields(scanner.Text())
		if len(parts) >= 3 && strings.HasPrefix(parts[2], "fuse.rclone") {
			mounts = append(mounts, parts[1])
		}
	}
	return mounts
}

// PrintCurrentMounts reproduces Archiver.print_current_mounts (`froster
// mount --list`).
func (w *Workflow) PrintCurrentMounts() {
	mounts := w.getMounts()
	if len(mounts) > 0 {
		w.echo("\nCURRENT MOUNTED FOLDERS:\n")
		for _, mp := range mounts {
			w.echof("    %s", mp)
		}
		w.echo("")
	} else {
		w.echo("\nNO FOLDERS MOUNTED\n")
	}
}

// Mounts exposes the current fuse.rclone mount points (Python
// Archiver.get_mounts), for the umount TUI fallback in the app layer.
func (w *Workflow) Mounts() []string { return w.getMounts() }

// Mount reproduces Archiver.mount/_mount_locally (spec §4.1 step 4). The
// mountpoint argument is cleaned here like Python does. An
// already-mounted mountpoint hard-exits (Python sys.exit(1)) via
// ErrReported; a mount failure stops the remaining folders but exits 0.
func (w *Workflow) Mount(ctx context.Context, folders []string, mountpoint string) error {
	mountpoint = CleanPath(mountpoint)

	for _, folder := range folders {
		entry := w.DB.Get(folder)
		if entry == nil {
			w.echof("\nWARNING: folder %s not in archive.\n", quoteDouble(folder))
			w.echo("Nothing will be restored.\n")
			continue
		}

		if _, err := os.Stat(folder); os.IsNotExist(err) && mountpoint == "" {
			w.echof("\nWARNING: folder %s does not exist and no mountpoint provided.\n", quoteDouble(folder))
			w.echo("Nothing will be restored.\n")
			continue
		}

		// Always the parent entry's S3 path: a subfolder of a recursive
		// archive mounts the whole parent (spec §4.1).
		s3Folder := entry.ArchiveFolder
		localFolder := entry.LocalFolder

		if folder == localFolder {
			if mountpoint != "" {
				w.echof("\nMOUNTING %s at %s...", quoteDouble(localFolder), quoteDouble(mountpoint))
			} else {
				w.echof("\nMOUNTING %s...", quoteDouble(localFolder))
			}
		} else {
			if mountpoint != "" {
				w.echof("\nMOUNTING parent folder %s at %s...", quoteDouble(localFolder), quoteDouble(mountpoint))
			} else {
				w.echof("\nMOUNTING parent folder %s...", quoteDouble(localFolder))
			}
		}

		// Python quirk reproduced: mountpoint is a loop-level variable, so
		// once defaulted it carries over to the next folder.
		if mountpoint == "" {
			mountpoint = localFolder
		}

		if w.isMounted(mountpoint) {
			w.echof("    ...%s already mounted\n", quoteDouble(mountpoint))
			// Python: sys.exit(1) — remaining folders are not processed.
			return ErrReported
		}

		if w.MountFn == nil {
			w.echo("    ...FAILED\n")
			w.echoErr("Error: no mount implementation configured")
			return nil
		}
		if err := w.MountFn(s3Folder, mountpoint); err != nil {
			w.echo("    ...FAILED\n")
			w.echoErr(fmt.Sprintf("Error: %v", err))
			// Python stops processing remaining folders but returns
			// success (exit 0).
			return nil
		}
		w.echo("    ...MOUNTED\n")
	}
	return nil
}

func (w *Workflow) isMounted(folder string) bool {
	for _, mp := range w.getMounts() {
		if mp == folder {
			return true
		}
	}
	return false
}

// Umount reproduces Archiver.unmount/_unmount_locally as *intended* — the
// shipped Python `froster umount` dies with a TypeError before reaching
// this logic (spec §4.2, documented deviation: go-froster implements the
// intended behavior). Always exits 0.
func (w *Workflow) Umount(folders []string) error {
	for _, folder := range folders {
		w.echof("\nUNMOUNTING %s...", folder)

		if !w.isMounted(folder) {
			w.echo("    ...IS NOT MOUNTED\n")
			continue
		}

		unmount := w.UnmountFn
		if unmount == nil {
			unmount = mount.Unmount
		}
		if err := unmount(folder); err != nil {
			w.echo("    ...UNMOUNTING FAILED\n")
		} else {
			w.echo("    ...UNMOUNTED SUCCESS\n")
		}
	}
	return nil
}

// CleanPath reproduces Python's clean_path helper (spec §0.6):
// os.path.realpath(os.path.expanduser(path).rstrip('/')). An empty path
// stays empty.
func CleanPath(path string) string {
	if path == "" {
		return ""
	}
	if path == "~" {
		if home, err := os.UserHomeDir(); err == nil {
			path = home
		}
	} else if strings.HasPrefix(path, "~/") {
		if home, err := os.UserHomeDir(); err == nil {
			path = home + path[1:]
		}
	}
	path = strings.TrimRight(path, "/")
	if path == "" {
		path = "/"
	}
	// os.path.realpath resolves symlinks but never fails on missing
	// paths: it resolves the longest existing prefix. Go's
	// filepath.EvalSymlinks errors on missing paths, so walk up to the
	// nearest existing ancestor and re-append the remainder.
	resolved, err := evalSymlinksBestEffort(path)
	if err == nil {
		return resolved
	}
	abs, err := absPath(path)
	if err != nil {
		return path
	}
	return abs
}

func absPath(path string) (string, error) {
	if strings.HasPrefix(path, "/") {
		return path, nil
	}
	wd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	return wd + "/" + path, nil
}

func evalSymlinksBestEffort(path string) (string, error) {
	abs, err := absPath(path)
	if err != nil {
		return "", err
	}
	remainder := ""
	p := abs
	for {
		resolved, err := evalSymlinks(p)
		if err == nil {
			if remainder == "" {
				return resolved, nil
			}
			return resolved + "/" + remainder, nil
		}
		dir, base := splitPath(p)
		if dir == p {
			return abs, nil
		}
		if remainder == "" {
			remainder = base
		} else {
			remainder = base + "/" + remainder
		}
		p = dir
	}
}

func evalSymlinks(path string) (string, error) {
	return filepath.EvalSymlinks(path)
}

func splitPath(p string) (dir, base string) {
	i := strings.LastIndexByte(p, '/')
	if i <= 0 {
		return "/", strings.TrimPrefix(p, "/")
	}
	return p[:i], p[i+1:]
}
