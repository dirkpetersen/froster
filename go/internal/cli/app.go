package cli

import (
	"context"
	"fmt"
)

// GlobalArgs carries the values of the root-level (global) flags. In the
// Python implementation these are arguments of the main argparse parser and
// must appear on the command line *before* the subcommand; the cobra tree
// reproduces that via Command.TraverseChildren (see root.go).
type GlobalArgs struct {
	Cores          int    // -c/--cores
	Debug          bool   // -d/--debug
	DefaultProfile bool   // -D/--default-profile
	Info           bool   // -i/--info
	LogPrint       bool   // -l/--log-print
	Memory         int    // -m/--mem (GB)
	NoSlurm        bool   // -n/--no-slurm
	Profile        string // -p/--profile
	Version        bool   // -v/--version
}

// CredentialsArgs carries the flag values of `froster credentials`.
type CredentialsArgs struct {
	Global GlobalArgs
}

// ConfigArgs carries the flag values of `froster config`.
type ConfigArgs struct {
	Global GlobalArgs

	Print        bool   // -p/--print
	Reset        bool   // -r/--reset
	ImportConfig string // -i/--import
	ExportConfig string // -e/--export
}

// IndexArgs carries the flag values of `froster index`.
type IndexArgs struct {
	Global GlobalArgs

	Folders     []string // positional
	Force       bool     // -f/--force
	Permissions bool     // -p/--permissions
	PwalkCopy   string   // -y/--pwalk-copy
}

// ArchiveArgs carries the flag values of `froster archive`.
type ArchiveArgs struct {
	Global GlobalArgs

	Folders   []string // positional
	Force     bool     // -f/--force
	Larger    int      // -l/--larger (GiB)
	Older     int      // -o/--older (days)
	Newer     int      // -w/--newer (days)
	NIH       bool     // -n/--nih
	NIHRef    string   // -i/--nih-ref
	AgeMtime  bool     // -m/--mtime
	Recursive bool     // -r/--recursive
	Reset     bool     // -s/--reset
	NoTar     bool     // -t/--no-tar
	DryRun    bool     // -d/--dry-run
}

// DeleteArgs carries the flag values of `froster delete`.
type DeleteArgs struct {
	Global GlobalArgs

	Folders   []string // positional
	Bucket    string   // -b/--bucket (hidden; debug only in Python froster)
	Recursive bool     // -r/--recursive
}

// MountArgs carries the flag values of `froster mount`.
type MountArgs struct {
	Global GlobalArgs

	Folders    []string // positional
	AWS        bool     // -a/--aws (stubbed, see GO-ARCHITECTURE.md section 9)
	List       bool     // -l/--list
	MountPoint string   // -m/--mount-point
}

// UmountArgs carries the flag values of `froster umount`. In Python, umount
// is an argparse alias of mount and therefore accepts the same flags.
type UmountArgs struct {
	Global GlobalArgs

	Folders    []string // positional
	AWS        bool     // -a/--aws (parsed for compatibility; ignored by unmount)
	List       bool     // -l/--list
	MountPoint string   // -m/--mount-point (parsed for compatibility; ignored by unmount)
}

// RestoreArgs carries the flag values of `froster restore`.
type RestoreArgs struct {
	Global GlobalArgs

	Folders []string // positional
	AWS     bool     // -a/--aws (stubbed, see GO-ARCHITECTURE.md section 9)
	// Days is a string, not an int: the Python argparse option uses
	// action='store' without type=int, so any CLI value arrives as a
	// string (default "30").
	Days         string // -d/--days
	InstanceType string // -i/--instance-type (stubbed, see GO-ARCHITECTURE.md section 9)
	NoDownload   bool   // -l/--no-download
	Monitor      bool   // -m/--monitor (stubbed, see GO-ARCHITECTURE.md section 9)
	RetrieveOpt  string // -o/--retrieve-opt
	Recursive    bool   // -r/--recursive
	ChangeTier   bool   // -t/--change-tier (routes to App.ChangeTier)
}

// UpdateArgs carries the flag values of `froster update`.
type UpdateArgs struct {
	Global GlobalArgs

	Rclone bool // -r/--rclone
}

// TestArgs carries the flag values of `froster test`.
type TestArgs struct {
	Global GlobalArgs
}

// App is the behavior behind the froster command tree. The CLI layer parses
// flags into the typed Args structs above and dispatches to these methods;
// wiring real workflows only requires implementing App, never touching the
// flag definitions.
type App interface {
	Credentials(ctx context.Context, args CredentialsArgs) error
	Config(ctx context.Context, args ConfigArgs) error
	Index(ctx context.Context, args IndexArgs) error
	Archive(ctx context.Context, args ArchiveArgs) error
	Delete(ctx context.Context, args DeleteArgs) error
	Mount(ctx context.Context, args MountArgs) error
	Umount(ctx context.Context, args UmountArgs) error
	Restore(ctx context.Context, args RestoreArgs) error
	// ChangeTier is invoked for `froster restore --change-tier`.
	ChangeTier(ctx context.Context, args RestoreArgs) error
	Update(ctx context.Context, args UpdateArgs) error
	Test(ctx context.Context, args TestArgs) error
	// LogPrint is invoked for the global -l/--log-print flag
	// (Python: print the log file to the screen).
	LogPrint(ctx context.Context, args GlobalArgs) error
	// SetDefaultProfile is invoked for the global -D/--default-profile flag.
	SetDefaultProfile(ctx context.Context, args GlobalArgs) error
}

// NotImplementedApp is the default App: every method returns a clear
// "not implemented" error. It lets the CLI surface (flags, help, aliases)
// be exercised before the workflows are wired up.
type NotImplementedApp struct{}

var _ App = NotImplementedApp{}

func notImplemented(what string) error {
	return fmt.Errorf("'%s' is not implemented yet in this go-froster build", what)
}

// Credentials implements App.
func (NotImplementedApp) Credentials(context.Context, CredentialsArgs) error {
	return notImplemented("froster credentials")
}

// Config implements App.
func (NotImplementedApp) Config(context.Context, ConfigArgs) error {
	return notImplemented("froster config")
}

// Index implements App.
func (NotImplementedApp) Index(context.Context, IndexArgs) error {
	return notImplemented("froster index")
}

// Archive implements App.
func (NotImplementedApp) Archive(context.Context, ArchiveArgs) error {
	return notImplemented("froster archive")
}

// Delete implements App.
func (NotImplementedApp) Delete(context.Context, DeleteArgs) error {
	return notImplemented("froster delete")
}

// Mount implements App.
func (NotImplementedApp) Mount(context.Context, MountArgs) error {
	return notImplemented("froster mount")
}

// Umount implements App.
func (NotImplementedApp) Umount(context.Context, UmountArgs) error {
	return notImplemented("froster umount")
}

// Restore implements App.
func (NotImplementedApp) Restore(context.Context, RestoreArgs) error {
	return notImplemented("froster restore")
}

// ChangeTier implements App.
func (NotImplementedApp) ChangeTier(context.Context, RestoreArgs) error {
	return notImplemented("froster restore --change-tier")
}

// Update implements App.
func (NotImplementedApp) Update(context.Context, UpdateArgs) error {
	return notImplemented("froster update")
}

// Test implements App.
func (NotImplementedApp) Test(context.Context, TestArgs) error {
	return notImplemented("froster test")
}

// LogPrint implements App.
func (NotImplementedApp) LogPrint(context.Context, GlobalArgs) error {
	return notImplemented("froster --log-print")
}

// SetDefaultProfile implements App.
func (NotImplementedApp) SetDefaultProfile(context.Context, GlobalArgs) error {
	return notImplemented("froster --default-profile")
}
