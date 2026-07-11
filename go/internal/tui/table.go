package tui

import (
	"strconv"
	"strings"

	"github.com/charmbracelet/bubbles/key"
	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// DefaultMaxRows caps the number of rows a table screen displays, matching
// the Python MAXHOTSPOTS constant.
const DefaultMaxRows = 5000

// Column describes one table column.
type Column struct {
	Title string
	// Width is the rendered width in cells; 0 auto-sizes to the widest
	// value (capped at maxAutoWidth).
	Width int
}

// TableConfig configures the reusable table-selection screen. All five
// froster table TUIs are instances of this one component.
type TableConfig struct {
	// Title is rendered bold above the table.
	Title string
	// InfoLines are context lines rendered between title and table
	// (e.g. the tier selector's folder/size/object-count block).
	InfoLines []string
	Columns   []Column
	// Rows hold one string per column.
	Rows [][]string
	// MultiSelect lets space toggle rows; enter accepts the toggled set
	// (or the cursor row when nothing is toggled).
	MultiSelect bool
	// EnableFilter enables a "/" case-insensitive substring filter.
	EnableFilter bool
	// MaxRows caps the rows shown; 0 means DefaultMaxRows, negative
	// means unlimited.
	MaxRows int
	// FooterLines are hint lines rendered below the table.
	FooterLines []string
	// Confirm, when non-nil, is called on enter with the indices (into
	// Rows) and cell values about to be accepted. A non-nil result is
	// shown as a modal; nil accepts immediately. Inside the modal,
	// ActionAccept ends the screen with OutcomeSelected, ActionReturn
	// goes back to the table, ActionQuitToCLI ends with
	// OutcomeQuitToCLI and ActionCancel ends with OutcomeCancelled.
	Confirm func(indices []int, rows [][]string) *ConfirmConfig
}

// tableKeyMap holds the key bindings of the table screen.
type tableKeyMap struct {
	Up, Down, PageUp, PageDown, Home, End key.Binding
	Toggle, Accept, Filter, Quit          key.Binding
}

func defaultTableKeys() tableKeyMap {
	return tableKeyMap{
		Up:       key.NewBinding(key.WithKeys("up", "k"), key.WithHelp("↑/k", "up")),
		Down:     key.NewBinding(key.WithKeys("down", "j"), key.WithHelp("↓/j", "down")),
		PageUp:   key.NewBinding(key.WithKeys("pgup", "ctrl+b"), key.WithHelp("pgup", "page up")),
		PageDown: key.NewBinding(key.WithKeys("pgdown", "ctrl+f"), key.WithHelp("pgdn", "page down")),
		Home:     key.NewBinding(key.WithKeys("home", "g"), key.WithHelp("g", "top")),
		End:      key.NewBinding(key.WithKeys("end", "G"), key.WithHelp("G", "bottom")),
		Toggle:   key.NewBinding(key.WithKeys(" "), key.WithHelp("space", "toggle")),
		Accept:   key.NewBinding(key.WithKeys("enter"), key.WithHelp("enter", "select")),
		Filter:   key.NewBinding(key.WithKeys("/"), key.WithHelp("/", "filter")),
		Quit:     key.NewBinding(key.WithKeys("q", "esc", "ctrl+c"), key.WithHelp("q", "quit")),
	}
}

const (
	defaultViewRows = 20
	maxAutoWidth    = 80
	viewChromeLines = 8 // rough title/header/footer overhead for sizing
)

// tableModel is the Bubble Tea model behind every table screen.
type tableModel struct {
	cfg  TableConfig
	keys tableKeyMap

	rows    [][]string // capped copy of cfg.Rows
	visible []int      // indices into rows matching the filter
	cursor  int        // position within visible
	offset  int        // first visible row rendered
	height  int        // rows rendered at once

	selected map[int]bool // multi-select marks, keyed by row index

	filtering bool
	filter    textinput.Model

	modal   *confirmModel
	pending []int // rows awaiting modal confirmation

	done    bool
	outcome Outcome
	picked  []int // accepted row indices
}

func newTableModel(cfg TableConfig) *tableModel {
	maxRows := cfg.MaxRows
	if maxRows == 0 {
		maxRows = DefaultMaxRows
	}
	rows := cfg.Rows
	if maxRows > 0 && len(rows) > maxRows {
		rows = rows[:maxRows]
	}
	filter := textinput.New()
	filter.Prompt = "/"
	filter.Placeholder = "filter"
	m := &tableModel{
		cfg:      cfg,
		keys:     defaultTableKeys(),
		rows:     rows,
		height:   defaultViewRows,
		selected: make(map[int]bool),
		filter:   filter,
	}
	m.applyFilter()
	return m
}

// Init implements tea.Model.
func (m *tableModel) Init() tea.Cmd { return nil }

// Update implements tea.Model.
func (m *tableModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		h := msg.Height - viewChromeLines - len(m.cfg.InfoLines) - len(m.cfg.FooterLines)
		if h < 3 {
			h = 3
		}
		m.height = h
		m.scrollToCursor()
		return m, nil
	case tea.KeyMsg:
		if m.modal != nil {
			return m.updateModal(msg)
		}
		if m.filtering {
			return m.updateFilter(msg)
		}
		return m.updateTable(msg)
	}
	return m, nil
}

func (m *tableModel) updateTable(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch {
	case key.Matches(msg, m.keys.Quit):
		return m.finish(OutcomeCancelled, nil)
	case key.Matches(msg, m.keys.Up):
		m.moveCursor(-1)
	case key.Matches(msg, m.keys.Down):
		m.moveCursor(1)
	case key.Matches(msg, m.keys.PageUp):
		m.moveCursor(-m.height)
	case key.Matches(msg, m.keys.PageDown):
		m.moveCursor(m.height)
	case key.Matches(msg, m.keys.Home):
		m.cursor = 0
		m.scrollToCursor()
	case key.Matches(msg, m.keys.End):
		m.cursor = max(0, len(m.visible)-1)
		m.scrollToCursor()
	case key.Matches(msg, m.keys.Toggle) && m.cfg.MultiSelect:
		if len(m.visible) > 0 {
			idx := m.visible[m.cursor]
			if m.selected[idx] {
				delete(m.selected, idx)
			} else {
				m.selected[idx] = true
			}
			m.moveCursor(1)
		}
	case key.Matches(msg, m.keys.Filter) && m.cfg.EnableFilter:
		m.filtering = true
		return m, m.filter.Focus()
	case key.Matches(msg, m.keys.Accept):
		return m.accept()
	}
	return m, nil
}

func (m *tableModel) updateFilter(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "enter":
		m.filtering = false
		m.filter.Blur()
	case "esc":
		m.filtering = false
		m.filter.SetValue("")
		m.filter.Blur()
		m.applyFilter()
	case "ctrl+c":
		return m.finish(OutcomeCancelled, nil)
	default:
		var cmd tea.Cmd
		m.filter, cmd = m.filter.Update(msg)
		m.applyFilter()
		return m, cmd
	}
	return m, nil
}

func (m *tableModel) updateModal(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	btn := m.modal.handleKey(msg)
	if btn == nil {
		return m, nil
	}
	switch btn.Action {
	case ActionAccept:
		return m.finish(OutcomeSelected, m.pending)
	case ActionQuitToCLI:
		return m.finish(OutcomeQuitToCLI, m.pending)
	case ActionCancel:
		return m.finish(OutcomeCancelled, nil)
	default: // ActionReturn
		m.modal = nil
		m.pending = nil
	}
	return m, nil
}

// accept gathers the current selection and either confirms it via modal or
// finishes immediately.
func (m *tableModel) accept() (tea.Model, tea.Cmd) {
	indices := m.currentSelection()
	if len(indices) == 0 {
		return m, nil
	}
	if m.cfg.Confirm != nil {
		if cc := m.cfg.Confirm(indices, m.cells(indices)); cc != nil {
			if cc.EscAction == ActionCancel {
				// Inside a table flow esc closes the modal and
				// keeps the table, like the Python modals.
				cc.EscAction = ActionReturn
			}
			m.pending = indices
			m.modal = newConfirmModel(*cc)
			return m, nil
		}
	}
	return m.finish(OutcomeSelected, indices)
}

// currentSelection returns the toggled rows (in table order) or, when none
// are toggled or multi-select is off, the cursor row.
func (m *tableModel) currentSelection() []int {
	if m.cfg.MultiSelect && len(m.selected) > 0 {
		var indices []int
		for i := range m.rows {
			if m.selected[i] {
				indices = append(indices, i)
			}
		}
		return indices
	}
	if len(m.visible) == 0 {
		return nil
	}
	return []int{m.visible[m.cursor]}
}

func (m *tableModel) cells(indices []int) [][]string {
	out := make([][]string, len(indices))
	for i, idx := range indices {
		out[i] = m.rows[idx]
	}
	return out
}

func (m *tableModel) finish(o Outcome, indices []int) (tea.Model, tea.Cmd) {
	m.outcome = o
	m.picked = indices
	m.modal = nil
	m.pending = nil
	m.done = true
	return m, tea.Quit
}

// result returns the accepted rows after the program has finished.
func (m *tableModel) result() (Outcome, [][]string) {
	return m.outcome, m.cells(m.picked)
}

func (m *tableModel) moveCursor(delta int) {
	if len(m.visible) == 0 {
		m.cursor = 0
		return
	}
	m.cursor += delta
	if m.cursor < 0 {
		m.cursor = 0
	}
	if m.cursor > len(m.visible)-1 {
		m.cursor = len(m.visible) - 1
	}
	m.scrollToCursor()
}

func (m *tableModel) scrollToCursor() {
	if m.cursor < m.offset {
		m.offset = m.cursor
	}
	if m.cursor >= m.offset+m.height {
		m.offset = m.cursor - m.height + 1
	}
	if m.offset < 0 {
		m.offset = 0
	}
}

// applyFilter recomputes visible rows from the filter input.
func (m *tableModel) applyFilter() {
	needle := strings.ToLower(strings.TrimSpace(m.filter.Value()))
	m.visible = m.visible[:0]
	for i, row := range m.rows {
		if needle == "" || rowMatches(row, needle) {
			m.visible = append(m.visible, i)
		}
	}
	if m.cursor > len(m.visible)-1 {
		m.cursor = max(0, len(m.visible)-1)
	}
	m.scrollToCursor()
}

func rowMatches(row []string, needle string) bool {
	for _, cell := range row {
		if strings.Contains(strings.ToLower(cell), needle) {
			return true
		}
	}
	return false
}

var (
	titleStyle  = lipgloss.NewStyle().Bold(true)
	headerStyle = lipgloss.NewStyle().Bold(true).Underline(true)
	cursorStyle = lipgloss.NewStyle().Reverse(true)
	dimStyle    = lipgloss.NewStyle().Faint(true)
)

// View implements tea.Model.
func (m *tableModel) View() string {
	if m.done {
		return ""
	}
	if m.modal != nil {
		return m.modal.View() + "\n"
	}

	var b strings.Builder
	if m.cfg.Title != "" {
		b.WriteString(titleStyle.Render(m.cfg.Title))
		b.WriteString("\n")
	}
	for _, line := range m.cfg.InfoLines {
		b.WriteString(line)
		b.WriteString("\n")
	}
	if m.filtering || m.filter.Value() != "" {
		b.WriteString(m.filter.View())
		b.WriteString("\n")
	}

	widths := m.columnWidths()
	marker := m.cfg.MultiSelect

	// Header.
	header := make([]string, len(m.cfg.Columns))
	for i, col := range m.cfg.Columns {
		header[i] = pad(col.Title, widths[i])
	}
	if marker {
		b.WriteString("    ")
	}
	b.WriteString(headerStyle.Render(strings.Join(header, "  ")))
	b.WriteString("\n")

	// Rows.
	end := min(m.offset+m.height, len(m.visible))
	for vi := m.offset; vi < end; vi++ {
		idx := m.visible[vi]
		row := m.rows[idx]
		cells := make([]string, len(m.cfg.Columns))
		for i := range m.cfg.Columns {
			val := ""
			if i < len(row) {
				val = row[i]
			}
			cells[i] = pad(val, widths[i])
		}
		line := strings.Join(cells, "  ")
		if marker {
			if m.selected[idx] {
				line = "[x] " + line
			} else {
				line = "[ ] " + line
			}
		}
		if vi == m.cursor {
			line = cursorStyle.Render(line)
		}
		b.WriteString(line)
		b.WriteString("\n")
	}
	if len(m.visible) == 0 {
		b.WriteString(dimStyle.Render("(no rows)"))
		b.WriteString("\n")
	}
	if len(m.visible) > m.height {
		b.WriteString(dimStyle.Render(
			"… " + strconv.Itoa(m.offset+1) + "-" + strconv.Itoa(end) +
				" of " + strconv.Itoa(len(m.visible))))
		b.WriteString("\n")
	}

	// Footer.
	for _, line := range m.cfg.FooterLines {
		b.WriteString(line)
		b.WriteString("\n")
	}
	hints := []string{"↑/↓ move", "enter select"}
	if m.cfg.MultiSelect {
		hints = append(hints, "space toggle")
	}
	if m.cfg.EnableFilter {
		hints = append(hints, "/ filter")
	}
	hints = append(hints, "q quit")
	b.WriteString(dimStyle.Render(strings.Join(hints, " · ")))
	b.WriteString("\n")
	return b.String()
}

// columnWidths computes the rendered width of each column.
func (m *tableModel) columnWidths() []int {
	widths := make([]int, len(m.cfg.Columns))
	for i, col := range m.cfg.Columns {
		if col.Width > 0 {
			widths[i] = col.Width
			continue
		}
		w := lipgloss.Width(col.Title)
		for _, row := range m.rows {
			if i < len(row) {
				if cw := lipgloss.Width(row[i]); cw > w {
					w = cw
				}
			}
		}
		if w > maxAutoWidth {
			w = maxAutoWidth
		}
		widths[i] = w
	}
	return widths
}

// pad right-pads (or truncates with an ellipsis) s to width cells.
func pad(s string, width int) string {
	w := lipgloss.Width(s)
	if w > width {
		runes := []rune(s)
		if width > 1 && len(runes) > width-1 {
			return string(runes[:width-1]) + "…"
		}
		return string(runes[:width])
	}
	return s + strings.Repeat(" ", width-w)
}
