//go:build !linux && !darwin

package hotspots

import "os"

// atimeOf falls back to the modification time on platforms where the raw
// stat access time is not portably available. froster targets Linux HPC
// systems (and macOS for development); on other platforms the newest-file
// atime scan degrades to mtime.
func atimeOf(fi os.FileInfo) float64 {
	return mtimeOf(fi)
}
