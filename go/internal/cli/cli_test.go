package cli

import (
	"bytes"
	"context"
	"errors"
	"strings"
	"testing"
)

// recorderApp records which App method was dispatched and with which args.
type recorderApp struct {
	method string
	args   any
}

func (r *recorderApp) record(method string, args any) error {
	r.method = method
	r.args = args
	return nil
}

func (r *recorderApp) Credentials(_ context.Context, a CredentialsArgs) error {
	return r.record("Credentials", a)
}
func (r *recorderApp) Config(_ context.Context, a ConfigArgs) error   { return r.record("Config", a) }
func (r *recorderApp) Index(_ context.Context, a IndexArgs) error     { return r.record("Index", a) }
func (r *recorderApp) Archive(_ context.Context, a ArchiveArgs) error { return r.record("Archive", a) }
func (r *recorderApp) Delete(_ context.Context, a DeleteArgs) error   { return r.record("Delete", a) }
func (r *recorderApp) Mount(_ context.Context, a MountArgs) error     { return r.record("Mount", a) }
func (r *recorderApp) Umount(_ context.Context, a UmountArgs) error   { return r.record("Umount", a) }
func (r *recorderApp) Restore(_ context.Context, a RestoreArgs) error { return r.record("Restore", a) }
func (r *recorderApp) ChangeTier(_ context.Context, a RestoreArgs) error {
	return r.record("ChangeTier", a)
}
func (r *recorderApp) Update(_ context.Context, a UpdateArgs) error { return r.record("Update", a) }
func (r *recorderApp) Test(_ context.Context, a TestArgs) error     { return r.record("Test", a) }
func (r *recorderApp) LogPrint(_ context.Context, a GlobalArgs) error {
	return r.record("LogPrint", a)
}
func (r *recorderApp) SetDefaultProfile(_ context.Context, a GlobalArgs) error {
	return r.record("SetDefaultProfile", a)
}

func execute(t *testing.T, app App, args ...string) (stdout, stderr string, err error) {
	t.Helper()
	root := NewRootCmd(app)
	var out, errBuf bytes.Buffer
	root.SetOut(&out)
	root.SetErr(&errBuf)
	root.SetArgs(args)
	err = root.Execute()
	return out.String(), errBuf.String(), err
}

func TestRestoreHelpContainsRetrieveOptText(t *testing.T) {
	for _, invocation := range [][]string{{"restore", "-h"}, {"rst", "--help"}} {
		out, _, err := execute(t, NotImplementedApp{}, invocation...)
		if err != nil {
			t.Fatalf("%v: %v", invocation, err)
		}
		// pflag re-indents continuation lines, so assert line-wise
		// (trimmed) containment of the long argparse help text.
		for _, line := range strings.Split(helpRestoreRetrieveOpt, "\n") {
			line = strings.TrimSpace(line)
			if line == "" {
				continue
			}
			if !strings.Contains(out, line) {
				t.Errorf("%v output missing retrieve-opt help line %q", invocation, line)
			}
		}
	}
}

func TestUnknownFlagsError(t *testing.T) {
	for _, args := range [][]string{
		{"--bogus"},
		{"archive", "--bogus"},
		{"umount", "--bogus"},
		// Global flags are only valid before the subcommand, like argparse.
		{"archive", "--cores", "4"},
	} {
		_, _, err := execute(t, NotImplementedApp{}, args...)
		if err == nil {
			t.Errorf("%v: expected an unknown-flag error", args)
			continue
		}
		if !strings.Contains(err.Error(), "unknown flag") {
			t.Errorf("%v: error = %q, want unknown flag", args, err)
		}
		if got := ExitCode(err); got != 2 {
			t.Errorf("%v: exit code = %d, want 2 (argparse usage error)", args, got)
		}
	}
}

func TestUnknownSubcommandErrors(t *testing.T) {
	_, _, err := execute(t, NotImplementedApp{}, "frobnicate")
	if err == nil {
		t.Fatal("expected error for unknown subcommand")
	}
}

func TestVersionAndInfoPrintDirectly(t *testing.T) {
	out, _, err := execute(t, NotImplementedApp{}, "-v")
	if err != nil {
		t.Fatalf("-v: %v", err)
	}
	if !strings.HasPrefix(out, "froster v") {
		t.Errorf("-v output = %q, want froster v<version>", out)
	}

	// Like Python froster, the global action flags short-circuit any
	// subcommand: `froster -v archive` prints the version and exits 0.
	rec := &recorderApp{}
	out, _, err = execute(t, rec, "-v", "archive", "/tmp/x")
	if err != nil || rec.method != "" {
		t.Errorf("-v archive: err=%v dispatched=%q, want version print only", err, rec.method)
	}
	if !strings.HasPrefix(out, "froster v") {
		t.Errorf("-v archive output = %q", out)
	}

	out, _, err = execute(t, NotImplementedApp{}, "--info")
	if err != nil {
		t.Fatalf("--info: %v", err)
	}
	if !strings.Contains(out, "froster") || !strings.Contains(out, "version:") {
		t.Errorf("--info output = %q", out)
	}
}

func TestNoArgsPrintsHelpAndExits1(t *testing.T) {
	out, _, err := execute(t, NotImplementedApp{})
	var ee *ExitError
	if !errors.As(err, &ee) || ee.Code != 1 {
		t.Fatalf("no args: err = %v, want ExitError{1}", err)
	}
	if !Silent(err) {
		t.Errorf("help-then-exit error must be silent")
	}
	if !strings.Contains(out, "Available Commands:") || !strings.Contains(out, "archive") {
		t.Errorf("no-args output should be the help text, got %q", out)
	}
}

func TestGlobalActionFlagRouting(t *testing.T) {
	rec := &recorderApp{}
	if _, _, err := execute(t, rec, "--log-print"); err != nil || rec.method != "LogPrint" {
		t.Errorf("--log-print: err=%v method=%q", err, rec.method)
	}
	rec = &recorderApp{}
	if _, _, err := execute(t, rec, "-D"); err != nil || rec.method != "SetDefaultProfile" {
		t.Errorf("-D: err=%v method=%q", err, rec.method)
	}
}

func TestStubbedRestoreFlags(t *testing.T) {
	for _, args := range [][]string{
		{"restore", "--aws", "/tmp/x"},
		{"restore", "--monitor"},
		{"restore", "-i", "t3.large", "/tmp/x"},
		{"mount", "--aws", "/tmp/x"},
	} {
		rec := &recorderApp{}
		_, _, err := execute(t, rec, args...)
		if err == nil {
			t.Errorf("%v: expected stub error", args)
			continue
		}
		msg := err.Error()
		if !strings.Contains(msg, "not yet implemented in go-froster") ||
			!strings.Contains(msg, "pip install froster==0.22.x") ||
			!strings.Contains(msg, "GO-ARCHITECTURE.md section 9") {
			t.Errorf("%v: stub message incomplete: %q", args, msg)
		}
		if rec.method != "" {
			t.Errorf("%v: dispatched %q despite stub", args, rec.method)
		}
	}

	// All stubbed flags used together are reported together.
	_, _, err := execute(t, &recorderApp{}, "restore", "-a", "-m", "-i", "c5.xlarge")
	if err == nil || !strings.Contains(err.Error(), "'restore --aws', 'restore --monitor', 'restore --instance-type'") {
		t.Errorf("combined stub error = %v", err)
	}
}

func TestArchiveDispatch(t *testing.T) {
	rec := &recorderApp{}
	_, _, err := execute(t, rec,
		"-c", "8", "-n", "-p", "myprofile",
		"archive", "-r", "-o", "100", "-l", "5", "--nih-ref", "R01",
		"/data/a", "/data/b")
	if err != nil {
		t.Fatalf("archive dispatch: %v", err)
	}
	if rec.method != "Archive" {
		t.Fatalf("dispatched %q, want Archive", rec.method)
	}
	a := rec.args.(ArchiveArgs)
	switch {
	case a.Global.Cores != 8, !a.Global.NoSlurm, a.Global.Profile != "myprofile":
		t.Errorf("global args not carried: %+v", a.Global)
	case !a.Recursive, a.Older != 100, a.Larger != 5, a.NIHRef != "R01":
		t.Errorf("archive flags not carried: %+v", a)
	case len(a.Folders) != 2 || a.Folders[0] != "/data/a" || a.Folders[1] != "/data/b":
		t.Errorf("folders = %v", a.Folders)
	}
	// Defaults from env-dependent global flags (Slurm env cleared in TestMain).
	if a.Global.Memory != 16 {
		t.Errorf("default --mem = %d, want 16", a.Global.Memory)
	}
}

// TestShorthandsAreCommandLocal pins the argparse semantics: -d after
// `archive` is --dry-run, while -d before the subcommand is the global
// --debug (in stock cobra persistent flags these would collide and panic).
func TestShorthandsAreCommandLocal(t *testing.T) {
	rec := &recorderApp{}
	if _, _, err := execute(t, rec, "archive", "-d", "/tmp/x"); err != nil {
		t.Fatalf("archive -d: %v", err)
	}
	a := rec.args.(ArchiveArgs)
	if !a.DryRun || a.Global.Debug {
		t.Errorf("archive -d: DryRun=%v Debug=%v, want dry-run only", a.DryRun, a.Global.Debug)
	}

	rec = &recorderApp{}
	if _, _, err := execute(t, rec, "-d", "archive", "/tmp/x"); err != nil {
		t.Fatalf("-d archive: %v", err)
	}
	a = rec.args.(ArchiveArgs)
	if a.DryRun || !a.Global.Debug {
		t.Errorf("-d archive: DryRun=%v Debug=%v, want debug only", a.DryRun, a.Global.Debug)
	}
}

func TestMountAndUmountDispatch(t *testing.T) {
	rec := &recorderApp{}
	if _, _, err := execute(t, rec, "mount", "-m", "/mnt/here", "/data/a"); err != nil {
		t.Fatalf("mount: %v", err)
	}
	if rec.method != "Mount" {
		t.Fatalf("dispatched %q, want Mount", rec.method)
	}
	m := rec.args.(MountArgs)
	if m.MountPoint != "/mnt/here" || len(m.Folders) != 1 {
		t.Errorf("mount args = %+v", m)
	}

	rec = &recorderApp{}
	if _, _, err := execute(t, rec, "umount", "/data/a"); err != nil {
		t.Fatalf("umount: %v", err)
	}
	if rec.method != "Umount" {
		t.Fatalf("dispatched %q, want Umount", rec.method)
	}
	u := rec.args.(UmountArgs)
	if len(u.Folders) != 1 || u.Folders[0] != "/data/a" {
		t.Errorf("umount args = %+v", u)
	}

	// umount --list parses (same flag surface as mount).
	rec = &recorderApp{}
	if _, _, err := execute(t, rec, "umount", "--list"); err != nil {
		t.Fatalf("umount --list: %v", err)
	}
	if !rec.args.(UmountArgs).List {
		t.Errorf("umount --list not carried")
	}
}

func TestRestoreChangeTierRouting(t *testing.T) {
	rec := &recorderApp{}
	if _, _, err := execute(t, rec, "restore", "-t", "/data/a"); err != nil {
		t.Fatalf("restore -t: %v", err)
	}
	if rec.method != "ChangeTier" {
		t.Errorf("restore --change-tier dispatched %q, want ChangeTier", rec.method)
	}

	rec = &recorderApp{}
	if _, _, err := execute(t, rec, "restore", "-d", "45", "/data/a"); err != nil {
		t.Fatalf("restore: %v", err)
	}
	if rec.method != "Restore" {
		t.Fatalf("dispatched %q, want Restore", rec.method)
	}
	r := rec.args.(RestoreArgs)
	if r.Days != "45" || r.RetrieveOpt != "Bulk" {
		t.Errorf("restore args = %+v, want Days=45 RetrieveOpt=Bulk", r)
	}
}

func TestAliasesDispatch(t *testing.T) {
	cases := []struct {
		alias  string
		method string
	}{
		{"crd", "Credentials"},
		{"cnf", "Config"},
		{"idx", "Index"},
		{"arc", "Archive"},
		{"del", "Delete"},
		{"rst", "Restore"},
		{"upd", "Update"},
		{"tst", "Test"},
	}
	for _, tc := range cases {
		rec := &recorderApp{}
		if _, _, err := execute(t, rec, tc.alias); err != nil {
			t.Errorf("%s: %v", tc.alias, err)
			continue
		}
		if rec.method != tc.method {
			t.Errorf("%s dispatched %q, want %q", tc.alias, rec.method, tc.method)
		}
	}
}

func TestNotImplementedAppErrors(t *testing.T) {
	_, _, err := execute(t, NotImplementedApp{}, "index", "/tmp/x")
	if err == nil || !strings.Contains(err.Error(), "not implemented yet in this go-froster build") {
		t.Errorf("NotImplementedApp index error = %v", err)
	}
	if got := ExitCode(err); got != 1 {
		t.Errorf("exit code = %d, want 1", got)
	}
}

func TestHiddenDeleteBucketFlag(t *testing.T) {
	out, _, err := execute(t, NotImplementedApp{}, "delete", "--help")
	if err != nil {
		t.Fatalf("delete --help: %v", err)
	}
	if strings.Contains(out, "--bucket") {
		t.Errorf("--bucket must be hidden from delete help (argparse.SUPPRESS)")
	}
	// ... but it still parses.
	rec := &recorderApp{}
	if _, _, err := execute(t, rec, "delete", "-b", "mybucket"); err != nil {
		t.Fatalf("delete -b: %v", err)
	}
	if rec.args.(DeleteArgs).Bucket != "mybucket" {
		t.Errorf("delete -b not carried: %+v", rec.args)
	}
}
