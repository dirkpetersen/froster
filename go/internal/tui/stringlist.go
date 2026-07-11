package tui

import "context"

// newStringListModel builds the table model for PickString.
func newStringListModel(title string, items []string) *tableModel {
	cells := make([][]string, len(items))
	for i, item := range items {
		cells[i] = []string{item}
	}
	return newTableModel(TableConfig{
		Columns:      []Column{{Title: title}},
		Rows:         cells,
		EnableFilter: true,
	})
}

// PickString shows a single-column selection list (Python
// TextualStringListSelector, e.g. "Select a Hotspot file") and returns the
// chosen item. ok is false when the user quit without selecting. A missing
// TTY returns ErrNotInteractive.
func PickString(ctx context.Context, title string, items []string) (item string, ok bool, err error) {
	final, err := runModel(ctx, newStringListModel(title, items))
	if err != nil {
		return "", false, err
	}
	outcome, picked := final.(*tableModel).result()
	if outcome != OutcomeSelected || len(picked) == 0 {
		return "", false, nil
	}
	return picked[0][0], true, nil
}
