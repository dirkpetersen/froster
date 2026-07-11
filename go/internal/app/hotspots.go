package app

import (
	"context"
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"golang.org/x/sys/unix"

	"github.com/dirkpetersen/froster/go/internal/cli"
	"github.com/dirkpetersen/froster/go/internal/config"
	"github.com/dirkpetersen/froster/go/internal/tui"
	"github.com/dirkpetersen/froster/go/internal/workflow"
)

// archiveSelectHotspots reproduces Archiver.archive_select_hotspots
// (spec §1.2): the interactive hotspot-file → folder selection path used
// when `froster archive` is called without folder arguments.
func (a *App) archiveSelectHotspots(ctx context.Context, s *session, wf *workflow.Workflow, args cli.ArchiveArgs) error {
	hotspotsDir := s.cfg.HotspotsDir()
	if hotspotsDir == "" || !isDir(hotspotsDir) {
		s.log.Logf("%s", "\nNo folders to archive in arguments and no Hotspots CSV files found.")
		s.log.Logf("%s", "\nFor archive a specific folder run:")
		s.log.Logf("%s", "    froster archive \"/your/folder/to/archive\"")
		// The stray leading space reproduces the Python message.
		s.log.Logf("%s", "\n For index a folder a find hotspots run:")
		s.log.Logf("%s", "    froster index \"/your/folder/to/index\"\n")
		return nil
	}

	var csvFiles []string
	entries, err := os.ReadDir(hotspotsDir)
	if err != nil {
		return err
	}
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".csv") {
			csvFiles = append(csvFiles, e.Name())
		}
	}
	if len(csvFiles) == 0 {
		s.log.Logf("%s", "\nNo hotposts found. \n") // (sic)
		s.log.Logf("%s", "You can search for hotspot by indexing folders using command:")
		s.log.Logf("%s", "    froster index \"/your/folder/to/index\"\n")
		s.log.Logf("%s", "For archive a specific folder run:")
		s.log.Logf("%s", "    froster archive \"/your/folder/to/archive\"\n")
		return nil
	}

	sortByModTimeDesc(hotspotsDir, csvFiles)

	picked, ok, err := a.pickString(ctx, "Select a Hotspot file", csvFiles)
	if err != nil {
		return err
	}
	if !ok {
		return exit1() // Python: nothing selected → return False
	}
	hotspotSelected := filepath.Join(hotspotsDir, picked)

	pathResult, filteringSkipped := a.getHotspotFolders(s, hotspotSelected, args.Force)
	pathToDisplay := pathResult
	if pathResult == "" {
		if filteringSkipped {
			pathToDisplay = hotspotSelected
		} else {
			s.log.Logf("\nNo writable hotspots found or accessible in %s.\n", hotspotSelected)
			return nil
		}
	}

	rows, err := readHotspotCSV(pathToDisplay)
	if err != nil {
		fmt.Fprintf(a.stderr(), "Error: %v\n", err)
		return exit1()
	}

	opts := tui.HotspotOptions{
		OlderDays: args.Older,
		NewerDays: args.Newer,
		LargerGiB: args.Larger,
		UseMtime:  args.AgeMtime,
		Profile:   s.profile,
		Recursive: args.Recursive,
		NoTar:     args.NoTar,
		NIHRef:    args.NIHRef,
	}
	res, err := tui.PickHotspots(ctx, rows, opts)
	if err != nil {
		return err
	}
	if len(res.Folders) == 0 {
		return exit1() // no row selected / user quit
	}
	folder := res.Folders[0]

	if filteringSkipped {
		s.log.Logf("Checking write permission for selected folder: %s", folder)
		if !pathWritable(folder) {
			s.log.Logf("\nError: Write permission denied for selected folder: %s\n", folder)
			return exit1()
		}
		s.log.Logf("%s", "  Permission granted.")
	}

	if res.QuitToCLI {
		s.log.Logf("\nTo archive this folder later, run:\n\n    %s\n", res.CLICommand)
		return nil
	}

	// Start Job. DOCUMENTED DEVIATION (fixes dead Python code): the
	// selected folder is appended to the replayed argv so a Slurm
	// submission re-runs non-interactively; Python's equivalent hinges on
	// a '--hotspots' token that never exists, so its batch job would
	// re-open the TUI.
	argv := append(append([]string{}, a.Argv...), folder)
	return a.archiveFolders(ctx, s, wf, args, []string{folder}, argv)
}

// getHotspotFolders reproduces Archiver.get_hotspot_folders +
// _filter_hotspots_by_write_access: filter the hotspot CSV down to
// folders the user can write, caching the result in a per-user copy.
// Returns the CSV path to display and whether filtering was skipped
// (file ≥ 5000 lines).
func (a *App) getHotspotFolders(s *session, hotspotCSV string, force bool) (string, bool) {
	lineCount := countLines(hotspotCSV)
	if lineCount >= 5000 {
		s.log.Logf("Skipping proactive write permission check for large file (%d lines): %s", lineCount, hotspotCSV)
		return "", true
	}

	userDir := filepath.Join(s.cfg.HotspotsDir(), config.Whoami())
	if err := os.MkdirAll(userDir, 0o775); err != nil {
		fmt.Fprintf(a.stderr(), "Error: %v\n", err)
		return "", false
	}
	userCSV := filepath.Join(userDir, filepath.Base(hotspotCSV))

	// Reuse a fresher per-user copy unless --force.
	if uInfo, err := os.Stat(userCSV); err == nil {
		if oInfo, err := os.Stat(hotspotCSV); err == nil && uInfo.ModTime().After(oInfo.ModTime()) {
			if !force {
				return a.checkUserCSVHasRows(s, hotspotCSV, userCSV)
			}
			s.log.Logf("Re-filtering hotspots due to --force flag: %s", hotspotCSV)
		}
	}

	s.log.Logf("%s", "Filtering hotspots for folders with write permissions ...")

	in, err := os.Open(hotspotCSV)
	if err != nil {
		fmt.Fprintf(a.stderr(), "Error: Hotspot file not found: %s\n", hotspotCSV)
		return "", false
	}
	defer in.Close()
	reader := csv.NewReader(in)
	reader.FieldsPerRecord = -1
	header, err := reader.Read()
	if err != nil {
		fmt.Fprintf(a.stderr(), "Error: Hotspot file is empty or has no header: %s\n", hotspotCSV)
		return "", false
	}
	folderCol := -1
	for i, name := range header {
		if name == "Folder" {
			folderCol = i
			break
		}
	}
	if folderCol < 0 {
		fmt.Fprintf(a.stderr(), "Error: 'Folder' column not found in hotspot file: %s\n", hotspotCSV)
		return "", false
	}

	var writable [][]string
	for {
		rec, err := reader.Read()
		if err != nil {
			break
		}
		if folderCol < len(rec) && pathWritable(rec[folderCol]) {
			writable = append(writable, rec)
		}
	}

	out, err := os.Create(userCSV)
	if err != nil {
		fmt.Fprintf(a.stderr(), "Error writing user hotspot file: %s\n", userCSV)
		return "", false
	}
	writer := csv.NewWriter(out)
	writer.UseCRLF = true
	_ = writer.Write(header)
	for _, rec := range writable {
		_ = writer.Write(rec)
	}
	writer.Flush()
	if err := out.Close(); err != nil {
		fmt.Fprintf(a.stderr(), "Error writing user hotspot file: %s\n", userCSV)
		return "", false
	}
	if len(writable) > 0 {
		s.log.Logf("Filtered hotspots written to: %s", userCSV)
	} else {
		s.log.Logf("No writable folders found. Empty file created: %s", userCSV)
	}

	return a.checkUserCSVHasRows(s, hotspotCSV, userCSV)
}

// checkUserCSVHasRows implements get_hotspot_folders' post-check: the
// per-user CSV must contain at least one data row.
func (a *App) checkUserCSVHasRows(s *session, hotspotCSV, userCSV string) (string, bool) {
	rows, err := readHotspotCSV(userCSV)
	if err != nil {
		fmt.Fprintf(a.stderr(), "Error: Filtered hotspot file not found after creation: %s\n", userCSV)
		return "", false
	}
	if len(rows) == 0 {
		s.log.Logf("No writable hotspot folders found in: %s", hotspotCSV)
		return "", false
	}
	return userCSV, false
}

// readHotspotCSV parses a hotspots CSV (columns User,AccD,ModD,GiB,MiBAvg,
// Folder,Group,TiB,FileCount,DirSize) into TUI rows.
func readHotspotCSV(path string) ([]tui.HotspotRow, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	recs, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}
	var rows []tui.HotspotRow
	for i, rec := range recs {
		if i == 0 || len(rec) < 10 {
			continue // header / short row
		}
		atoi := func(s string) int { n, _ := strconv.Atoi(s); return n }
		atoi64 := func(s string) int64 { n, _ := strconv.ParseInt(s, 10, 64); return n }
		rows = append(rows, tui.HotspotRow{
			User:       rec[0],
			AccessDays: atoi(rec[1]),
			ModifyDays: atoi(rec[2]),
			GiB:        atoi(rec[3]),
			AvgMiB:     atoi(rec[4]),
			Folder:     rec[5],
			Group:      rec[6],
			TiB:        atoi(rec[7]),
			FileCount:  atoi64(rec[8]),
			DirSize:    atoi64(rec[9]),
		})
	}
	return rows, nil
}

// pathWritable is Python's _check_path_permissions(path, write_only=True):
// the path must exist and os.access(path, W_OK) must succeed.
func pathWritable(path string) bool {
	if path == "" {
		return false
	}
	if _, err := os.Stat(path); err != nil {
		return false
	}
	return unix.Access(path, unix.W_OK) == nil
}

func isDir(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}

func countLines(path string) int {
	data, err := os.ReadFile(path)
	if err != nil {
		return 0
	}
	count := 0
	for _, b := range data {
		if b == '\n' {
			count++
		}
	}
	if len(data) > 0 && data[len(data)-1] != '\n' {
		count++
	}
	return count
}

// sortByModTimeDesc sorts CSV file names inside dir newest-first (Python
// sorts the hotspot files by mtime descending before the selector).
func sortByModTimeDesc(dir string, names []string) {
	mtime := func(name string) int64 {
		info, err := os.Stat(filepath.Join(dir, name))
		if err != nil {
			return 0
		}
		return info.ModTime().UnixNano()
	}
	sort.SliceStable(names, func(i, j int) bool { return mtime(names[i]) > mtime(names[j]) })
}
