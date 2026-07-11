package app

import (
	"bytes"
	"context"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
	"github.com/dirkpetersen/froster/go/internal/cli"
	"github.com/dirkpetersen/froster/go/internal/tui"
	"github.com/dirkpetersen/froster/go/internal/workflow"
)

var stdoutMu sync.Mutex

// captureStdout redirects os.Stdout while fn runs (the logging package
// writes user-facing output straight to stdout).
func captureStdout(t *testing.T, fn func()) string {
	t.Helper()
	stdoutMu.Lock()
	defer stdoutMu.Unlock()
	old := os.Stdout
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	os.Stdout = w
	done := make(chan string)
	go func() {
		var buf bytes.Buffer
		io.Copy(&buf, r) //nolint:errcheck
		done <- buf.String()
	}()
	fn()
	w.Close()
	os.Stdout = old
	return <-done
}

// isolatedApp points every froster path at temp directories so the user's
// real configuration is never touched, and returns an App with quiet
// stderr.
func isolatedApp(t *testing.T) *App {
	t.Helper()
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("XDG_CONFIG_HOME", filepath.Join(home, ".config"))
	t.Setenv("XDG_DATA_HOME", filepath.Join(home, ".local", "share"))
	a := New()
	a.Stderr = io.Discard
	a.Argv = nil
	return a
}

func exitCodeOf(err error) int { return cli.ExitCode(err) }

func TestArchiveUnconfiguredCredentialsGate(t *testing.T) {
	a := isolatedApp(t)
	out := captureStdout(t, func() {
		err := a.Archive(context.Background(), cli.ArchiveArgs{Folders: []string{t.TempDir()}})
		if exitCodeOf(err) != 1 {
			t.Errorf("exit code = %d, want 1", exitCodeOf(err))
		}
	})
	for _, want := range []string{
		"\nError: No profile found. Please configure an S3 profile using the command:",
		"\nYou can configure the credentials using the command:",
		"    froster config",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("output missing %q:\n%s", want, out)
		}
	}
}

func TestRestoreDeleteMountAreGated(t *testing.T) {
	a := isolatedApp(t)
	ctx := context.Background()

	checks := []func() error{
		func() error { return a.Restore(ctx, cli.RestoreArgs{Folders: []string{"/tmp"}, Days: "30"}) },
		func() error { return a.Delete(ctx, cli.DeleteArgs{Folders: []string{"/tmp"}}) },
		func() error { return a.Mount(ctx, cli.MountArgs{Folders: []string{"/tmp"}}) },
	}
	for i, fn := range checks {
		out := captureStdout(t, func() {
			if code := exitCodeOf(fn()); code != 1 {
				t.Errorf("case %d: exit code = %d, want 1", i, code)
			}
		})
		if !strings.Contains(out, "You can configure the credentials using the command:") {
			t.Errorf("case %d missing credentials hint:\n%s", i, out)
		}
	}
}

func TestIndexArgumentValidation(t *testing.T) {
	a := isolatedApp(t)
	ctx := context.Background()

	// No folders.
	out := captureStdout(t, func() {
		err := a.Index(ctx, cli.IndexArgs{})
		if exitCodeOf(err) != 1 {
			t.Errorf("exit code = %d, want 1", exitCodeOf(err))
		}
	})
	if !strings.Contains(out, "\nError: Folder not provided. Check the index command usage with \"froster index --help\"\n") {
		t.Errorf("missing folder-not-provided message:\n%s", out)
	}

	// Nonexistent folder.
	missing := filepath.Join(t.TempDir(), "nope")
	out = captureStdout(t, func() {
		err := a.Index(ctx, cli.IndexArgs{Folders: []string{missing}})
		if exitCodeOf(err) != 1 {
			t.Errorf("exit code = %d, want 1", exitCodeOf(err))
		}
	})
	if !strings.Contains(out, "\nError: The folder "+missing+" does not exist.\n") {
		t.Errorf("missing folder-does-not-exist message:\n%s", out)
	}

	// Nonexistent pwalk-copy target.
	dir := t.TempDir()
	out = captureStdout(t, func() {
		err := a.Index(ctx, cli.IndexArgs{Folders: []string{dir}, PwalkCopy: missing})
		if exitCodeOf(err) != 1 {
			t.Errorf("exit code = %d, want 1", exitCodeOf(err))
		}
	})
	if !strings.Contains(out, "\nError: Folder \""+missing+"\" does not exist.\n") {
		t.Errorf("missing pwalk-copy message:\n%s", out)
	}
}

func TestIndexRunsUnconfigured(t *testing.T) {
	// index needs no credentials or profile; it must work on a fresh
	// system (Python parity: index skips the credentials gate).
	a := isolatedApp(t)
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "f.dat"), make([]byte, 2048), 0o644); err != nil {
		t.Fatal(err)
	}
	out := captureStdout(t, func() {
		if err := a.Index(context.Background(), cli.IndexArgs{
			Global:  cli.GlobalArgs{NoSlurm: true, Cores: 4},
			Folders: []string{dir},
		}); err != nil {
			t.Errorf("Index: %v", err)
		}
	})
	if !strings.Contains(out, "INDEXING SUCCESSFULLY COMPLETED") {
		t.Errorf("index did not complete:\n%s", out)
	}
	// The hotspots CSV landed in the isolated XDG data dir.
	csvPath := filepath.Join(os.Getenv("XDG_DATA_HOME"), "froster", "hotspots",
		strings.ReplaceAll(dir, "/", "+")+".csv")
	if _, err := os.Stat(csvPath); err != nil {
		t.Errorf("hotspot CSV missing at %s: %v", csvPath, err)
	}
}

func TestUmountNoMounts(t *testing.T) {
	a := isolatedApp(t)
	if len(workflow.ProcMounts()) > 0 {
		t.Skip("machine has live rclone mounts; skipping no-mounts test")
	}
	out := captureStdout(t, func() {
		if err := a.Umount(context.Background(), cli.UmountArgs{Folders: []string{"/tmp/x"}}); err != nil {
			t.Errorf("Umount: %v", err)
		}
	})
	if !strings.Contains(out, "\nNOTE: No rclone mounts on this computer.\n") {
		t.Errorf("missing no-mounts NOTE:\n%s", out)
	}
}

func TestLogPrintWithoutDebugEnvStillPrints(t *testing.T) {
	a := isolatedApp(t)
	t.Setenv("DEBUG", "")
	out := captureStdout(t, func() {
		if err := a.LogPrint(context.Background(), cli.GlobalArgs{}); err != nil {
			t.Errorf("LogPrint: %v", err)
		}
	})
	// No log file exists in the isolated app; the flag alone must still
	// activate printing (Python sets DEBUG=1 from the flag itself).
	if !strings.Contains(out, "No log file found") {
		t.Errorf("LogPrint silent without DEBUG env; want notice, got:\n%s", out)
	}
}

func TestUnknownProfileFlag(t *testing.T) {
	a := isolatedApp(t)
	out := captureStdout(t, func() {
		err := a.Credentials(context.Background(), cli.CredentialsArgs{
			Global: cli.GlobalArgs{Profile: "nosuch"},
		})
		if exitCodeOf(err) != 1 {
			t.Errorf("exit code = %d, want 1", exitCodeOf(err))
		}
	})
	if !strings.Contains(out, `"profile nosuch" does not exist in the configuration file (remember case sensitive)`) {
		t.Errorf("missing unknown-profile message:\n%s", out)
	}
}

func TestWrapWorkflowErr(t *testing.T) {
	if wrapWorkflowErr(nil) != nil {
		t.Error("nil must stay nil")
	}
	if code := exitCodeOf(wrapWorkflowErr(workflow.ErrReported)); code != 1 {
		t.Errorf("ErrReported exit code = %d, want 1", code)
	}
	if !cli.Silent(wrapWorkflowErr(workflow.ErrReported)) {
		t.Error("ErrReported must be silent (messages already printed)")
	}
	other := errors.New("boom")
	if wrapWorkflowErr(other) != other {
		t.Error("unexpected errors must pass through")
	}
}

func TestCleanPaths(t *testing.T) {
	dir := t.TempDir()
	got := cleanPaths([]string{dir + "/"})
	if got[0] != dir {
		t.Errorf("cleanPaths trailing slash: %q", got[0])
	}
}

func TestArchiveRowsAdapter(t *testing.T) {
	entries := []*archivedb.Entry{{
		LocalFolder:    "/data/x",
		S3StorageClass: "DEEP_ARCHIVE",
		Profile:        "aws",
		ArchiveMode:    archivedb.ModeRecursive,
	}}
	rows := archiveRows(entries, true)
	want := tui.ArchiveRow{LocalFolder: "/data/x", StorageClass: "DEEP_ARCHIVE", Profile: "aws", ArchiveMode: "Recursive"}
	if rows[0] != want {
		t.Errorf("rows[0] = %+v, want %+v", rows[0], want)
	}
	if rows := archiveRows(entries, false); rows[0].ArchiveMode != "" {
		t.Error("withMode=false must omit archive_mode")
	}
}
