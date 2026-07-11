package tui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestConfirmDefaultsToYesNo(t *testing.T) {
	a := newConfirmApp(ConfirmConfig{Title: "Delete?"})
	send(t, a, keyMsg(tea.KeyEnter)) // Yes has initial focus
	if a.choice != ActionAccept {
		t.Fatalf("choice = %v, want ActionAccept", a.choice)
	}
}

func TestConfirmNavigateToNo(t *testing.T) {
	a := newConfirmApp(ConfirmConfig{Title: "Delete?"})
	send(t, a, keyMsg(tea.KeyRight), keyMsg(tea.KeyEnter))
	if a.choice != ActionCancel {
		t.Fatalf("choice = %v, want ActionCancel", a.choice)
	}
}

func TestConfirmFocusWraps(t *testing.T) {
	a := newConfirmApp(ConfirmConfig{Title: "Delete?"})
	// Two buttons: right+right wraps back to Yes; left from Yes wraps to No.
	send(t, a, keyMsg(tea.KeyRight), keyMsg(tea.KeyRight), keyMsg(tea.KeyEnter))
	if a.choice != ActionAccept {
		t.Fatalf("choice = %v, want ActionAccept after wrapping", a.choice)
	}
	b := newConfirmApp(ConfirmConfig{Title: "Delete?"})
	send(t, b, keyMsg(tea.KeyLeft), keyMsg(tea.KeyEnter))
	if b.choice != ActionCancel {
		t.Fatalf("choice = %v, want ActionCancel after wrapping left", b.choice)
	}
}

func TestConfirmEscCancels(t *testing.T) {
	a := newConfirmApp(ConfirmConfig{Title: "Delete?"})
	send(t, a, keyMsg(tea.KeyEsc))
	if a.choice != ActionCancel {
		t.Fatalf("choice = %v, want ActionCancel", a.choice)
	}
}

func TestConfirmViewShowsBodyAndButtons(t *testing.T) {
	a := newConfirmApp(ConfirmConfig{
		Title: "Do you want to start this archiving job now?",
		Body:  []string{"line one", "line two"},
		Buttons: []ConfirmButton{
			{Label: "Start Job", Action: ActionAccept},
			{Label: "Back to List", Action: ActionReturn},
			{Label: "Quit to CLI", Action: ActionQuitToCLI},
		},
	})
	view := a.View()
	for _, want := range []string{
		"Do you want to start this archiving job now?",
		"line one", "line two",
		"Start Job", "Back to List", "Quit to CLI",
	} {
		if !strings.Contains(view, want) {
			t.Errorf("view missing %q:\n%s", want, view)
		}
	}
}
