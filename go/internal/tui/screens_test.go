package tui

import (
	"context"
	"errors"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

// --- non-TTY guard ------------------------------------------------------------

func TestScreensRequireTTY(t *testing.T) {
	old := interactive
	interactive = func() bool { return false }
	defer func() { interactive = old }()

	ctx := context.Background()
	calls := map[string]func() error{
		"PickHotspots": func() error {
			_, err := PickHotspots(ctx, nil, HotspotOptions{})
			return err
		},
		"PickArchivedFolder": func() error {
			_, _, err := PickArchivedFolder(ctx, nil)
			return err
		},
		"SelectStorageTier": func() error {
			_, err := SelectStorageTier(ctx, TierSelectorOptions{})
			return err
		},
		"PickString": func() error {
			_, _, err := PickString(ctx, "title", nil)
			return err
		},
		"Confirm": func() error {
			_, err := Confirm(ctx, ConfirmConfig{Title: "?"})
			return err
		},
	}
	for name, call := range calls {
		if err := call(); !errors.Is(err, ErrNotInteractive) {
			t.Errorf("%s: err = %v, want ErrNotInteractive", name, err)
		}
	}
}

// --- hotspot filters and CLI echo ----------------------------------------------

func sampleHotspots() []HotspotRow {
	return []HotspotRow{
		{User: "alice", AccessDays: 400, ModifyDays: 500, GiB: 200, AvgMiB: 10,
			Folder: "/data/old-big", Group: "lab", TiB: 0, FileCount: 100, DirSize: 214748364800},
		{User: "bob", AccessDays: 10, ModifyDays: 20, GiB: 300, AvgMiB: 20,
			Folder: "/data/new-big", Group: "lab", TiB: 0, FileCount: 50, DirSize: 322122547200},
		{User: "carol", AccessDays: 900, ModifyDays: 30, GiB: 5, AvgMiB: 1,
			Folder: "/data/old-small", Group: "lab", TiB: 0, FileCount: 9999, DirSize: 5368709120},
	}
}

func TestFilterHotspots(t *testing.T) {
	rows := sampleHotspots()

	folders := func(rows []HotspotRow) []string {
		var out []string
		for _, r := range rows {
			out = append(out, r.Folder)
		}
		return out
	}

	tests := []struct {
		name string
		opts HotspotOptions
		want []string
	}{
		{"no filters", HotspotOptions{},
			[]string{"/data/old-big", "/data/new-big", "/data/old-small"}},
		{"older 100 days", HotspotOptions{OlderDays: 100},
			[]string{"/data/old-big", "/data/old-small"}},
		{"newer 30 days", HotspotOptions{NewerDays: 30},
			[]string{"/data/new-big"}},
		{"larger 100 GiB", HotspotOptions{LargerGiB: 100},
			[]string{"/data/old-big", "/data/new-big"}},
		{"older and larger", HotspotOptions{OlderDays: 100, LargerGiB: 100},
			[]string{"/data/old-big"}},
		{"older 100 mtime", HotspotOptions{OlderDays: 100, UseMtime: true},
			[]string{"/data/old-big"}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := folders(FilterHotspots(rows, tt.opts))
			if strings.Join(got, ",") != strings.Join(tt.want, ",") {
				t.Errorf("got %v, want %v", got, tt.want)
			}
		})
	}
}

func TestBuildArchiveCommand(t *testing.T) {
	opts := HotspotOptions{
		Profile:   "profile aws",
		Recursive: true,
		NoTar:     true,
		NIHRef:    "R01HL123456",
		LargerGiB: 100,
		OlderDays: 30,
		UseMtime:  true,
	}
	got := BuildArchiveCommand([]string{"/data/old-big"}, opts)
	want := `froster archive --profile "aws" --recursive --no-tar` +
		` --nih-ref "R01HL123456" --larger 100 --older 30 --mtime "/data/old-big"`
	if got != want {
		t.Errorf("got:\n%s\nwant:\n%s", got, want)
	}

	if got := BuildArchiveCommand([]string{"/x"}, HotspotOptions{}); got != `froster archive "/x"` {
		t.Errorf("minimal command = %q", got)
	}
}

// --- hotspot picker flow --------------------------------------------------------

func TestHotspotFlowStartJob(t *testing.T) {
	m := newHotspotModel(sampleHotspots(), HotspotOptions{})
	// Pick the second row, confirm with "Start Job".
	send(t, m, keyMsg(tea.KeyDown), keyMsg(tea.KeyEnter))
	if m.modal == nil {
		t.Fatal("selecting a hotspot should open the ScreenConfirm modal")
	}
	send(t, m, keyMsg(tea.KeyEnter)) // Start Job

	res := hotspotResult(m, HotspotOptions{})
	if res.QuitToCLI {
		t.Fatal("QuitToCLI should be false for Start Job")
	}
	if len(res.Folders) != 1 || res.Folders[0] != "/data/new-big" {
		t.Fatalf("Folders = %v, want [/data/new-big]", res.Folders)
	}
}

func TestHotspotFlowQuitToCLI(t *testing.T) {
	opts := HotspotOptions{OlderDays: 100, LargerGiB: 100}
	m := newHotspotModel(sampleHotspots(), opts)
	if len(m.rows) != 1 {
		t.Fatalf("filters should leave 1 row, got %d", len(m.rows))
	}
	send(t, m, keyMsg(tea.KeyEnter), // open modal
		keyMsg(tea.KeyRight), keyMsg(tea.KeyRight), keyMsg(tea.KeyEnter)) // Quit to CLI

	res := hotspotResult(m, opts)
	if !res.QuitToCLI {
		t.Fatal("QuitToCLI should be true")
	}
	if res.CLICommand != BuildArchiveCommand([]string{"/data/old-big"}, opts) {
		t.Errorf("CLICommand = %q", res.CLICommand)
	}
	if !strings.Contains(res.CLICommand, `--older 100`) ||
		!strings.Contains(res.CLICommand, `"/data/old-big"`) {
		t.Errorf("CLICommand missing flags or folder: %q", res.CLICommand)
	}
}

func TestHotspotFlowBackToListThenQuit(t *testing.T) {
	m := newHotspotModel(sampleHotspots(), HotspotOptions{})
	send(t, m, keyMsg(tea.KeyEnter), // open modal
		keyMsg(tea.KeyRight), keyMsg(tea.KeyEnter)) // Back to List
	if m.done || m.modal != nil {
		t.Fatal("Back to List should keep the table open")
	}
	send(t, m, runeMsg("q"))
	res := hotspotResult(m, HotspotOptions{})
	if len(res.Folders) != 0 || res.QuitToCLI {
		t.Fatalf("cancelled screen should return an empty result, got %+v", res)
	}
}

func TestHotspotMultiSelect(t *testing.T) {
	m := newHotspotModel(sampleHotspots(), HotspotOptions{MultiSelect: true})
	send(t, m, spaceMsg(), spaceMsg(), keyMsg(tea.KeyEnter), keyMsg(tea.KeyEnter))
	res := hotspotResult(m, HotspotOptions{MultiSelect: true})
	want := []string{"/data/old-big", "/data/new-big"}
	if strings.Join(res.Folders, ",") != strings.Join(want, ",") {
		t.Fatalf("Folders = %v, want %v", res.Folders, want)
	}
}

// --- archived folders picker ------------------------------------------------------

func TestArchivePickerSelects(t *testing.T) {
	rows := []ArchiveRow{
		{LocalFolder: "/data/a", StorageClass: "DEEP_ARCHIVE", Profile: "aws", ArchiveMode: "Single"},
		{LocalFolder: "/data/b", StorageClass: "GLACIER", Profile: "aws", ArchiveMode: "Recursive"},
	}
	m := newArchiveModel(rows)
	send(t, m, keyMsg(tea.KeyDown), keyMsg(tea.KeyEnter))
	outcome, picked := m.result()
	if outcome != OutcomeSelected || picked[0][0] != "/data/b" {
		t.Fatalf("outcome=%v picked=%v, want /data/b", outcome, picked)
	}
}

// --- storage tier selector ---------------------------------------------------------

func tierOpts() TierSelectorOptions {
	return TierSelectorOptions{
		CurrentTier:    "DEEP_ARCHIVE",
		Folder:         "/data/a",
		TotalSizeBytes: 5 << 30, // 5 GiB
		ObjectCount:    1234,
	}
}

func TestTierModelExcludesCurrentTier(t *testing.T) {
	m, shown := newTierModel(tierOpts())
	if len(shown) != len(StorageTiers)-1 {
		t.Fatalf("shown = %d tiers, want %d", len(shown), len(StorageTiers)-1)
	}
	for _, tier := range shown {
		if tier.Key == "DEEP_ARCHIVE" {
			t.Fatal("current tier must not be offered")
		}
	}
	view := m.View()
	for _, want := range []string{
		"Change Storage Tier", "Folder: /data/a", "Current tier: DEEP_ARCHIVE",
		"Total size: 5.00 GiB", "Object count: 1234",
		"Storage Cost", "Retrieval Time", "$2.50-23/TiB/mo",
	} {
		if !strings.Contains(view, want) {
			t.Errorf("view missing %q", want)
		}
	}
}

func TestTierSelectProceed(t *testing.T) {
	m, shown := newTierModel(tierOpts())
	send(t, m, keyMsg(tea.KeyDown), keyMsg(tea.KeyEnter)) // STANDARD_IA
	if m.modal == nil {
		t.Fatal("selecting a tier should open the confirmation modal")
	}
	modalView := m.modal.View()
	for _, want := range []string{"Confirm Storage Tier Change", "New tier: STANDARD_IA",
		"Objects to change: 1234", "Total size: 5.00 GiB"} {
		if !strings.Contains(modalView, want) {
			t.Errorf("modal missing %q:\n%s", want, modalView)
		}
	}
	send(t, m, keyMsg(tea.KeyEnter)) // Proceed
	if m.outcome != OutcomeSelected || shown[m.picked[0]].Key != "STANDARD_IA" {
		t.Fatalf("outcome=%v picked=%v, want STANDARD_IA", m.outcome, m.picked)
	}
}

func TestTierCancelReturnsToTable(t *testing.T) {
	m, shown := newTierModel(tierOpts())
	send(t, m, keyMsg(tea.KeyEnter), // modal for first tier
		keyMsg(tea.KeyRight), keyMsg(tea.KeyEnter)) // Cancel
	if m.done || m.modal != nil {
		t.Fatal("Cancel should return to the tier table")
	}
	// The user can pick another tier afterwards.
	send(t, m, keyMsg(tea.KeyDown), keyMsg(tea.KeyDown), keyMsg(tea.KeyEnter), keyMsg(tea.KeyEnter))
	if m.outcome != OutcomeSelected || shown[m.picked[0]].Key != "ONEZONE_IA" {
		t.Fatalf("picked = %v, want ONEZONE_IA", m.picked)
	}
}

func TestTierQuitCancels(t *testing.T) {
	m, _ := newTierModel(tierOpts())
	send(t, m, keyMsg(tea.KeyEsc))
	if m.outcome != OutcomeCancelled {
		t.Fatalf("outcome = %v, want OutcomeCancelled", m.outcome)
	}
}

// --- string list selector -------------------------------------------------------------

func TestStringListSelect(t *testing.T) {
	m := newStringListModel("Select a Hotspot file", []string{"a.csv", "b.csv", "c.csv"})
	send(t, m, keyMsg(tea.KeyDown), keyMsg(tea.KeyDown), keyMsg(tea.KeyEnter))
	outcome, picked := m.result()
	if outcome != OutcomeSelected || picked[0][0] != "c.csv" {
		t.Fatalf("outcome=%v picked=%v, want c.csv", outcome, picked)
	}
}

func TestStringListQuit(t *testing.T) {
	m := newStringListModel("Select a Hotspot file", []string{"a.csv"})
	send(t, m, runeMsg("q"))
	if outcome, _ := m.result(); outcome != OutcomeCancelled {
		t.Fatalf("outcome = %v, want OutcomeCancelled", outcome)
	}
}
