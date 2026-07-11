package workflow

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/dirkpetersen/froster/go/internal/hotspots"
	"github.com/dirkpetersen/froster/go/internal/walker"
)

// IndexOptions carries the index-specific flags.
type IndexOptions struct {
	Force     bool   // -f/--force: re-index even when a hotspot CSV exists
	PwalkCopy string // -y/--pwalk-copy: directory receiving the raw scan CSV
	// HotspotsDir is the destination directory for hotspot CSV files
	// (cfg.hotspots_dir).
	HotspotsDir string
}

// tebi is 2^40, the TiB divisor used in the index summary.
const tebi = 1099511627776

// daysAged are the aging buckets of the index summary (spec: Archiver
// _index_locally's daysaged list).
var daysAged = hotspots.DaysAged

// IndexCollision runs the recursive-dependency check with the index error
// message; callers run it before the Slurm gate, like Archiver.index.
func (w *Workflow) IndexCollision(folders []string) bool {
	if w.checkRecursiveCollision(folders) {
		w.echo("\nError: You cannot index folders if there is a dependency between them. Specify only the parent folder.\n")
		return true
	}
	return false
}

// Index reproduces Archiver.index's local path: a per-folder
// scan+aggregate (_index_locally). The dependency check (IndexCollision)
// and the Slurm gate live in the app layer, in Python's order.
func (w *Workflow) Index(folders []string, opts IndexOptions) error {
	ok := true
	for _, folder := range folders {
		if !w.indexLocally(folder, opts) {
			ok = false
		}
	}
	if !ok {
		w.echo("\nWARNING: Some folders may have permission issues or are locked. Check the output above.\n")
		return ErrReported
	}
	return nil
}

// HotspotCSVPath returns the hotspot CSV location for a folder, creating
// the hotspots directory (mode 0775) like Python's get_hotspots_path. The
// file name encodes the path with '/' replaced by '+' (Python
// _get_hotspots_filename — whose mount-aware '@' branch is dead code that
// is unconditionally overwritten, spec §6.1).
func (w *Workflow) HotspotCSVPath(hotspotsDir, folder string) (string, error) {
	if err := os.MkdirAll(hotspotsDir, 0o775); err != nil {
		return "", err
	}
	return filepath.Join(hotspotsDir, HotspotFileName(folder)), nil
}

// HotspotFileName is the hotspot CSV file name for a folder.
func HotspotFileName(folder string) string {
	return strings.ReplaceAll(folder, "/", "+") + ".csv"
}

// indexLocally reproduces Archiver._index_locally with the Go-native
// pipeline: internal/walker replaces the pwalk subprocess and
// internal/hotspots replaces the grep|iconv|DuckDB stage. The intermediate
// progress messages are kept for output parity.
func (w *Workflow) indexLocally(folder string, opts IndexOptions) bool {
	// NOTE: Python's "\nINDEXING {folder}" line (both variants) is passed
	// flush=True into its log() helper, which re-passes flush to print()
	// that already receives flush=True — the resulting TypeError is
	// swallowed and the line is NEVER printed. Reproduced by not printing
	// it (verified against the golden fixture logs).

	var hotspotCSV string
	if opts.PwalkCopy == "" {
		var err error
		hotspotCSV, err = w.HotspotCSVPath(opts.HotspotsDir, folder)
		if err != nil {
			w.echoErr(fmt.Sprintf("Error: %v", err))
			return false
		}
		if _, err := os.Stat(hotspotCSV); err == nil && !opts.Force {
			w.echof("FOLDER ALREADY INDEXED at %s", hotspotCSV)
			w.echo("\nUse \"-f\" or \"--force\" flag to force indexing again.\n")
			return true
		}
	}

	// Scan the tree (pwalk replacement).
	tmp, err := os.CreateTemp("", "froster-pwalk-*")
	if err != nil {
		w.echoErr(fmt.Sprintf("Error: %v", err))
		return false
	}
	tmpPath := tmp.Name()
	tmp.Close()
	defer os.Remove(tmpPath)

	w.echof("  Running pwalk filesystem scan on %s...", quoteDouble(folder))
	summary, err := walker.WalkToFile(folder, tmpPath, walker.Options{
		NoSnap: true,
		OneFS:  true,
		Header: true,
	})
	w.echo("    ...pwalk scan complete.")
	if err != nil {
		w.echoErr(fmt.Sprintf("\nError: filesystem scan of %s failed: %v\n", folder, err))
		return false
	}

	// Permission problems: Python scans pwalk's stderr for "Permission
	// denied" and prints a warning with the first such line.
	permissionDenied := false
	for _, msg := range summary.Errs {
		if strings.Contains(strings.ToLower(msg), "permission denied") {
			w.echof("\nWARNING:\n"+
				"    You don't have enough permissions in one or more files or folders.\n"+
				"    First error message with permission denied:\n\n"+
				"        %s\n\n"+
				"    You can check the permissions of the folders using the command:\n"+
				"        froster index --permissions \"/your/folder\"\n", quoteDouble(msg))
			permissionDenied = true
			break
		}
	}

	// --pwalk-copy: save the scan output (transcoded ISO-8859-1 → UTF-8
	// like Python's iconv step, directories included). The hotspot
	// analysis still runs afterwards, exactly like Python.
	if opts.PwalkCopy != "" {
		copyPath := filepath.Join(opts.PwalkCopy, HotspotFileName(folder))
		if err := transcodeLatin1File(tmpPath, copyPath); err != nil {
			w.echoErr(fmt.Sprintf("\nError: copying pwalk output to %s failed: %v\n", copyPath, err))
			return false
		}
	}

	// Progress chatter kept for parity with the Python pipeline stages.
	w.echo("  Filtering pwalk output (removing directories)...")
	w.echo("    ...filtering complete.")
	w.echo("  Converting character encoding...")
	w.echo("    ...conversion complete.")
	w.echo("  Analyzing folder data with DuckDB...")

	if opts.PwalkCopy != "" {
		// Python still runs the whole aggregation in pwalk-copy mode but
		// recomputes the hotspot path; do the same.
		var err error
		hotspotCSV, err = w.HotspotCSVPath(opts.HotspotsDir, folder)
		if err != nil {
			w.echoErr(fmt.Sprintf("Error: %v", err))
			return false
		}
	}

	hsSummary, err := hotspots.AnalyzeFile(tmpPath, hotspotCSV, hotspots.Options{
		Now:  w.now(),
		Logf: func(format string, a ...any) { w.echof(format, a...) },
	})
	w.echo("    ...analysis complete.")
	if err != nil {
		w.echoErr(fmt.Sprintf("\nError: hotspot analysis of %s failed: %v\n", folder, err))
		return false
	}
	w.echof("  Processing and writing hotspots CSV (%s)...", hotspotCSV)
	w.echo("    ...hotspots CSV written.")

	w.echof("\nHotspots file: %s\n"+
		"    with %d hotspots >= %d GiB\n"+
		"    with a total disk use of %s TiB\n",
		hotspotCSV, hsSummary.NumHotspots, hsSummary.ThresholdGiB,
		pyRoundRepr(float64(hsSummary.TotalBytes)/tebi, 3))

	w.echof("Total folders processed: %d", hsSummary.TotalFolders)

	w.echo("\nINDEXING SUCCESSFULLY COMPLETED")

	var lastAged int64
	for i, days := range daysAged {
		aged := hsSummary.AgedBytes[i]
		if aged > 0 && aged != lastAged {
			w.echof("%s TiB have not been accessed for %d days (or %s years)",
				pyRoundRepr(float64(aged)/tebi, 3), days, pyRoundRepr(float64(days)/365, 1))
		}
		lastAged = aged
	}

	w.echo("")

	return !permissionDenied
}

// transcodeLatin1File copies src to dst re-encoding every byte from
// ISO-8859-1 to UTF-8, exactly like `iconv -f ISO-8859-1 -t UTF-8` (every
// byte sequence is valid ISO-8859-1, so this never fails; already-UTF-8
// names get mojibake'd, matching Python).
func transcodeLatin1File(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	bw := bufio.NewWriter(out)
	br := bufio.NewReader(in)
	for {
		b, err := br.ReadByte()
		if err == io.EOF {
			break
		}
		if err != nil {
			out.Close()
			return err
		}
		if _, err := bw.WriteRune(rune(b)); err != nil {
			out.Close()
			return err
		}
	}
	if err := bw.Flush(); err != nil {
		out.Close()
		return err
	}
	return out.Close()
}
