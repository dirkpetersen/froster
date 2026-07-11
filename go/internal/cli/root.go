// Package cli defines the froster command tree. The surface (subcommands,
// aliases, flags, defaults) must match the Python implementation exactly;
// the contract lives in go/testdata/cli-contract.json and is enforced by
// contract_test.go.
//
// Flag-parsing semantics deliberately mirror argparse, not stock cobra:
// in Python froster the global flags belong to the main parser and must
// appear before the subcommand, while each subparser owns its flags after
// the subcommand name. Several subcommand shorthands (-p, -i, -d, -l, -m,
// -n) reuse global shorthand letters, so the global flags cannot be cobra
// persistent flags (pflag would panic on shorthand redefinition). Instead
// they are root-local flags and the tree sets Command.TraverseChildren,
// which parses root flags from the argv prefix and subcommand flags from
// the remainder — exactly the argparse behavior.
package cli

import (
	"context"
	"errors"
	"fmt"
	"os"
	"runtime"
	"strconv"

	"github.com/spf13/cobra"

	"github.com/dirkpetersen/froster/go/internal/version"
)

// Env-dependent defaults, matching Python froster:
//
//	cpucores = int(os.getenv('SLURM_CPUS_ON_NODE', 4))
//	nodemem  = int(os.getenv('SLURM_MEM_PER_NODE', 16384)) // 1024
const (
	defaultCores    = 4
	defaultMemMiB   = 16384
	envSlurmCores   = "SLURM_CPUS_ON_NODE"
	envSlurmMemNode = "SLURM_MEM_PER_NODE"
)

// ExitError carries a specific process exit code up through Execute without
// an error message to print (e.g. `froster` with no arguments prints help
// and exits 1, like the Python implementation).
type ExitError struct {
	Code int
}

func (e *ExitError) Error() string {
	return fmt.Sprintf("exit status %d", e.Code)
}

// usageError marks a flag/usage parse error so main can exit with status 2,
// matching argparse.
type usageError struct {
	err error
}

func (e *usageError) Error() string { return e.err.Error() }
func (e *usageError) Unwrap() error { return e.err }

// ExitCode returns the process exit code that a froster binary should use
// for the error returned by Execute: 0 for nil, the embedded code for
// ExitError, 2 for command-line usage errors (argparse compatibility), and
// 1 otherwise.
func ExitCode(err error) int {
	if err == nil {
		return 0
	}
	var ee *ExitError
	if errors.As(err, &ee) {
		return ee.Code
	}
	var ue *usageError
	if errors.As(err, &ue) {
		return 2
	}
	return 1
}

// Silent reports whether err has already been fully communicated to the user
// (help/usage printed) and should not be printed again by the caller.
func Silent(err error) bool {
	var ee *ExitError
	return errors.As(err, &ee)
}

func envInt(key string, fallback int) int {
	v, ok := os.LookupEnv(key)
	if !ok {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}

// Execute builds the froster command tree around app and runs it with
// os.Args. Use ExitCode on the returned error to pick the process exit code.
func Execute(app App) error {
	root := NewRootCmd(app)
	return root.Execute()
}

// NewRootCmd builds the complete froster command tree, dispatching to app.
// Env-dependent defaults (--cores, --mem) are computed at build time, like
// the Python parser does at parse_arguments() time.
func NewRootCmd(app App) *cobra.Command {
	global := &GlobalArgs{}

	cpuCores := envInt(envSlurmCores, defaultCores)
	nodeMem := envInt(envSlurmMemNode, defaultMemMiB) / 1024

	root := &cobra.Command{
		Use:   "froster",
		Short: descRoot,
		Long:  descRoot,
		// argparse semantics: global flags before the subcommand,
		// subcommand flags after it (see package comment).
		TraverseChildren: true,
		SilenceErrors:    true,
		SilenceUsage:     true,
		Args:             cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			if handled, err := runGlobalActions(cmd, app, *global); handled {
				return err
			}
			// Python: no arguments -> print help, exit 1.
			if err := cmd.Help(); err != nil {
				return err
			}
			return &ExitError{Code: 1}
		},
	}

	// cobra's auto-generated completion command is not part of the Python
	// CLI surface; keep it functional but out of --help.
	root.CompletionOptions.HiddenDefaultCmd = true

	f := root.Flags()
	f.IntVarP(&global.Cores, "cores", "c", cpuCores,
		fmt.Sprintf(helpGlobalCoresFmt, cpuCores))
	f.BoolVarP(&global.Debug, "debug", "d", false, helpGlobalDebug)
	f.BoolVarP(&global.DefaultProfile, "default-profile", "D", false, helpGlobalDefaultProfile)
	f.BoolVarP(&global.Info, "info", "i", false, helpGlobalInfo)
	f.BoolVarP(&global.LogPrint, "log-print", "l", false, helpGlobalLogPrint)
	f.IntVarP(&global.Memory, "mem", "m", nodeMem,
		fmt.Sprintf(helpGlobalMemoryFmt, nodeMem))
	f.BoolVarP(&global.NoSlurm, "no-slurm", "n", false, helpGlobalNoSlurm)
	f.StringVarP(&global.Profile, "profile", "p", "", helpGlobalProfile)
	f.BoolVarP(&global.Version, "version", "v", false, helpGlobalVersion)

	// Exit status 2 on usage errors, matching argparse.
	root.SetFlagErrorFunc(func(cmd *cobra.Command, err error) error {
		return &usageError{err: err}
	})

	root.AddCommand(
		newCredentialsCmd(app, global),
		newConfigCmd(app, global),
		newIndexCmd(app, global),
		newArchiveCmd(app, global),
		newDeleteCmd(app, global),
		newMountCmd(app, global),
		newUmountCmd(app, global),
		newRestoreCmd(app, global),
		newUpdateCmd(app, global),
		newTestCmd(app, global),
	)

	return root
}

// runGlobalActions handles the global action flags that short-circuit any
// subcommand, in the same precedence order as Python froster's main():
// --version, --info, --log-print, --default-profile. It reports whether one
// of them ran.
func runGlobalActions(cmd *cobra.Command, app App, global GlobalArgs) (bool, error) {
	switch {
	case global.Version:
		printVersion(cmd)
		return true, nil
	case global.Info:
		printInfo(cmd)
		return true, nil
	case global.LogPrint:
		return true, app.LogPrint(cmd.Context(), global)
	case global.DefaultProfile:
		return true, app.SetDefaultProfile(cmd.Context(), global)
	}
	return false, nil
}

func printVersion(cmd *cobra.Command) {
	// Same format as Python: log(f'froster v{importlib.metadata.version("froster")}')
	fmt.Fprintf(cmd.OutOrStdout(), "froster v%s\n", version.Version)
}

func printInfo(cmd *cobra.Command) {
	w := cmd.OutOrStdout()
	exe, err := os.Executable()
	if err != nil {
		exe = "unknown"
	}
	fmt.Fprintf(w, "\nTOOLS\n")
	fmt.Fprintf(w, "\n  froster\n")
	fmt.Fprintf(w, "    version: %s\n", version.Version)
	fmt.Fprintf(w, "    commit: %s\n", version.Commit)
	fmt.Fprintf(w, "    path: %s\n", exe)
	fmt.Fprintf(w, "\n  go\n")
	fmt.Fprintf(w, "    version: %s\n", runtime.Version())
	fmt.Fprintf(w, "    platform: %s/%s\n", runtime.GOOS, runtime.GOARCH)
}

// run wraps a subcommand body so that the global action flags (--version,
// --info, --log-print, --default-profile) short-circuit it, exactly like
// Python froster checks them in main() before dispatching the subcommand
// (e.g. `froster -v archive` prints the version and exits 0).
func run(app App, global *GlobalArgs, body func(ctx context.Context, folders []string) error) func(*cobra.Command, []string) error {
	return func(cmd *cobra.Command, args []string) error {
		if handled, err := runGlobalActions(cmd, app, *global); handled {
			return err
		}
		return body(cmd.Context(), args)
	}
}
