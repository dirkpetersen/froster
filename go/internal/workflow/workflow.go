// Package workflow implements froster's core data workflows — archive,
// delete, restore, mount/umount, reset and index — with drop-in behavioral
// parity with the Python implementation (froster/froster.py v0.22.0). The
// authoritative behavior contract is go/docs/python-behavior-spec.md; every
// user-facing message, artifact file format, transfer parameter set, and
// database mutation is reproduced from there (including typos like
// "please us the -f").
//
// The package is deliberately free of AWS/Slurm/TUI dependencies beyond
// small interfaces and callbacks: the app layer (internal/app) wires
// credentials, Slurm submission and interactive selection around these
// workflows.
package workflow

import (
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
	"github.com/dirkpetersen/froster/go/internal/logging"
	"github.com/dirkpetersen/froster/go/internal/transfer"
)

// Artifact file names, matching Archiver.__init__ (spec §0.1).
const (
	SmallfilesTarFileName      = "Froster.smallfiles.tar"
	AllfilesCSVFileName        = "Froster.allfiles.csv"
	MD5SumFileName             = ".froster.md5sum"
	MD5SumRestoredFileName     = ".froster-restored.md5sum"
	WhereDidTheFilesGoFileName = "Where-did-the-files-go.txt"
)

// DirMetaFiles is Python's Archiver.dirmetafiles. Note that
// Froster.smallfiles.tar is deliberately NOT in this list (spec §0.1).
var DirMetaFiles = []string{
	AllfilesCSVFileName,
	MD5SumFileName,
	MD5SumRestoredFileName,
	WhereDidTheFilesGoFileName,
}

// DefaultThresholdKiB is the small-file tar threshold; files strictly
// smaller than this many KiB are tarred. Python hardcodes 1024 in
// ConfigManager (spec §0.1).
const DefaultThresholdKiB = 1024

// ErrReported signals that a workflow failed and has already printed all
// user-facing messages; the caller should exit with status 1 without
// printing anything further (mirroring Python's `return False` +
// `sys.exit(1)` in main).
var ErrReported = errors.New("froster: operation failed (details above)")

// Workflow carries the per-invocation state that Python spreads over
// ConfigManager, Archiver and the parsed args. Construct it in the app
// layer; the zero value is not usable — at minimum Log, Engine and DB must
// be set. Optional fields have documented defaults.
type Workflow struct {
	// Log receives all user-facing stdout output (Python's log()).
	Log *logging.Logger
	// Stderr receives messages Python writes with file=sys.stderr.
	// Defaults to os.Stderr.
	Stderr io.Writer

	// Engine performs rclone-equivalent copies and checksum verification.
	Engine transfer.Engine
	// DB is the froster-archives.json handle.
	DB *archivedb.DB

	// Profile configuration (Python cfg.* attributes).
	Provider     string // cfg.provider, e.g. "AWS", "Minio"
	Profile      string // cfg.profile: full section name, e.g. "profile minio"
	Credentials  string // cfg.credentials: the ~/.aws profile name; stored as the DB "profile" key
	Endpoint     string // cfg.endpoint ("" for AWS)
	Bucket       string // cfg.bucket_name
	ArchiveDir   string // cfg.archive_dir prefix inside the bucket
	StorageClass string // cfg.storage_class
	Email        string // cfg.email (used in Where-did-the-files-go.txt)

	// User is the archiving user (Python getpass.getuser()).
	User string
	// Cores is the --cores value (transfer/checker parallelism).
	Cores int
	// ThresholdKiB is the small-file tar threshold; 0 means
	// DefaultThresholdKiB.
	ThresholdKiB int

	// Now returns the current time; nil means time.Now. Injectable so
	// tests can pin manifest timestamps.
	Now func() time.Time

	// MountFn mounts remote at mountpoint in the background (surviving
	// this process). nil means the default daemon-spawning implementation
	// (see mount.go).
	MountFn func(remote, mountpoint string) error
	// UnmountFn unmounts a mountpoint; nil means fusermount3 -u via
	// internal/mount.Unmount.
	UnmountFn func(mountpoint string) error
	// GetMounts returns the current fuse.rclone mount points; nil means
	// parsing /proc/mounts (Python Rclone.get_mounts).
	GetMounts func() []string

	// Glacier triggers Glacier retrievals (nil is allowed when no entry
	// uses a Glacier storage class; restoring a Glacier archive without
	// it is an error).
	Glacier GlacierClient
	// ScheduleRestore submits one delayed Slurm restore retry
	// ("now+12hours", ...). nil disables scheduling (equivalent to Slurm
	// not being installed).
	ScheduleRestore func(scheduled string)
	// SlurmInstalled reports whether sbatch exists; nil means "false".
	// Used only by Restore's retry-scheduling gate, which (unlike the
	// other Slurm gates) fires even inside a Slurm job (spec §6.1).
	SlurmInstalled func() bool
}

// GlacierClient is the subset of awsx.Client that Restore needs.
type GlacierClient interface {
	// TriggerGlacierRestore mirrors awsx.Client.TriggerGlacierRestore.
	TriggerGlacierRestore(bucket, prefix string, days int32, tier string) (GlacierResult, error)
}

// GlacierResult mirrors awsx.RestoreResult without importing awsx (which
// would drag the AWS SDK into every workflow test).
type GlacierResult struct {
	Triggered    []string
	InProgress   []string
	Restored     []string
	NotGlacier   []string
	NotSupported []string
}

func (w *Workflow) now() time.Time {
	if w.Now != nil {
		return w.Now()
	}
	return time.Now()
}

func (w *Workflow) stderr() io.Writer {
	if w.Stderr != nil {
		return w.Stderr
	}
	return os.Stderr
}

func (w *Workflow) thresholdKiB() int {
	if w.ThresholdKiB > 0 {
		return w.ThresholdKiB
	}
	return DefaultThresholdKiB
}

// echo prints one line to stdout exactly like Python's log(s) — the string
// itself plus a trailing newline.
func (w *Workflow) echo(s string) { w.Log.Logf("%s", s) }

// echof is echo with formatting.
func (w *Workflow) echof(format string, a ...any) { w.Log.Logf(format, a...) }

// echoErr prints one line to stderr like Python's log(s, file=sys.stderr).
func (w *Workflow) echoErr(s string) { fmt.Fprintln(w.stderr(), s) }

// rcloneErr reports a failed transfer operation on stderr, standing in for
// the "Error: Rclone {cmd} command failed" diagnostics Python's Rclone
// wrapper prints (spec §0.5).
func (w *Workflow) rcloneErr(command string, err error) {
	fmt.Fprintf(w.stderr(), "\n        Error: Rclone %s command failed\n        Error: %v\n", command, err)
}

// s3Dest computes the upload destination for an absolute folder path,
// mirroring Python's
// os.path.join(f':s3:{bucket}', archive_dir, folder.lstrip('/')) →
// ":s3:<bucket>/<archive_dir>/<abs-path-without-leading-slash>".
func (w *Workflow) s3Dest(folder string) string {
	return filepath.Join(":s3:"+w.Bucket, w.ArchiveDir, strings.TrimLeft(folder, string(os.PathSeparator)))
}

// checkRecursiveCollision reports whether any folder is a subdirectory of
// another, printing the per-pair message (Python _is_recursive_collision).
// The first pair form goes to stderr, the second to stdout — an asymmetry
// in the Python source that is reproduced here.
func (w *Workflow) checkRecursiveCollision(folders []string) bool {
	collision := false
	for i := 0; i < len(folders); i++ {
		for j := i + 1; j < len(folders); j++ {
			switch {
			case isSubPath(folders[i], folders[j]):
				collision = true
				w.echoErr(fmt.Sprintf("Folder %s is a subdirectory of folder %s.\n", folders[j], folders[i]))
			case isSubPath(folders[j], folders[i]):
				collision = true
				w.echo(fmt.Sprintf("Folder %s is a subdirectory of folder %s.\n", folders[i], folders[j]))
			}
		}
	}
	return collision
}

// ArchiveCollision runs the recursive-dependency check with the archive
// error message; it prints everything and reports whether a collision was
// found. Exposed so the app layer can run the check in the same position
// Python does (before the Slurm submission gate).
func (w *Workflow) ArchiveCollision(folders []string) bool {
	if w.checkRecursiveCollision(folders) {
		w.echo("\nError: You cannot archive folders recursively if there is a dependency between them.\n")
		return true
	}
	return false
}

// DeleteCollision is ArchiveCollision with the delete message.
func (w *Workflow) DeleteCollision(folders []string) bool {
	if w.checkRecursiveCollision(folders) {
		w.echo("\nError: You cannot delete folders recursively if there is a dependency between them.\n")
		return true
	}
	return false
}

// RestoreCollision is ArchiveCollision with the restore message.
func (w *Workflow) RestoreCollision(folders []string) bool {
	if w.checkRecursiveCollision(folders) {
		w.echo("\nError: You cannot restore folders recursively if there is a dependency between them.\n")
		return true
	}
	return false
}

// isSubPath reports whether child is parent or lies below parent
// (Python: os.path.commonpath([parent, child]) == parent).
func isSubPath(parent, child string) bool {
	parent = filepath.Clean(parent)
	child = filepath.Clean(child)
	return child == parent || strings.HasPrefix(child, parent+string(os.PathSeparator))
}

// walkRoots yields top and all its subdirectories in topdown order,
// mirroring Python's Archiver._walker: directories named ".snapshot" are
// skipped entirely, symlinks are never followed (symlinked directories are
// treated as files and do not appear here), and directory read errors are
// printed to stderr and skipped (Python's _walkerr).
func (w *Workflow) walkRoots(top string) []string {
	var roots []string
	seen := map[string]bool{}
	_ = filepath.WalkDir(top, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			// Python's _walkerr: print the OSError and continue.
			fmt.Fprintln(w.stderr(), err.Error())
			if d != nil && d.IsDir() {
				return fs.SkipDir
			}
			return nil
		}
		if !d.IsDir() {
			return nil
		}
		if d.Name() == ".snapshot" && path != top {
			return fs.SkipDir
		}
		if !seen[path] {
			seen[path] = true
			roots = append(roots, path)
		}
		return nil
	})
	if len(roots) == 0 {
		// An unreadable top folder: Python's os.walk yields nothing;
		// callers iterate zero times. Keep that behavior.
		return nil
	}
	return roots
}

// topFiles returns the names of the non-directory entries (regular files,
// symlinks — including symlinks to directories — and special files)
// directly inside dir, matching the "files" list Python's _walker yields
// for the top directory. Order is lexical (Go's os.ReadDir); Python's
// os.scandir order is filesystem-dependent, so no consumer may rely on it.
func topFiles(dir string) ([]string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var names []string
	for _, e := range entries {
		if !e.IsDir() {
			names = append(names, e.Name())
		}
	}
	return names, nil
}

// isMetaFile reports whether name is one of the four froster metadata
// files (DirMetaFiles).
func isMetaFile(name string) bool {
	for _, m := range DirMetaFiles {
		if name == m {
			return true
		}
	}
	return false
}

// pyDictRepr renders an archive entry approximately as Python's dict repr
// (log(f'{archived_folder_info}')): single-quoted keys and values in the
// current writer's key order. Entries loaded from files written by older
// froster versions may render in a slightly different key order than
// CPython would — acceptable for an informational message.
func pyDictRepr(e *archivedb.Entry) string {
	type kv struct{ k, v string }
	pairs := []kv{
		{"local_folder", e.LocalFolder},
		{"archive_folder", e.ArchiveFolder},
		{"s3_storage_class", e.S3StorageClass},
		{"profile", e.Profile},
		{"provider", e.Provider},
		{"endpoint", e.Endpoint},
		{"archive_mode", e.ArchiveMode},
		{"timestamp", e.Timestamp},
		{"timestamp_archive", e.TimestampArchive},
		{"user", e.User},
	}
	if e.NIHProject != "" {
		pairs = append(pairs, kv{"nih_project", e.NIHProject})
	}
	var b strings.Builder
	b.WriteByte('{')
	for i, p := range pairs {
		if i > 0 {
			b.WriteString(", ")
		}
		fmt.Fprintf(&b, "'%s': '%s'", p.k, p.v)
	}
	b.WriteByte('}')
	return b.String()
}
