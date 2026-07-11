package tui

import (
	"context"
	"fmt"
	"strconv"
	"strings"
)

// HotspotRow mirrors one data row of the hotspots CSV written by
// `froster index` (columns: User, AccD, ModD, GiB, MiBAvg, Folder, Group,
// TiB, FileCount, DirSize). The integrator adapts its own hotspot type to
// this struct; the tui package deliberately does not import other internal
// packages.
type HotspotRow struct {
	User string
	// AccessDays is the AccD column: days since the newest atime.
	AccessDays int
	// ModifyDays is the ModD column: days since the newest mtime.
	ModifyDays int
	GiB        int
	AvgMiB     int // MiBAvg: average file size in MiB
	Folder     string
	Group      string
	TiB        int
	// FileCount is pw_fcount, DirSize is pw_dirsum in bytes.
	FileCount int64
	DirSize   int64
}

// HotspotOptions configures PickHotspots. The filter fields correspond to
// the froster archive --older/--newer/--larger/--mtime flags; the echo
// fields reproduce the flags in the command line printed for the
// "Quit to CLI" outcome (Python archive_select_hotspots).
type HotspotOptions struct {
	// OlderDays keeps folders not accessed for more than this many days
	// (0 disables). Mutually exclusive with NewerDays.
	OlderDays int
	// NewerDays keeps folders accessed within this many days (0 disables).
	NewerDays int
	// LargerGiB keeps folders larger than this many GiB (0 disables).
	LargerGiB int
	// UseMtime applies the age filters to ModifyDays instead of
	// AccessDays (--mtime).
	UseMtime bool

	// MultiSelect enables selecting several folders with space.
	MultiSelect bool
	// MaxRows caps displayed rows; 0 means DefaultMaxRows.
	MaxRows int

	// Fields echoed into the generated CLI command.
	Profile   string
	Recursive bool
	NoTar     bool
	NIHRef    string
}

// HotspotResult is the outcome of PickHotspots.
type HotspotResult struct {
	// Folders selected for archiving; empty when the user cancelled.
	Folders []string
	// QuitToCLI is true when the user chose "Quit to CLI"; the caller
	// should print CLICommand and exit instead of archiving.
	QuitToCLI bool
	// CLICommand is the equivalent froster archive command line, set
	// when QuitToCLI is true.
	CLICommand string
}

var hotspotColumns = []Column{
	{Title: "User"}, {Title: "AccD"}, {Title: "ModD"}, {Title: "GiB"},
	{Title: "MiBAvg"}, {Title: "Folder"}, {Title: "Group"}, {Title: "TiB"},
	{Title: "FileCount"}, {Title: "DirSize"},
}

// hotspotFolderColumn is the index of the Folder column, as in the Python
// row layout (0:User 1:AccD 2:ModD 3:GiB 4:MiBAvg 5:Folder 6:Group ...).
const hotspotFolderColumn = 5

// FilterHotspots applies the --older/--newer/--larger flag semantics to
// rows and returns the matching subset. Exported so headless code paths can
// share the exact filter the TUI uses.
func FilterHotspots(rows []HotspotRow, opts HotspotOptions) []HotspotRow {
	out := make([]HotspotRow, 0, len(rows))
	for _, r := range rows {
		age := r.AccessDays
		if opts.UseMtime {
			age = r.ModifyDays
		}
		if opts.OlderDays > 0 && age <= opts.OlderDays {
			continue
		}
		if opts.NewerDays > 0 && age > opts.NewerDays {
			continue
		}
		if opts.LargerGiB > 0 && r.GiB <= opts.LargerGiB {
			continue
		}
		out = append(out, r)
	}
	return out
}

// BuildArchiveCommand renders the froster archive command equivalent to
// archiving folders with opts, as printed by the "Quit to CLI" action
// (mirrors the cmd_str assembly in Python archive_select_hotspots).
func BuildArchiveCommand(folders []string, opts HotspotOptions) string {
	var b strings.Builder
	b.WriteString("froster archive")
	if opts.Profile != "" {
		fmt.Fprintf(&b, " --profile %q", strings.TrimPrefix(opts.Profile, "profile "))
	}
	if opts.Recursive {
		b.WriteString(" --recursive")
	}
	if opts.NoTar {
		b.WriteString(" --no-tar")
	}
	if opts.NIHRef != "" {
		fmt.Fprintf(&b, " --nih-ref %q", opts.NIHRef)
	}
	if opts.LargerGiB > 0 {
		fmt.Fprintf(&b, " --larger %d", opts.LargerGiB)
	}
	if opts.OlderDays > 0 {
		fmt.Fprintf(&b, " --older %d", opts.OlderDays)
	}
	if opts.NewerDays > 0 {
		fmt.Fprintf(&b, " --newer %d", opts.NewerDays)
	}
	if opts.UseMtime {
		b.WriteString(" --mtime")
	}
	for _, f := range folders {
		fmt.Fprintf(&b, " %q", f)
	}
	return b.String()
}

// hotspotConfirm is the ScreenConfirm equivalent shown after picking a row.
func hotspotConfirm([]int, [][]string) *ConfirmConfig {
	return &ConfirmConfig{
		Body: []string{
			"Do you want to start this archiving job now?",
			"Choose 'Quit to CLI' if you would like to archive recursively",
		},
		Buttons: []ConfirmButton{
			{Label: "Start Job", Action: ActionAccept},
			{Label: "Back to List", Action: ActionReturn},
			{Label: "Quit to CLI", Action: ActionQuitToCLI},
		},
	}
}

// newHotspotModel builds the table model for PickHotspots; split out so
// tests can drive it directly.
func newHotspotModel(rows []HotspotRow, opts HotspotOptions) *tableModel {
	filtered := FilterHotspots(rows, opts)
	cells := make([][]string, len(filtered))
	for i, r := range filtered {
		cells[i] = []string{
			r.User,
			strconv.Itoa(r.AccessDays),
			strconv.Itoa(r.ModifyDays),
			strconv.Itoa(r.GiB),
			strconv.Itoa(r.AvgMiB),
			r.Folder,
			r.Group,
			strconv.Itoa(r.TiB),
			strconv.FormatInt(r.FileCount, 10),
			strconv.FormatInt(r.DirSize, 10),
		}
	}
	return newTableModel(TableConfig{
		Title:        "Select a folder to archive",
		Columns:      hotspotColumns,
		Rows:         cells,
		MultiSelect:  opts.MultiSelect,
		EnableFilter: true,
		MaxRows:      opts.MaxRows,
		Confirm:      hotspotConfirm,
	})
}

// hotspotResult translates a finished model into a HotspotResult.
func hotspotResult(m *tableModel, opts HotspotOptions) HotspotResult {
	outcome, rows := m.result()
	if outcome == OutcomeCancelled {
		return HotspotResult{}
	}
	folders := make([]string, len(rows))
	for i, row := range rows {
		folders[i] = row[hotspotFolderColumn]
	}
	res := HotspotResult{Folders: folders}
	if outcome == OutcomeQuitToCLI {
		res.QuitToCLI = true
		res.CLICommand = BuildArchiveCommand(folders, opts)
	}
	return res
}

// PickHotspots shows the hotspot table (Python TableHotspots) and returns
// the folders the user picked. Selecting a row opens a confirmation modal
// with Start Job / Back to List / Quit to CLI; the latter fills
// HotspotResult.CLICommand with an equivalent froster archive command.
// A cancelled screen returns an empty result and a nil error; a missing TTY
// returns ErrNotInteractive.
func PickHotspots(ctx context.Context, rows []HotspotRow, opts HotspotOptions) (HotspotResult, error) {
	final, err := runModel(ctx, newHotspotModel(rows, opts))
	if err != nil {
		return HotspotResult{}, err
	}
	return hotspotResult(final.(*tableModel), opts), nil
}
