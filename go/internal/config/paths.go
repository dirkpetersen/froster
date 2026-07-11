// Package config manages froster's configuration with full drop-in
// compatibility with the Python implementation (froster/froster.py, class
// ConfigManager).
//
// It covers:
//
//   - XDG Base Directory path resolution (~/.config/froster/config.ini,
//     ~/.local/share/froster/), honoring XDG_CONFIG_HOME / XDG_DATA_HOME.
//   - Reading and writing config.ini in the exact format Python's
//     configparser produces (lowercase keys, "key = value", one blank line
//     after every section) while preserving key order and unknown
//     keys/sections, so Python and Go clients can share the same file.
//   - The [SHARED] shared-config redirection: when is_shared is true, the
//     archive database (froster-archives.json) and the hotspots directory
//     live under shared_dir instead of the local data directory. The Slurm
//     output directory and the log file are NOT redirected.
//   - Profile sections ([profile <name>]) and default-profile selection
//     ([DEFAULT_PROFILE]).
//   - AWS credentials files (~/.aws/credentials, ~/.aws/config) as managed
//     by Python froster, including the configparser-style nested
//     "s3 = \n endpoint_url = ..." value.
//   - Corrupted-config detection matching install.sh commit 6e3f4a9: a
//     config.ini smaller than 40 bytes is considered corrupted, and a
//     restore can be attempted from the newest complete backup pair under
//     $XDG_CONFIG_HOME/froster_backups and $XDG_DATA_HOME/froster_backups.
package config

import (
	"fmt"
	"os"
	"os/user"
	"path/filepath"
)

// File and directory names shared with the Python implementation.
const (
	// ArchiveJSONFileName is the name of the archive database file
	// (Python: ConfigManager.archive_json_file_name).
	ArchiveJSONFileName = "froster-archives.json"

	// ConfigFileName is the name of froster's ini configuration file.
	ConfigFileName = "config.ini"

	// hotspotsDirName is the directory (under the data dir or the shared
	// dir) that holds hotspot CSV files.
	hotspotsDirName = "hotspots"

	// slurmDirName is the directory under the data dir for Slurm job output.
	slurmDirName = "slurm"

	// logFileName is froster's log file under the data dir.
	logFileName = "froster.log"

	// backupsDirName is the sibling directory of the config/data dirs where
	// install.sh keeps timestamped backups (froster_<YYYYMMDDHHMMSS>.bak).
	backupsDirName = "froster_backups"
)

// Defaults hardcoded in Python's ConfigManager.__init__ (they are attributes,
// not config.ini entries, in froster v0.22.x).
const (
	// MaxSmallFileSizeKiB: files smaller than this are tarred into
	// Froster.smallfiles.tar before upload.
	MaxSmallFileSizeKiB = 1024

	// MinIndexFolderSizeGiB: minimum folder size for hotspot candidates.
	MinIndexFolderSizeGiB = 1

	// MinIndexFolderSizeAvgMiB: minimum average file size for hotspot
	// candidates.
	MinIndexFolderSizeAvgMiB = 10

	// MaxHotspotsDisplayEntries: maximum number of rows shown in the
	// hotspots TUI.
	MaxHotspotsDisplayEntries = 5000

	// SSHKeyName is froster's default EC2 ssh key name.
	SSHKeyName = "froster-ec2"
)

// Paths resolves froster's on-disk locations following the XDG Base
// Directory specification, exactly as Python's ConfigManager.__init__ does:
//
//	config dir: $XDG_CONFIG_HOME/froster  or ~/.config/froster
//	data dir:   $XDG_DATA_HOME/froster    or ~/.local/share/froster
//	AWS dir:    ~/.aws                    (not XDG-relocatable)
//
// All fields are absolute paths. Construct with DefaultPaths (which honors
// the environment) or fill the struct directly in tests.
type Paths struct {
	// Home is the user's home directory.
	Home string
	// ConfigDir is froster's configuration directory.
	ConfigDir string
	// DataDir is froster's local data directory.
	DataDir string
	// AWSDir is the AWS configuration directory (~/.aws).
	AWSDir string
}

// DefaultPaths resolves Paths from the environment, mirroring Python's
// ConfigManager.__init__. XDG_CONFIG_HOME and XDG_DATA_HOME override the
// defaults, which makes test isolation possible without touching the real
// user configuration.
func DefaultPaths() (Paths, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return Paths{}, fmt.Errorf("resolving home directory: %w", err)
	}

	var p Paths
	p.Home = home

	if xdg := os.Getenv("XDG_CONFIG_HOME"); xdg != "" {
		p.ConfigDir = filepath.Join(xdg, "froster")
	} else {
		p.ConfigDir = filepath.Join(home, ".config", "froster")
	}

	if xdg := os.Getenv("XDG_DATA_HOME"); xdg != "" {
		p.DataDir = filepath.Join(xdg, "froster")
	} else {
		p.DataDir = filepath.Join(home, ".local", "share", "froster")
	}

	p.AWSDir = filepath.Join(home, ".aws")

	return p, nil
}

// ConfigFile returns the path of froster's config.ini.
func (p Paths) ConfigFile() string {
	return filepath.Join(p.ConfigDir, ConfigFileName)
}

// LocalArchiveJSON returns the archive database path in the local data
// directory, ignoring any shared-config redirection. Use
// Config.ArchiveJSON for the shared-aware path.
func (p Paths) LocalArchiveJSON() string {
	return filepath.Join(p.DataDir, ArchiveJSONFileName)
}

// LocalHotspotsDir returns the hotspots directory in the local data
// directory, ignoring any shared-config redirection. Use
// Config.HotspotsDir for the shared-aware path.
func (p Paths) LocalHotspotsDir() string {
	return filepath.Join(p.DataDir, hotspotsDirName)
}

// SlurmDir returns the directory for Slurm job output files. It is always
// local (Python never redirects it in shared mode).
func (p Paths) SlurmDir() string {
	return filepath.Join(p.DataDir, slurmDirName)
}

// LogFile returns froster's log file path. It is always local.
func (p Paths) LogFile() string {
	return filepath.Join(p.DataDir, logFileName)
}

// AWSConfigFile returns the path of ~/.aws/config.
func (p Paths) AWSConfigFile() string {
	return filepath.Join(p.AWSDir, "config")
}

// AWSCredentialsFile returns the path of ~/.aws/credentials.
func (p Paths) AWSCredentialsFile() string {
	return filepath.Join(p.AWSDir, "credentials")
}

// ConfigBackupsRoot returns the directory install.sh uses for config
// backups: a froster_backups directory next to the froster config dir
// (i.e. $XDG_CONFIG_HOME/froster_backups).
func (p Paths) ConfigBackupsRoot() string {
	return filepath.Join(filepath.Dir(p.ConfigDir), backupsDirName)
}

// DataBackupsRoot returns the directory install.sh uses for data backups:
// a froster_backups directory next to the froster data dir
// (i.e. $XDG_DATA_HOME/froster_backups).
func (p Paths) DataBackupsRoot() string {
	return filepath.Join(filepath.Dir(p.DataDir), backupsDirName)
}

// AWS returns an accessor for the AWS credentials and config files under
// this Paths' AWS directory.
func (p Paths) AWS() AWSFiles {
	return AWSFiles{
		ConfigFile:      p.AWSConfigFile(),
		CredentialsFile: p.AWSCredentialsFile(),
	}
}

// Whoami returns the current username (Python: getpass.getuser()).
func Whoami() string {
	if u, err := user.Current(); err == nil && u.Username != "" {
		return u.Username
	}
	return os.Getenv("USER")
}
