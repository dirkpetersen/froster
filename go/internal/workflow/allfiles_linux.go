//go:build linux

package workflow

import (
	"syscall"
	"time"
)

func sysAtime(st *syscall.Stat_t) time.Time { return time.Unix(st.Atim.Sec, st.Atim.Nsec) }
func sysMtime(st *syscall.Stat_t) time.Time { return time.Unix(st.Mtim.Sec, st.Mtim.Nsec) }
func sysMode(st *syscall.Stat_t) uint32     { return st.Mode }
