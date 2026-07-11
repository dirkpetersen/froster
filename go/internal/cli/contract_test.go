package cli

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"testing"

	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
)

// The CLI contract (go/testdata/cli-contract.json) is the complete argparse
// surface dumped from Python froster. These tests assert the cobra tree
// matches it in both directions.

type contractFlag struct {
	Default      any      `json:"default"`
	Dest         string   `json:"dest"`
	EnvDependent bool     `json:"env_dependent"`
	Flags        []string `json:"flags"`
	Help         string   `json:"help"`
	Nargs        string   `json:"nargs"`
	Positional   bool     `json:"positional"`
	Type         string   `json:"type"`
}

type contractCommand struct {
	Aliases     []string                   `json:"aliases"`
	Options     []contractFlag             `json:"options"`
	Positionals []contractFlag             `json:"positionals"`
	Subcommands map[string]contractCommand `json:"subcommands"`
}

type contractDoc struct {
	Options     []contractFlag             `json:"options"`
	Positionals []contractFlag             `json:"positionals"`
	Subcommands map[string]contractCommand `json:"subcommands"`
}

// extraFlagAllowlist are cobra flags allowed to exist without a contract
// entry. argparse adds -h/--help automatically too, but the dump script
// excludes it.
var extraFlagAllowlist = map[string]bool{
	"help": true,
}

// extraCommandAllowlist are cobra subcommands allowed to exist without a
// contract entry. "help" and "completion" are cobra built-ins (completion is
// hidden from --help); "umount" implements the contract's `mount` alias as a
// separate command (see newUmountCmd).
var extraCommandAllowlist = map[string]bool{
	"help":       true,
	"completion": true,
	"umount":     true,
}

func loadContract(t *testing.T) contractDoc {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("..", "..", "testdata", "cli-contract.json"))
	if err != nil {
		t.Fatalf("reading contract: %v", err)
	}
	var doc contractDoc
	if err := json.Unmarshal(data, &doc); err != nil {
		t.Fatalf("parsing contract: %v", err)
	}
	return doc
}

// TestMain clears the Slurm environment so env-dependent defaults resolve to
// the same values the contract was dumped with (cores=4, mem=16).
func TestMain(m *testing.M) {
	os.Unsetenv("SLURM_CPUS_ON_NODE")
	os.Unsetenv("SLURM_MEM_PER_NODE")
	os.Exit(m.Run())
}

// longShort splits a contract flags list (e.g. ["-c", "--cores"] or
// ["--newer", "-w"]) into the long name (without dashes) and the shorthand
// letter.
func longShort(t *testing.T, cf contractFlag) (long, short string) {
	t.Helper()
	for _, fl := range cf.Flags {
		switch {
		case strings.HasPrefix(fl, "--"):
			long = strings.TrimPrefix(fl, "--")
		case strings.HasPrefix(fl, "-"):
			short = strings.TrimPrefix(fl, "-")
		}
	}
	if long == "" || short == "" {
		t.Fatalf("contract flag %q: could not determine long/short from %v", cf.Dest, cf.Flags)
	}
	return long, short
}

func pflagType(t *testing.T, contractType string) string {
	t.Helper()
	switch contractType {
	case "bool":
		return "bool"
	case "int":
		return "int"
	case "string":
		return "string"
	default:
		t.Fatalf("unhandled contract flag type %q", contractType)
		return ""
	}
}

// stringifyDefault renders a contract default the way pflag's DefValue does.
// Note restore --days: argparse type "string" with integer default 30 maps
// to the string "30".
func stringifyDefault(t *testing.T, v any) string {
	t.Helper()
	switch d := v.(type) {
	case bool:
		return strconv.FormatBool(d)
	case string:
		return d
	case float64: // encoding/json decodes all numbers as float64
		return strconv.FormatFloat(d, 'f', -1, 64)
	default:
		t.Fatalf("unhandled contract default %v (%T)", v, v)
		return ""
	}
}

func checkFlag(t *testing.T, scope string, fs *pflag.FlagSet, cf contractFlag) {
	t.Helper()
	long, short := longShort(t, cf)
	fl := fs.Lookup(long)
	if fl == nil {
		t.Errorf("%s: flag --%s missing", scope, long)
		return
	}
	if fl.Shorthand != short {
		t.Errorf("%s: flag --%s shorthand = %q, contract wants %q", scope, long, fl.Shorthand, short)
	}
	if want := pflagType(t, cf.Type); fl.Value.Type() != want {
		t.Errorf("%s: flag --%s type = %q, contract wants %q", scope, long, fl.Value.Type(), want)
	}
	if cf.EnvDependent {
		// Env-dependent default: assert presence and parseability only;
		// the value depends on SLURM_* at build time.
		if _, err := strconv.Atoi(fl.DefValue); err != nil {
			t.Errorf("%s: env-dependent flag --%s default %q is not an int", scope, long, fl.DefValue)
		}
	} else if want := stringifyDefault(t, cf.Default); fl.DefValue != want {
		t.Errorf("%s: flag --%s default = %q, contract wants %q", scope, long, fl.DefValue, want)
	}
	if cf.Help == "==SUPPRESS==" {
		// argparse.SUPPRESS -> hidden flag in cobra.
		if !fl.Hidden {
			t.Errorf("%s: flag --%s should be hidden (argparse.SUPPRESS)", scope, long)
		}
	} else if fl.Usage != cf.Help {
		// Env-dependent help (--cores/--mem) embeds the computed default;
		// with the Slurm env cleared in TestMain it too must match the
		// contract verbatim.
		t.Errorf("%s: flag --%s help = %q, contract wants %q", scope, long, fl.Usage, cf.Help)
	}
}

func findCommand(t *testing.T, root *cobra.Command, name string) *cobra.Command {
	t.Helper()
	for _, c := range root.Commands() {
		if c.Name() == name {
			return c
		}
	}
	t.Fatalf("subcommand %q missing from cobra tree", name)
	return nil
}

func TestContractGlobalFlags(t *testing.T) {
	doc := loadContract(t)
	root := NewRootCmd(NotImplementedApp{})

	// Global flags are root-local (not persistent) on purpose: like argparse,
	// they are only accepted before the subcommand (see root.go).
	for _, cf := range doc.Options {
		checkFlag(t, "root", root.Flags(), cf)
	}
	if root.HasPersistentFlags() {
		t.Errorf("root must not use persistent flags (argparse global-flags-before-subcommand semantics)")
	}
	if len(doc.Positionals) != 0 {
		t.Fatalf("contract unexpectedly defines root positionals")
	}
	if err := root.Args(root, []string{"bogus"}); err == nil {
		t.Errorf("root should reject positional arguments")
	}
}

func TestContractSubcommands(t *testing.T) {
	doc := loadContract(t)
	root := NewRootCmd(NotImplementedApp{})

	for name, sub := range doc.Subcommands {
		t.Run(name, func(t *testing.T) {
			cmd := findCommand(t, root, name)

			// mount is special: its contract alias "umount" is implemented
			// as a standalone command with the same flag surface, because
			// the Python dispatcher inspects argv to pick mount vs unmount.
			if name == "mount" {
				if !slices.Equal(sub.Aliases, []string{"umount"}) {
					t.Fatalf("contract drift: mount aliases = %v", sub.Aliases)
				}
				if len(cmd.Aliases) != 0 {
					t.Errorf("mount must not carry cobra aliases (umount is a separate command)")
				}
				umount := findCommand(t, root, "umount")
				for _, cf := range sub.Options {
					checkFlag(t, "umount", umount.Flags(), cf)
				}
				checkPositionals(t, "umount", umount, sub.Positionals)
			} else if !slices.Equal(cmd.Aliases, sub.Aliases) {
				t.Errorf("%s: aliases = %v, contract wants %v", name, cmd.Aliases, sub.Aliases)
			}

			for _, cf := range sub.Options {
				checkFlag(t, name, cmd.Flags(), cf)
			}
			checkPositionals(t, name, cmd, sub.Positionals)

			if len(sub.Subcommands) != 0 {
				t.Fatalf("contract drift: %s has nested subcommands", name)
			}
		})
	}
}

func checkPositionals(t *testing.T, name string, cmd *cobra.Command, positionals []contractFlag) {
	t.Helper()
	switch len(positionals) {
	case 0:
		if err := cmd.Args(cmd, []string{"unexpected"}); err == nil {
			t.Errorf("%s: takes no positionals per contract but accepts them", name)
		}
	case 1:
		if positionals[0].Nargs != "*" {
			t.Fatalf("contract drift: %s positional nargs = %q", name, positionals[0].Nargs)
		}
		if err := cmd.Args(cmd, nil); err != nil {
			t.Errorf("%s: nargs='*' must accept zero args: %v", name, err)
		}
		if err := cmd.Args(cmd, []string{"a", "b", "c"}); err != nil {
			t.Errorf("%s: nargs='*' must accept several args: %v", name, err)
		}
	default:
		t.Fatalf("contract drift: %s has %d positionals", name, len(positionals))
	}
}

// TestNoExtraSurface walks the cobra tree and flags anything that is not in
// the contract (modulo explicit allowlists).
func TestNoExtraSurface(t *testing.T) {
	doc := loadContract(t)
	root := NewRootCmd(NotImplementedApp{})
	// Materialize cobra's implicit help/completion additions so the
	// allowlist is exercised rather than silently unused.
	root.InitDefaultHelpFlag()
	root.InitDefaultHelpCmd()
	root.InitDefaultCompletionCmd()

	contractFlagNames := func(options []contractFlag) map[string]bool {
		names := make(map[string]bool, len(options))
		for _, cf := range options {
			long, _ := longShort(t, cf)
			names[long] = true
		}
		return names
	}

	globals := contractFlagNames(doc.Options)
	root.Flags().VisitAll(func(fl *pflag.Flag) {
		if !globals[fl.Name] && !extraFlagAllowlist[fl.Name] {
			t.Errorf("root: flag --%s is not in the contract", fl.Name)
		}
	})

	for _, cmd := range root.Commands() {
		name := cmd.Name()
		sub, inContract := doc.Subcommands[name]
		if !inContract {
			if !extraCommandAllowlist[name] {
				t.Errorf("subcommand %q is not in the contract", name)
				continue
			}
			if name != "umount" {
				continue // help/completion: cobra built-ins, flags not checked
			}
			// umount implements the contract's mount alias: it must not
			// exceed mount's flag surface.
			sub = doc.Subcommands["mount"]
		}
		known := contractFlagNames(sub.Options)
		cmd.InitDefaultHelpFlag()
		cmd.Flags().VisitAll(func(fl *pflag.Flag) {
			if !known[fl.Name] && !extraFlagAllowlist[fl.Name] {
				t.Errorf("%s: flag --%s is not in the contract", name, fl.Name)
			}
		})
	}

	// And no contract subcommand may be missing (the forward test also
	// covers this; kept here so this test is self-contained).
	for name := range doc.Subcommands {
		found := false
		for _, cmd := range root.Commands() {
			if cmd.Name() == name {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("contract subcommand %q missing from cobra tree", name)
		}
	}
}

// TestEnvDependentDefaults reproduces the Python default computation:
// cores = int($SLURM_CPUS_ON_NODE or 4), mem = int($SLURM_MEM_PER_NODE or 16384) / 1024.
func TestEnvDependentDefaults(t *testing.T) {
	t.Setenv("SLURM_CPUS_ON_NODE", "7")
	t.Setenv("SLURM_MEM_PER_NODE", "32768")
	root := NewRootCmd(NotImplementedApp{})
	if got := root.Flags().Lookup("cores").DefValue; got != "7" {
		t.Errorf("--cores default = %q, want 7 (from SLURM_CPUS_ON_NODE)", got)
	}
	if got := root.Flags().Lookup("cores").Usage; got != fmt.Sprintf(helpGlobalCoresFmt, 7) {
		t.Errorf("--cores help = %q, want embedded default 7", got)
	}
	if got := root.Flags().Lookup("mem").DefValue; got != "32" {
		t.Errorf("--mem default = %q, want 32 (SLURM_MEM_PER_NODE/1024)", got)
	}
	if got := root.Flags().Lookup("mem").Usage; got != fmt.Sprintf(helpGlobalMemoryFmt, 32) {
		t.Errorf("--mem help = %q, want embedded default 32", got)
	}
}
