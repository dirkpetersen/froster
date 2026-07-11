// Package tui implements froster's interactive terminal screens on top of
// Bubble Tea. It replaces the five Textual apps of the Python implementation
// (TableHotspots, TableArchive, TableNIHGrants, TableStorageTierSelector,
// TextualStringListSelector plus the ScreenConfirm/ScreenConfirmTierChange
// modals) with one reusable table-selection component (see table.go) that is
// instantiated per screen with a small config.
//
// Every screen is exposed as a plain function taking data in and returning
// the selection: PickHotspots, PickArchivedFolder, SelectStorageTier,
// PickString and Confirm. The functions never read froster state themselves;
// callers adapt their own row types to the minimal row structs defined here.
// This keeps workflows headless-testable: the models behind the functions can
// be driven directly with key messages in tests.
//
// TUIs are sugar, never load-bearing (GO-ARCHITECTURE.md §6.6): when stdin or
// stdout is not a terminal every screen fails fast with ErrNotInteractive so
// callers can fall back to flags.
package tui

import (
	"context"
	"errors"
	"os"

	tea "github.com/charmbracelet/bubbletea"
	"golang.org/x/term"
)

// ErrNotInteractive is returned by all screen functions when there is no
// usable terminal. Callers should surface the headless alternative (explicit
// folder arguments, --older/--newer/--larger filters, ...) to the user.
var ErrNotInteractive = errors.New("tui: not an interactive terminal (stdin/stdout is not a TTY); use command-line flags instead")

// IsInteractive reports whether both stdin and stdout are attached to a
// terminal. Screens refuse to start when this is false, which covers Slurm
// batch jobs, pipes and redirections.
func IsInteractive() bool {
	return term.IsTerminal(int(os.Stdin.Fd())) && term.IsTerminal(int(os.Stdout.Fd()))
}

// interactive is swapped out in tests so screen functions can be exercised
// without a TTY.
var interactive = IsInteractive

// Outcome describes how the user left a table screen.
type Outcome int

const (
	// OutcomeCancelled means the user quit without selecting anything
	// (q, esc, ctrl+c).
	OutcomeCancelled Outcome = iota
	// OutcomeSelected means the user accepted a selection (and confirmed
	// it, if the screen has a confirmation modal).
	OutcomeSelected
	// OutcomeQuitToCLI means the user chose the "Quit to CLI" action: the
	// selection is returned but the caller should print an equivalent
	// command line instead of acting on it.
	OutcomeQuitToCLI
)

// runModel guards on interactivity and runs m to completion, returning the
// final model. The context cancels the program when done.
func runModel(ctx context.Context, m tea.Model) (tea.Model, error) {
	if !interactive() {
		return nil, ErrNotInteractive
	}
	if ctx == nil {
		ctx = context.Background()
	}
	p := tea.NewProgram(m, tea.WithContext(ctx))
	final, err := p.Run()
	if err != nil {
		return nil, err
	}
	return final, nil
}
