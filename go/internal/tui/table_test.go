package tui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

// --- test helpers -----------------------------------------------------------

func keyMsg(t tea.KeyType) tea.KeyMsg {
	return tea.KeyMsg{Type: t}
}

func runeMsg(s string) tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(s)}
}

func spaceMsg() tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeySpace, Runes: []rune{' '}}
}

// send drives a model through Update with a sequence of messages, the way
// the Bubble Tea runtime would.
func send(t *testing.T, m tea.Model, msgs ...tea.Msg) tea.Model {
	t.Helper()
	for _, msg := range msgs {
		m, _ = m.Update(msg)
	}
	return m
}

func testTableConfig(multi bool) TableConfig {
	return TableConfig{
		Title:   "Test table",
		Columns: []Column{{Title: "Name"}, {Title: "Value"}},
		Rows: [][]string{
			{"alpha", "1"},
			{"bravo", "2"},
			{"charlie", "3"},
		},
		MultiSelect:  multi,
		EnableFilter: true,
	}
}

// --- navigation and single selection ---------------------------------------

func TestTableSelectCursorRow(t *testing.T) {
	m := newTableModel(testTableConfig(false))
	send(t, m, keyMsg(tea.KeyDown), keyMsg(tea.KeyDown), keyMsg(tea.KeyEnter))

	if !m.done {
		t.Fatal("model should be done after enter")
	}
	outcome, rows := m.result()
	if outcome != OutcomeSelected {
		t.Fatalf("outcome = %v, want OutcomeSelected", outcome)
	}
	if len(rows) != 1 || rows[0][0] != "charlie" {
		t.Fatalf("rows = %v, want [[charlie 3]]", rows)
	}
}

func TestTableVimKeysAndBounds(t *testing.T) {
	m := newTableModel(testTableConfig(false))
	// j/j/j/j moves down but clamps at the last row; k moves back up.
	send(t, m, runeMsg("j"), runeMsg("j"), runeMsg("j"), runeMsg("j"), runeMsg("k"))
	if m.cursor != 1 {
		t.Fatalf("cursor = %d, want 1", m.cursor)
	}
}

func TestTableQuitCancels(t *testing.T) {
	for _, msg := range []tea.KeyMsg{runeMsg("q"), keyMsg(tea.KeyEsc), keyMsg(tea.KeyCtrlC)} {
		m := newTableModel(testTableConfig(false))
		send(t, m, msg)
		if !m.done {
			t.Fatalf("%q: model should be done", msg.String())
		}
		if outcome, _ := m.result(); outcome != OutcomeCancelled {
			t.Fatalf("%q: outcome = %v, want OutcomeCancelled", msg.String(), outcome)
		}
	}
}

func TestTableMaxRowsCap(t *testing.T) {
	cfg := testTableConfig(false)
	cfg.MaxRows = 2
	m := newTableModel(cfg)
	if len(m.rows) != 2 {
		t.Fatalf("len(rows) = %d, want 2", len(m.rows))
	}
}

// --- multi-select -----------------------------------------------------------

func TestTableMultiSelect(t *testing.T) {
	m := newTableModel(testTableConfig(true))
	// Toggle rows 0 and 1 (space advances the cursor), then accept.
	send(t, m, spaceMsg(), spaceMsg(), keyMsg(tea.KeyEnter))

	outcome, rows := m.result()
	if outcome != OutcomeSelected {
		t.Fatalf("outcome = %v, want OutcomeSelected", outcome)
	}
	if len(rows) != 2 || rows[0][0] != "alpha" || rows[1][0] != "bravo" {
		t.Fatalf("rows = %v, want alpha and bravo", rows)
	}
}

func TestTableMultiSelectToggleOff(t *testing.T) {
	m := newTableModel(testTableConfig(true))
	// Toggle row 0 on and off again; enter then selects the cursor row.
	send(t, m, spaceMsg(), keyMsg(tea.KeyUp), spaceMsg(), keyMsg(tea.KeyUp), keyMsg(tea.KeyEnter))

	outcome, rows := m.result()
	if outcome != OutcomeSelected {
		t.Fatalf("outcome = %v, want OutcomeSelected", outcome)
	}
	if len(rows) != 1 || rows[0][0] != "alpha" {
		t.Fatalf("rows = %v, want the cursor row [alpha]", rows)
	}
}

// --- filter ------------------------------------------------------------------

func TestTableFilterNarrowsAndSelects(t *testing.T) {
	m := newTableModel(testTableConfig(false))
	send(t, m, runeMsg("/"), runeMsg("brav"))
	if len(m.visible) != 1 {
		t.Fatalf("visible = %v, want a single match", m.visible)
	}
	// Enter closes the filter prompt, second enter selects the match.
	send(t, m, keyMsg(tea.KeyEnter), keyMsg(tea.KeyEnter))
	outcome, rows := m.result()
	if outcome != OutcomeSelected || rows[0][0] != "bravo" {
		t.Fatalf("outcome=%v rows=%v, want bravo selected", outcome, rows)
	}
}

func TestTableFilterEscClears(t *testing.T) {
	m := newTableModel(testTableConfig(false))
	send(t, m, runeMsg("/"), runeMsg("zzz"))
	if len(m.visible) != 0 {
		t.Fatalf("visible = %v, want no matches", m.visible)
	}
	// Enter on an empty result set must not select anything.
	send(t, m, keyMsg(tea.KeyEnter), keyMsg(tea.KeyEnter))
	if m.done {
		t.Fatal("enter with no visible rows should not finish the screen")
	}
	// Esc clears the filter (we are back in table mode after the enter above,
	// so reopen the filter first).
	send(t, m, runeMsg("/"), keyMsg(tea.KeyEsc))
	if len(m.visible) != 3 {
		t.Fatalf("visible = %v, want all rows after esc", m.visible)
	}
}

func TestTableFilterKeysDoNotQuit(t *testing.T) {
	m := newTableModel(testTableConfig(false))
	// "q" typed into the filter is a filter character, not quit.
	send(t, m, runeMsg("/"), runeMsg("q"))
	if m.done {
		t.Fatal("typing q into the filter must not quit")
	}
	if got := m.filter.Value(); got != "q" {
		t.Fatalf("filter value = %q, want %q", got, "q")
	}
}

// --- confirmation modal -------------------------------------------------------

func confirmedTableConfig() TableConfig {
	cfg := testTableConfig(false)
	cfg.Confirm = func([]int, [][]string) *ConfirmConfig {
		return &ConfirmConfig{
			Title: "Sure?",
			Buttons: []ConfirmButton{
				{Label: "Go", Action: ActionAccept},
				{Label: "Back", Action: ActionReturn},
				{Label: "Quit to CLI", Action: ActionQuitToCLI},
			},
		}
	}
	return cfg
}

func TestTableConfirmAccept(t *testing.T) {
	m := newTableModel(confirmedTableConfig())
	send(t, m, keyMsg(tea.KeyEnter))
	if m.modal == nil {
		t.Fatal("enter should open the confirm modal")
	}
	send(t, m, keyMsg(tea.KeyEnter)) // first button: Go
	outcome, rows := m.result()
	if outcome != OutcomeSelected || rows[0][0] != "alpha" {
		t.Fatalf("outcome=%v rows=%v, want alpha accepted", outcome, rows)
	}
}

func TestTableConfirmReturnKeepsTable(t *testing.T) {
	m := newTableModel(confirmedTableConfig())
	send(t, m, keyMsg(tea.KeyEnter), keyMsg(tea.KeyRight), keyMsg(tea.KeyEnter)) // Back
	if m.done {
		t.Fatal("Back must return to the table, not finish")
	}
	if m.modal != nil {
		t.Fatal("modal should be dismissed")
	}
	// The table is still usable afterwards.
	send(t, m, keyMsg(tea.KeyDown), keyMsg(tea.KeyEnter), keyMsg(tea.KeyEnter))
	outcome, rows := m.result()
	if outcome != OutcomeSelected || rows[0][0] != "bravo" {
		t.Fatalf("outcome=%v rows=%v, want bravo accepted after returning", outcome, rows)
	}
}

func TestTableConfirmQuitToCLI(t *testing.T) {
	m := newTableModel(confirmedTableConfig())
	send(t, m,
		keyMsg(tea.KeyDown), keyMsg(tea.KeyEnter), // open modal on bravo
		keyMsg(tea.KeyRight), keyMsg(tea.KeyRight), keyMsg(tea.KeyEnter)) // Quit to CLI
	outcome, rows := m.result()
	if outcome != OutcomeQuitToCLI {
		t.Fatalf("outcome = %v, want OutcomeQuitToCLI", outcome)
	}
	if len(rows) != 1 || rows[0][0] != "bravo" {
		t.Fatalf("rows = %v, want bravo", rows)
	}
}

func TestTableConfirmEscReturnsToTable(t *testing.T) {
	m := newTableModel(confirmedTableConfig())
	send(t, m, keyMsg(tea.KeyEnter), keyMsg(tea.KeyEsc))
	if m.done || m.modal != nil {
		t.Fatal("esc in a table modal must return to the table")
	}
}

// --- rendering smoke tests ----------------------------------------------------

func TestTableViewRendersColumnsAndMarkers(t *testing.T) {
	m := newTableModel(testTableConfig(true))
	send(t, m, spaceMsg())
	view := m.View()
	for _, want := range []string{"Test table", "Name", "Value", "alpha", "[x]", "[ ]"} {
		if !strings.Contains(view, want) {
			t.Errorf("view is missing %q:\n%s", want, view)
		}
	}
}

func TestTableViewModalReplacesTable(t *testing.T) {
	m := newTableModel(confirmedTableConfig())
	send(t, m, keyMsg(tea.KeyEnter))
	view := m.View()
	if !strings.Contains(view, "Sure?") || !strings.Contains(view, "Quit to CLI") {
		t.Errorf("modal view missing title or buttons:\n%s", view)
	}
	if strings.Contains(view, "bravo") {
		t.Errorf("modal view should replace the table:\n%s", view)
	}
}

func TestTableWindowSizeScrolls(t *testing.T) {
	cfg := testTableConfig(false)
	cfg.Rows = nil
	for i := 0; i < 50; i++ {
		cfg.Rows = append(cfg.Rows, []string{"row" + string(rune('a'+i%26)), "x"})
	}
	m := newTableModel(cfg)
	send(t, m, tea.WindowSizeMsg{Width: 80, Height: 12})
	send(t, m, keyMsg(tea.KeyEnd))
	if m.cursor != 49 {
		t.Fatalf("cursor = %d, want 49", m.cursor)
	}
	if m.offset == 0 {
		t.Fatal("offset should have scrolled with the cursor")
	}
}
