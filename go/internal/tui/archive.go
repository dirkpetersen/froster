package tui

import "context"

// ArchiveRow is one previously archived folder, matching the columns the
// Python code pulls from froster-archives.json for its TableArchive screen
// (archive_json_get_csv(['local_folder', 's3_storage_class', 'profile',
// 'archive_mode'])). Callers should pass rows sorted newest-first, as the
// Python code does.
type ArchiveRow struct {
	LocalFolder  string
	StorageClass string
	Profile      string
	ArchiveMode  string
}

var archiveColumns = []Column{
	{Title: "local_folder"},
	{Title: "s3_storage_class"},
	{Title: "profile"},
	{Title: "archive_mode"},
}

// newArchiveModel builds the table model for PickArchivedFolder.
func newArchiveModel(rows []ArchiveRow) *tableModel {
	cells := make([][]string, len(rows))
	for i, r := range rows {
		cells[i] = []string{r.LocalFolder, r.StorageClass, r.Profile, r.ArchiveMode}
	}
	return newTableModel(TableConfig{
		Title:        "Select an archived folder",
		Columns:      archiveColumns,
		Rows:         cells,
		EnableFilter: true,
	})
}

// PickArchivedFolder shows the archived-folders table (Python TableArchive,
// used by delete/restore/mount) and returns the local folder of the row the
// user selected. ok is false when the user quit without selecting. A missing
// TTY returns ErrNotInteractive.
func PickArchivedFolder(ctx context.Context, rows []ArchiveRow) (folder string, ok bool, err error) {
	final, err := runModel(ctx, newArchiveModel(rows))
	if err != nil {
		return "", false, err
	}
	outcome, picked := final.(*tableModel).result()
	if outcome != OutcomeSelected || len(picked) == 0 {
		return "", false, nil
	}
	return picked[0][0], true, nil
}
