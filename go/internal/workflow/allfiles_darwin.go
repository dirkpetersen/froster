//go:build darwin

package workflow

import (
	"syscall"
	"time"
)

func sysAtime(st *syscall.Stat_t) time.Time {
	return time.Unix(st.Atimespec.Sec, st.Atimespec.Nsec)
}
func sysMtime(st *syscall.Stat_t) time.Time {
	return time.Unix(st.Mtimespec.Sec, st.Mtimespec.Nsec)
}
func sysMode(st *syscall.Stat_t) uint32 { return uint32(st.Mode) }
