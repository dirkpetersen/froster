package workflow

import (
	"archive/tar"
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"os/user"
	"path/filepath"
	"strconv"
	"syscall"
	"time"
)

// genAllfilesAndTar reproduces Archiver._gen_allfiles_and_tar (spec §1.5):
// it creates Froster.allfiles.csv describing every top-level file and, when
// isTar is set, moves files strictly smaller than thresholdKiB KiB into
// Froster.smallfiles.tar (deleting the originals as they are tarred). If no
// file was tarred the empty tar is removed. If the tar already exists the
// function returns immediately (idempotent resume; note that Python does
// not regenerate a stale allfiles.csv in that case either).
func (w *Workflow) genAllfilesAndTar(dir string, thresholdKiB int, isTar bool) error {
	tarPath := filepath.Join(dir, SmallfilesTarFileName)
	csvPath := filepath.Join(dir, AllfilesCSVFileName)

	if _, err := os.Lstat(tarPath); err == nil {
		return nil
	}

	// Snapshot the top-level file list before creating the outputs, like
	// Python's os.walk which lists the directory before the tar exists.
	files, err := topFiles(dir)
	if err != nil {
		return err
	}

	tarFile, err := os.Create(tarPath)
	if err != nil {
		return err
	}
	csvFile, err := os.Create(csvPath)
	if err != nil {
		tarFile.Close()
		return err
	}

	tw := tar.NewWriter(tarFile)
	cw := csv.NewWriter(csvFile)
	cw.UseCRLF = true // Python csv 'excel' dialect writes \r\n

	closeAll := func() error {
		cw.Flush()
		err := cw.Error()
		if cerr := csvFile.Close(); err == nil {
			err = cerr
		}
		if terr := tw.Close(); err == nil {
			err = terr
		}
		if terr := tarFile.Close(); err == nil {
			err = terr
		}
		return err
	}

	if err := cw.Write([]string{"File", "Size(bytes)", "Date-Modified",
		"Date-Accessed", "Owner", "Group", "Permissions", "Tarred"}); err != nil {
		closeAll()
		return err
	}

	didTar := false
	for _, name := range files {
		// Skip the csv file itself (created after the snapshot, but kept
		// for defense, like Python's `if file_path == csv_path: continue`).
		if name == AllfilesCSVFileName || name == SmallfilesTarFileName {
			continue
		}
		filePath := filepath.Join(dir, name)

		info, err := os.Lstat(filePath)
		if err != nil {
			// Python's _get_file_stats logs "<path> not found." and the
			// subsequent code would fail; treat as disappeared.
			w.echof("Warning: File %s disappeared before tarring/removal.", filePath)
			continue
		}
		// Python: os.path.isfile (follows symlinks) or os.path.islink.
		// Special files (fifo, socket, device) are neither and get no row.
		isLink := info.Mode()&os.ModeSymlink != 0
		isRegular := info.Mode().IsRegular()
		if isLink {
			if target, err := os.Stat(filePath); err == nil {
				isRegular = target.Mode().IsRegular()
			}
		}
		if !isRegular && !isLink {
			continue
		}

		st, _ := info.Sys().(*syscall.Stat_t)
		size := info.Size()
		mdate := formatStatTime(statMtime(info, st))
		adate := formatStatTime(statAtime(info, st))
		owner, group := ownerGroup(st)
		permissions := fmt.Sprintf("0o%o", statRawMode(info, st))
		tarred := "No"

		if isTar && size < int64(thresholdKiB)*1024 {
			if err := addToTar(tw, filePath, name, info); err != nil {
				w.echof("Warning: Failed to tar or remove %s: %v", filePath, err)
				continue // skip the CSV row, like Python
			}
			didTar = true
			if err := os.Remove(filePath); err != nil {
				w.echof("Warning: Failed to tar or remove %s: %v", filePath, err)
				continue
			}
			tarred = "Yes"
		}

		if err := cw.Write([]string{name, strconv.FormatInt(size, 10),
			mdate, adate, owner, group, permissions, tarred}); err != nil {
			closeAll()
			return err
		}
	}

	if err := closeAll(); err != nil {
		return err
	}

	if !didTar {
		// Remove the empty tar (spec §1.5).
		if err := os.Remove(tarPath); err != nil {
			return err
		}
	}
	return nil
}

// addToTar appends one file or symlink to the tar with a flat member name
// (arcname = basename), mirroring tarfile.add(file_path, arcname=file) with
// the default PAX (POSIX.1-2001) format Python 3.8+ uses. hdrcharset
// handling for raw-byte names differs slightly (Go emits a UTF-8-tagged PAX
// path record where CPython tags hdrcharset=BINARY); member names,
// contents, and metadata are equivalent.
func addToTar(tw *tar.Writer, filePath, name string, info os.FileInfo) error {
	link := ""
	if info.Mode()&os.ModeSymlink != 0 {
		var err error
		link, err = os.Readlink(filePath)
		if err != nil {
			return err
		}
	}
	hdr, err := tar.FileInfoHeader(info, link)
	if err != nil {
		return err
	}
	hdr.Name = name
	hdr.Format = tar.FormatPAX
	// Python tarfile stores second-precision mtime in the ustar field and
	// no atime/ctime PAX records; drop sub-second precision to match.
	hdr.ModTime = hdr.ModTime.Truncate(time.Second)
	hdr.AccessTime = time.Time{}
	hdr.ChangeTime = time.Time{}
	if st, ok := info.Sys().(*syscall.Stat_t); ok {
		hdr.Uname = lookupUID(int64(st.Uid))
		hdr.Gname = lookupGID(int64(st.Gid))
	}

	if err := tw.WriteHeader(hdr); err != nil {
		return err
	}
	if hdr.Typeflag == tar.TypeReg {
		f, err := os.Open(filePath)
		if err != nil {
			return err
		}
		defer f.Close()
		if _, err := io.Copy(tw, f); err != nil {
			return err
		}
	}
	return tw.Flush()
}

// untar extracts every member of tarPath into dir, the equivalent of
// Python's tarfile.extractall(path=dir) as used by reset and restore.
// Existing files are overwritten.
func untar(tarPath, dir string) error {
	f, err := os.Open(tarPath)
	if err != nil {
		return err
	}
	defer f.Close()

	tr := tar.NewReader(f)
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return err
		}
		target := filepath.Join(dir, hdr.Name) //nolint:gosec // flat froster tars; matches Python extractall
		switch hdr.Typeflag {
		case tar.TypeDir:
			if err := os.MkdirAll(target, os.FileMode(hdr.Mode)&os.ModePerm); err != nil {
				return err
			}
		case tar.TypeSymlink:
			os.Remove(target)
			if err := os.Symlink(hdr.Linkname, target); err != nil {
				return err
			}
		case tar.TypeReg:
			if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
				return err
			}
			out, err := os.OpenFile(target, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, os.FileMode(hdr.Mode)&os.ModePerm)
			if err != nil {
				return err
			}
			if _, err := io.Copy(out, tr); err != nil { //nolint:gosec // trusted self-produced tar
				out.Close()
				return err
			}
			if err := out.Close(); err != nil {
				return err
			}
			// OpenFile's mode is masked by the umask and strips
			// setuid/setgid/sticky; Python's tarfile.extractall chmods
			// each member to the stored mode. Restore it exactly.
			mode := hdr.FileInfo().Mode() & (os.ModePerm | os.ModeSetuid | os.ModeSetgid | os.ModeSticky)
			if err := os.Chmod(target, mode); err != nil {
				return err
			}
			_ = os.Chtimes(target, time.Time{}, hdr.ModTime)
		default:
			// FIFOs etc.: skip silently (Python extractall would recreate
			// them; froster never tars them — see genAllfilesAndTar).
		}
	}
}

// formatStatTime renders a timestamp like Python's
// datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M:%S') (local time).
func formatStatTime(t time.Time) string {
	return t.Local().Format("2006-01-02 15:04:05")
}

func statAtime(info os.FileInfo, st *syscall.Stat_t) time.Time {
	if st != nil {
		return time.Unix(st.Atim.Sec, st.Atim.Nsec)
	}
	return info.ModTime()
}

func statMtime(info os.FileInfo, st *syscall.Stat_t) time.Time {
	if st != nil {
		return time.Unix(st.Mtim.Sec, st.Mtim.Nsec)
	}
	return info.ModTime()
}

// statRawMode returns the full st_mode (file type | permission bits) as the
// kernel reports it, which Python renders with oct() (e.g. 0o100644).
func statRawMode(info os.FileInfo, st *syscall.Stat_t) uint32 {
	if st != nil {
		return st.Mode
	}
	return uint32(info.Mode().Perm())
}

func ownerGroup(st *syscall.Stat_t) (string, string) {
	if st == nil {
		return "", ""
	}
	return lookupUID(int64(st.Uid)), lookupGID(int64(st.Gid))
}

// lookupUID resolves a uid to a username, falling back to the decimal uid
// (Python pwd.getpwuid with numeric fallback).
func lookupUID(uid int64) string {
	if u, err := user.LookupId(strconv.FormatInt(uid, 10)); err == nil {
		return u.Username
	}
	return strconv.FormatInt(uid, 10)
}

// lookupGID resolves a gid to a group name, falling back to the decimal gid.
func lookupGID(gid int64) string {
	if g, err := user.LookupGroupId(strconv.FormatInt(gid, 10)); err == nil {
		return g.Name
	}
	return strconv.FormatInt(gid, 10)
}
