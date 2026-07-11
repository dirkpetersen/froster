//go:build linux

package hotspots

import (
	"os"
	"syscall"
)

// atimeOf extracts the access time from a stat result as float epoch
// seconds, matching CPython's st_atime (sec + 1e-9*nsec as a C double).
func atimeOf(fi os.FileInfo) float64 {
	st := fi.Sys().(*syscall.Stat_t)
	return float64(st.Atim.Sec) + 1e-9*float64(st.Atim.Nsec)
}
