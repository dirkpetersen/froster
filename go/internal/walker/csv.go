package walker

import (
	"strconv"

	"golang.org/x/sys/unix"
)

// rowData carries everything needed to format one CSV row.
type rowData struct {
	ino    uint64
	pino   uint64
	depth  int64
	name   string // full path, unescaped
	ext    string // extension, unescaped
	stat   *unix.Stat_t
	fcount int64 // -1 for non-directories
	dirsum int64 // 0 for non-directories
}

// appendRow appends one pwalk-format CSV row to buf and returns the number
// of name fields from which control bytes were stripped ("bad names").
//
// The format string in C pwalk is:
//
//	%ju,%ju,%ld,"%s","%s",%ld,%ld,%ld,%ld,%ld,%d,"%07o",%ld,%ld,%ld,%ld,%ld\n
//
// covering inode, parent inode, depth, filename, extension, uid, gid,
// st_size, st_dev, st_blocks, st_nlink, st_mode (7-digit octal), atime,
// mtime, ctime, pw_fcount, pw_dirsum.
func appendRow(buf []byte, r rowData) ([]byte, int) {
	bad := 0
	buf = strconv.AppendUint(buf, r.ino, 10)
	buf = append(buf, ',')
	buf = strconv.AppendUint(buf, r.pino, 10)
	buf = append(buf, ',')
	buf = strconv.AppendInt(buf, r.depth, 10)
	buf = append(buf, ',', '"')
	buf, badName := appendEscaped(buf, r.name)
	if badName {
		bad++
	}
	buf = append(buf, '"', ',', '"')
	buf, badExt := appendEscaped(buf, r.ext)
	if badExt {
		bad++
	}
	buf = append(buf, '"', ',')
	buf = strconv.AppendUint(buf, uint64(r.stat.Uid), 10)
	buf = append(buf, ',')
	buf = strconv.AppendUint(buf, uint64(r.stat.Gid), 10)
	buf = append(buf, ',')
	buf = strconv.AppendInt(buf, r.stat.Size, 10)
	buf = append(buf, ',')
	// C prints st_dev cast to (long); reproduce the signed interpretation.
	buf = strconv.AppendInt(buf, int64(r.stat.Dev), 10)
	buf = append(buf, ',')
	buf = strconv.AppendInt(buf, r.stat.Blocks, 10)
	buf = append(buf, ',')
	buf = strconv.AppendUint(buf, r.stat.Nlink, 10)
	buf = append(buf, ',', '"')
	buf = appendOctal7(buf, r.stat.Mode)
	buf = append(buf, '"', ',')
	buf = strconv.AppendInt(buf, r.stat.Atim.Sec, 10)
	buf = append(buf, ',')
	buf = strconv.AppendInt(buf, r.stat.Mtim.Sec, 10)
	buf = append(buf, ',')
	buf = strconv.AppendInt(buf, r.stat.Ctim.Sec, 10)
	buf = append(buf, ',')
	buf = strconv.AppendInt(buf, r.fcount, 10)
	buf = append(buf, ',')
	buf = strconv.AppendInt(buf, r.dirsum, 10)
	buf = append(buf, '\n')
	return buf, bad
}

// appendEscaped appends s using C pwalk's csv_escape rules: double quotes
// are doubled, bytes < 32 are dropped, everything else (including
// non-UTF-8 bytes) passes through raw. It reports whether any control
// bytes were stripped.
func appendEscaped(buf []byte, s string) ([]byte, bool) {
	bad := false
	for i := 0; i < len(s); i++ {
		c := s[i]
		switch {
		case c == '"':
			buf = append(buf, '"', '"')
		case c < 32:
			bad = true
		default:
			buf = append(buf, c)
		}
	}
	return buf, bad
}

// appendOctal7 appends mode as a zero-padded 7-digit octal number,
// matching C pwalk's "%07o" (e.g. 0100644, 0040755, 0120777).
func appendOctal7(buf []byte, mode uint32) []byte {
	var tmp [12]byte
	oct := strconv.AppendUint(tmp[:0], uint64(mode), 8)
	for pad := 7 - len(oct); pad > 0; pad-- {
		buf = append(buf, '0')
	}
	return append(buf, oct...)
}
