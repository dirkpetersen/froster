package workflow

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
)

func TestMountFlow(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()
	entry := goldenEntry(dir)
	upsertEntry(t, w, entry)

	var mounted []string
	w.GetMounts = func() []string { return nil }
	w.MountFn = func(remote, mountpoint string) error {
		mounted = append(mounted, remote+" @ "+mountpoint)
		return nil
	}

	out := captureStdout(t, func() {
		if err := w.Mount(context.Background(), []string{dir}, ""); err != nil {
			t.Errorf("Mount: %v", err)
		}
	})
	if !strings.Contains(out, "\nMOUNTING \""+dir+"\"...\n") ||
		!strings.Contains(out, "    ...MOUNTED\n") {
		t.Errorf("mount messages wrong:\n%s", out)
	}
	// Default mountpoint is the entry's local folder.
	if len(mounted) != 1 || mounted[0] != entry.ArchiveFolder+" @ "+dir {
		t.Errorf("mounted = %v", mounted)
	}
}

func TestMountSubfolderMountsParent(t *testing.T) {
	w, _ := newTestWorkflow(t)
	parent := t.TempDir()
	sub := parent + "/inner"
	writeFile(t, sub+"/.keep", "")
	entry := goldenEntry(parent)
	entry.ArchiveMode = archivedb.ModeRecursive
	upsertEntry(t, w, entry)

	var mounted []string
	w.GetMounts = func() []string { return nil }
	w.MountFn = func(remote, mountpoint string) error {
		mounted = append(mounted, remote+" @ "+mountpoint)
		return nil
	}

	out := captureStdout(t, func() {
		if err := w.Mount(context.Background(), []string{sub}, ""); err != nil {
			t.Errorf("Mount: %v", err)
		}
	})
	if !strings.Contains(out, "\nMOUNTING parent folder \""+parent+"\"...\n") {
		t.Errorf("missing parent-mount message:\n%s", out)
	}
	// The parent's S3 path is mounted at the parent's local folder.
	if len(mounted) != 1 || mounted[0] != entry.ArchiveFolder+" @ "+parent {
		t.Errorf("mounted = %v", mounted)
	}
}

func TestMountAlreadyMountedHardExit(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()
	upsertEntry(t, w, goldenEntry(dir))
	w.GetMounts = func() []string { return []string{dir} }
	w.MountFn = func(string, string) error { t.Error("MountFn called"); return nil }

	out := captureStdout(t, func() {
		err := w.Mount(context.Background(), []string{dir}, "")
		if !errors.Is(err, ErrReported) {
			t.Errorf("err = %v, want ErrReported (Python sys.exit(1))", err)
		}
	})
	if !strings.Contains(out, "    ...\""+dir+"\" already mounted\n") {
		t.Errorf("missing already-mounted message:\n%s", out)
	}
}

func TestMountUnknownFolderWarns(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir := t.TempDir()
	w.GetMounts = func() []string { return nil }
	w.MountFn = func(string, string) error { t.Error("MountFn called"); return nil }

	out := captureStdout(t, func() {
		if err := w.Mount(context.Background(), []string{dir}, ""); err != nil {
			t.Errorf("Mount: %v", err)
		}
	})
	if !strings.Contains(out, "\nWARNING: folder \""+dir+"\" not in archive.\n") ||
		!strings.Contains(out, "Nothing will be restored.") {
		t.Errorf("missing warning:\n%s", out)
	}
}

func TestMountFailureStopsButExitsZero(t *testing.T) {
	w, _ := newTestWorkflow(t)
	dir1 := t.TempDir()
	dir2 := t.TempDir()
	upsertEntry(t, w, goldenEntry(dir1))
	upsertEntry(t, w, goldenEntry(dir2))
	w.GetMounts = func() []string { return nil }
	calls := 0
	w.MountFn = func(string, string) error { calls++; return errors.New("boom") }

	out := captureStdout(t, func() {
		if err := w.Mount(context.Background(), []string{dir1, dir2}, ""); err != nil {
			t.Errorf("Mount: %v (failure must still exit 0)", err)
		}
	})
	if calls != 1 {
		t.Errorf("MountFn called %d times, want 1 (stop after failure)", calls)
	}
	if !strings.Contains(out, "    ...FAILED\n") {
		t.Errorf("missing FAILED:\n%s", out)
	}
}

func TestUmountFlow(t *testing.T) {
	w, _ := newTestWorkflow(t)
	mounted := "/mnt/somewhere"
	w.GetMounts = func() []string { return []string{mounted} }
	var unmounted []string
	w.UnmountFn = func(mp string) error { unmounted = append(unmounted, mp); return nil }

	out := captureStdout(t, func() {
		if err := w.Umount([]string{mounted, "/not/mounted"}); err != nil {
			t.Errorf("Umount: %v", err)
		}
	})
	if len(unmounted) != 1 || unmounted[0] != mounted {
		t.Errorf("unmounted = %v", unmounted)
	}
	for _, want := range []string{
		"\nUNMOUNTING " + mounted + "...\n",
		"    ...UNMOUNTED SUCCESS\n",
		"\nUNMOUNTING /not/mounted...\n",
		"    ...IS NOT MOUNTED\n",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("output missing %q:\n%s", want, out)
		}
	}

	// Failure path.
	w.UnmountFn = func(string) error { return errors.New("busy") }
	out = captureStdout(t, func() {
		if err := w.Umount([]string{mounted}); err != nil {
			t.Errorf("Umount: %v", err)
		}
	})
	if !strings.Contains(out, "    ...UNMOUNTING FAILED\n") {
		t.Errorf("missing FAILED:\n%s", out)
	}
}

func TestPrintCurrentMounts(t *testing.T) {
	w, _ := newTestWorkflow(t)
	w.GetMounts = func() []string { return []string{"/mnt/a", "/mnt/b"} }
	out := captureStdout(t, func() { w.PrintCurrentMounts() })
	if !strings.Contains(out, "\nCURRENT MOUNTED FOLDERS:\n\n    /mnt/a\n    /mnt/b\n\n") {
		t.Errorf("mount list output:\n%q", out)
	}

	w.GetMounts = func() []string { return nil }
	out = captureStdout(t, func() { w.PrintCurrentMounts() })
	if !strings.Contains(out, "\nNO FOLDERS MOUNTED\n") {
		t.Errorf("empty mount list output:\n%q", out)
	}
}
