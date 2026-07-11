// Package app implements the real cli.App: it loads froster's
// configuration, gates on credentials and Slurm, drives the interactive
// selection screens, and dispatches into internal/workflow. Behavior
// follows go/docs/python-behavior-spec.md (froster/froster.py v0.22.0);
// deviations are marked with "DOCUMENTED DEVIATION" comments.
package app

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"

	"github.com/dirkpetersen/froster/go/internal/cli"
	"github.com/dirkpetersen/froster/go/internal/tui"
	"github.com/dirkpetersen/froster/go/internal/workflow"
)

// App is the production implementation of cli.App.
type App struct {
	// Stderr receives error messages Python writes to sys.stderr.
	// Defaults to os.Stderr.
	Stderr io.Writer

	// Argv are the CLI arguments (without the program name) replayed into
	// Slurm batch scripts. Defaults to os.Args[1:].
	Argv []string

	// pickArchived and pickString are TUI seams for tests.
	pickArchived func(ctx context.Context, rows []tui.ArchiveRow) (string, bool, error)
	pickString   func(ctx context.Context, title string, items []string) (string, bool, error)
}

var _ cli.App = (*App)(nil)

// New returns a ready-to-use App.
func New() *App {
	return &App{
		Stderr:       os.Stderr,
		Argv:         os.Args[1:],
		pickArchived: tui.PickArchivedFolder,
		pickString:   tui.PickString,
	}
}

// exit1 is the silent exit-status-1 error (all messages already printed),
// matching Python's `return False` / `sys.exit(1)` after logging.
func exit1() error { return &cli.ExitError{Code: 1} }

// wrapWorkflowErr translates workflow results into process exit semantics:
// ErrReported means everything was already printed (exit 1, silently);
// other errors bubble up for main to print.
func wrapWorkflowErr(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, workflow.ErrReported) {
		return exit1()
	}
	return err
}

// cleanPaths applies Python's clean_path to every folder argument
// (spec §0.6: realpath + expanduser + strip trailing slash). Like Python's
// clean_path_list, empty arguments are dropped, so e.g. `froster archive ""`
// falls through to the no-folders interactive path instead of trying to
// archive "".
func cleanPaths(folders []string) []string {
	out := make([]string, 0, len(folders))
	for _, f := range folders {
		if f == "" {
			continue
		}
		out = append(out, workflow.CleanPath(f))
	}
	return out
}

// stderr returns the configured error stream.
func (a *App) stderr() io.Writer {
	if a.Stderr != nil {
		return a.Stderr
	}
	return os.Stderr
}

// Credentials implements `froster credentials`: AWSBoto.check_credentials
// with prints=True (Python subcmd_credentials).
func (a *App) Credentials(ctx context.Context, args cli.CredentialsArgs) error {
	s, err := a.newSession(args.Global)
	if err != nil {
		return err
	}

	if s.profile == "" {
		s.log.Logf("%s", "\nError: No profile found. Please configure an S3 profile using the command:")
		s.log.Logf("%s", "    froster config\n")
		s.log.Logf("%s", "\nYou can configure the credentials using the command:")
		s.log.Logf("%s", "    froster config\n")
		return exit1()
	}

	s.log.Logf("%s", "\nChecking credentials...\n")
	s.log.Logf("  Profile: %s", s.profile)
	s.log.Logf("  Provider: %s", s.prof.Provider)
	s.log.Logf("  Credentials: %s", s.prof.Credentials)
	s.log.Logf("  Endpoint: %s\n", s.endpoint)

	if err := s.listBuckets(ctx); err != nil {
		s.log.Logf("Error: %v", err)
		s.log.Logf("%s", "\nYou can configure the credentials using the command:")
		s.log.Logf("%s", "    froster config\n")
		return exit1()
	}
	s.log.Logf("%s", "...credentials are valid\n")
	return nil
}

// Config implements App; the interactive configuration wizard is not part
// of this change set.
func (a *App) Config(ctx context.Context, args cli.ConfigArgs) error {
	return cli.NotImplementedApp{}.Config(ctx, args)
}

// Update implements App; the self-update check is not part of this change
// set.
func (a *App) Update(ctx context.Context, args cli.UpdateArgs) error {
	return cli.NotImplementedApp{}.Update(ctx, args)
}

// Test implements App; the self-test workflow is not part of this change
// set.
func (a *App) Test(ctx context.Context, args cli.TestArgs) error {
	return cli.NotImplementedApp{}.Test(ctx, args)
}

// LogPrint implements the global --log-print flag (Python print_log).
// The flag itself authorizes printing: Python's main() sets DEBUG=1 when
// -l/--log-print is passed (froster.py:7178), so print_log's DEBUG gate is
// always satisfied. Gating on a pre-existing DEBUG env var here would make
// `froster --log-print` silently print nothing (and the Go log file is
// written whenever --debug is passed, independent of the env).
func (a *App) LogPrint(ctx context.Context, args cli.GlobalArgs) error {
	s, err := a.newSession(args)
	if err != nil {
		return err
	}
	logPath := s.paths.LogFile()
	data, err := os.ReadFile(logPath)
	if err != nil {
		fmt.Print("\nNo log file found\n\n") // print('\nNo log file found\n')
		return nil
	}
	fmt.Println(string(data))
	return nil
}

// SetDefaultProfile implements the global --default-profile flag; the
// interactive profile selector is not part of this change set.
func (a *App) SetDefaultProfile(ctx context.Context, args cli.GlobalArgs) error {
	return cli.NotImplementedApp{}.SetDefaultProfile(ctx, args)
}
