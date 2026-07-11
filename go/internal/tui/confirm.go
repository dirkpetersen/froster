package tui

import (
	"context"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// ButtonAction is what pressing a confirmation-modal button does.
type ButtonAction int

const (
	// ActionCancel ends the screen with nothing selected. It is the zero
	// value so an unset EscAction cancels a standalone Confirm.
	ActionCancel ButtonAction = iota
	// ActionAccept accepts the pending selection and ends the screen.
	ActionAccept
	// ActionReturn dismisses the modal and returns to the underlying
	// table ("Back to List" / "Cancel" inside a table flow).
	ActionReturn
	// ActionQuitToCLI ends the screen signalling that the caller should
	// print an equivalent CLI command instead of acting on the selection.
	ActionQuitToCLI
)

// ConfirmButton is one button of a confirmation modal.
type ConfirmButton struct {
	Label  string
	Action ButtonAction
}

// ConfirmConfig describes a confirmation modal: a title, free-form body
// lines and a horizontal row of buttons. It is used both as the overlay of a
// table screen (TableConfig.Confirm) and standalone via Confirm.
type ConfirmConfig struct {
	Title string
	Body  []string
	// Buttons in display order; the first one has initial focus. When
	// empty, Yes (ActionAccept) / No (ActionCancel) are used.
	Buttons []ConfirmButton
	// EscAction is performed on esc/q. The zero value ActionCancel is
	// right for standalone confirms; table screens force it to
	// ActionReturn (esc closes the modal, the table stays), matching the
	// Python modals which only close via buttons.
	EscAction ButtonAction
}

// confirmModel is the shared modal widget. It is not a tea.Model itself; the
// hosting model forwards key messages to handleKey and renders View.
type confirmModel struct {
	cfg   ConfirmConfig
	focus int
}

func newConfirmModel(cfg ConfirmConfig) *confirmModel {
	if len(cfg.Buttons) == 0 {
		cfg.Buttons = []ConfirmButton{
			{Label: "Yes", Action: ActionAccept},
			{Label: "No", Action: ActionCancel},
		}
	}
	return &confirmModel{cfg: cfg}
}

// handleKey processes one key message and returns the pressed button, or nil
// if the modal stays open.
func (c *confirmModel) handleKey(msg tea.KeyMsg) *ConfirmButton {
	switch msg.String() {
	case "left", "shift+tab", "h":
		c.focus = (c.focus - 1 + len(c.cfg.Buttons)) % len(c.cfg.Buttons)
	case "right", "tab", "l":
		c.focus = (c.focus + 1) % len(c.cfg.Buttons)
	case "enter", " ":
		return &c.cfg.Buttons[c.focus]
	case "esc", "q", "ctrl+c":
		return &ConfirmButton{Label: "esc", Action: c.cfg.EscAction}
	}
	return nil
}

var (
	modalBorderStyle = lipgloss.NewStyle().
				Border(lipgloss.ThickBorder()).
				Padding(1, 3)
	modalTitleStyle   = lipgloss.NewStyle().Bold(true)
	buttonStyle       = lipgloss.NewStyle().Padding(0, 2)
	buttonFocusStyle  = buttonStyle.Reverse(true).Bold(true)
	modalButtonRowGap = "  "
)

// View renders the modal box.
func (c *confirmModel) View() string {
	var b strings.Builder
	if c.cfg.Title != "" {
		b.WriteString(modalTitleStyle.Render(c.cfg.Title))
		b.WriteString("\n\n")
	}
	for _, line := range c.cfg.Body {
		b.WriteString(line)
		b.WriteString("\n")
	}
	if len(c.cfg.Body) > 0 {
		b.WriteString("\n")
	}
	buttons := make([]string, len(c.cfg.Buttons))
	for i, btn := range c.cfg.Buttons {
		style := buttonStyle
		if i == c.focus {
			style = buttonFocusStyle
		}
		buttons[i] = style.Render(btn.Label)
	}
	b.WriteString(strings.Join(buttons, modalButtonRowGap))
	return modalBorderStyle.Render(b.String())
}

// confirmApp wraps confirmModel as a standalone Bubble Tea program.
type confirmApp struct {
	modal  *confirmModel
	choice ButtonAction
}

func newConfirmApp(cfg ConfirmConfig) *confirmApp {
	return &confirmApp{modal: newConfirmModel(cfg), choice: ActionCancel}
}

// Init implements tea.Model.
func (a *confirmApp) Init() tea.Cmd { return nil }

// Update implements tea.Model.
func (a *confirmApp) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	if key, ok := msg.(tea.KeyMsg); ok {
		if btn := a.modal.handleKey(key); btn != nil {
			a.choice = btn.Action
			return a, tea.Quit
		}
	}
	return a, nil
}

// View implements tea.Model.
func (a *confirmApp) View() string { return a.modal.View() + "\n" }

// Confirm shows a standalone confirmation modal and returns the action of
// the button the user pressed. With no buttons configured it is a plain
// Yes/No dialog; esc and q map to cfg.EscAction (ActionCancel by default).
func Confirm(ctx context.Context, cfg ConfirmConfig) (ButtonAction, error) {
	final, err := runModel(ctx, newConfirmApp(cfg))
	if err != nil {
		return ActionCancel, err
	}
	return final.(*confirmApp).choice, nil
}
