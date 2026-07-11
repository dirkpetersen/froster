package config

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// CorruptSizeThreshold is the minimum plausible size of a valid config.ini.
// A config file smaller than this is considered corrupted (empty or
// truncated by a previously buggy installer). This mirrors install.sh's
// check_and_restore_from_backup after commit 6e3f4a9 ("detect and restore
// corrupted config.ini files").
const CorruptSizeThreshold = 40

// CorruptedConfigError is returned by Load when config.ini exists but is
// too small to be valid. Callers should offer to restore from a backup
// (FindLatestBackup / RestoreBackup) or re-run the configuration wizard.
type CorruptedConfigError struct {
	// Path of the corrupted config file.
	Path string
	// Size of the file in bytes.
	Size int64
}

func (e *CorruptedConfigError) Error() string {
	return fmt.Sprintf(
		"config file %s is corrupted (%d bytes, less than %d): restore it from a backup or re-run 'froster config'",
		e.Path, e.Size, CorruptSizeThreshold)
}

// IsConfigCorrupted reports whether the config file at path exists but is
// smaller than CorruptSizeThreshold bytes. A missing file is not corrupted
// (it is a fresh install).
func IsConfigCorrupted(path string) bool {
	st, err := os.Stat(path)
	return err == nil && st.Size() < CorruptSizeThreshold
}

// Backup is a matched pair of config and archive-database backup files
// created by install.sh under $XDG_CONFIG_HOME/froster_backups and
// $XDG_DATA_HOME/froster_backups (directories named
// froster_<YYYYMMDDHHMMSS>.bak).
type Backup struct {
	// Timestamp is the raw YYYYMMDDHHMMSS suffix of the backup directories.
	Timestamp string
	// ConfigFile is the backed-up config.ini.
	ConfigFile string
	// DataFile is the backed-up froster-archives.json.
	DataFile string
}

// Date parses the backup's timestamp in local time. It returns the zero
// time if the timestamp is malformed.
func (b Backup) Date() time.Time {
	t, err := time.ParseInLocation("20060102150405", b.Timestamp, time.Local)
	if err != nil {
		return time.Time{}
	}
	return t
}

// ShouldOfferRestore mirrors install.sh's trigger condition: a restore is
// offered only when the config file is missing or corrupted AND the local
// archive database is missing. If either file is present and valid, the
// user's data is intact and no restore is needed.
func ShouldOfferRestore(p Paths) bool {
	configPath := p.ConfigFile()
	if _, err := os.Stat(configPath); err == nil && !IsConfigCorrupted(configPath) {
		return false
	} else if err != nil && !os.IsNotExist(err) {
		return false
	}
	if _, err := os.Stat(p.LocalArchiveJSON()); err == nil {
		return false
	}
	return true
}

// FindLatestBackup scans the backup roots for the newest backup that
// contains BOTH a config.ini and a froster-archives.json with matching
// timestamps (install.sh requires the complete pair). It returns nil when
// no complete backup exists.
func FindLatestBackup(p Paths) (*Backup, error) {
	entries, err := os.ReadDir(p.ConfigBackupsRoot())
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("scanning backups in %s: %w", p.ConfigBackupsRoot(), err)
	}

	var timestamps []string
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		name := e.Name()
		if strings.HasPrefix(name, "froster_") && strings.HasSuffix(name, ".bak") {
			timestamps = append(timestamps, strings.TrimSuffix(strings.TrimPrefix(name, "froster_"), ".bak"))
		}
	}

	// Newest first (names embed YYYYMMDDHHMMSS, so lexical order is
	// chronological — same trick as install.sh's "sort -r").
	sort.Sort(sort.Reverse(sort.StringSlice(timestamps)))

	for _, ts := range timestamps {
		b := Backup{
			Timestamp:  ts,
			ConfigFile: filepath.Join(p.ConfigBackupsRoot(), "froster_"+ts+".bak", ConfigFileName),
			DataFile:   filepath.Join(p.DataBackupsRoot(), "froster_"+ts+".bak", ArchiveJSONFileName),
		}
		if fileExists(b.ConfigFile) && fileExists(b.DataFile) {
			return &b, nil
		}
	}
	return nil, nil
}

// RestoreBackup copies the backup's config.ini and froster-archives.json
// back into place (config dir and local data dir), creating the target
// directories as needed. A corrupted config file in place is overwritten,
// exactly like install.sh's restore.
func RestoreBackup(p Paths, b Backup) error {
	if err := os.MkdirAll(p.ConfigDir, 0o775); err != nil {
		return fmt.Errorf("restoring backup: %w", err)
	}
	if err := os.MkdirAll(p.DataDir, 0o775); err != nil {
		return fmt.Errorf("restoring backup: %w", err)
	}
	if err := copyFile(b.ConfigFile, p.ConfigFile()); err != nil {
		return fmt.Errorf("restoring config from backup: %w", err)
	}
	if err := copyFile(b.DataFile, p.LocalArchiveJSON()); err != nil {
		return fmt.Errorf("restoring archive database from backup: %w", err)
	}
	return nil
}

func fileExists(path string) bool {
	st, err := os.Stat(path)
	return err == nil && st.Mode().IsRegular()
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o644)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	return out.Close()
}
