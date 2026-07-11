package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	ini "gopkg.in/ini.v1"
)

// Section and key names froster reads and writes in config.ini. Keys are
// lowercase because configparser lowercases option names.
const (
	sectionUser           = "USER"
	sectionShared         = "SHARED"
	sectionNIH            = "NIH"
	sectionDefaultProfile = "DEFAULT_PROFILE"
	sectionUpdate         = "UPDATE"
	sectionSlurm          = "SLURM"

	// sectionCloud is spelled "CLOULD" in the Python source (a typo in
	// ConfigManager.set_ec2_last_instance / ses_verify_requests_sent).
	// We reproduce it for file-level compatibility.
	sectionCloud = "CLOULD"

	keyName       = "name"
	keyEmail      = "email"
	keyIsShared   = "is_shared"
	keySharedDir  = "shared_dir"
	keyIsNIH      = "is_nih"
	keyProfile    = "profile"
	keyTimestamp  = "timestamp"
	keyEC2Last    = "ec2_last_instance"
	keySESVerify  = "ses_verify_requests_sent"
	profilePrefix = "profile "
)

// SLURM section keys.
const (
	keySlurmWalltimeDays  = "slurm_walltime_days"
	keySlurmWalltimeHours = "slurm_walltime_hours"
	keySlurmPartition     = "slurm_partition"
	keySlurmQOS           = "slurm_qos"
	keySlurmLscratch      = "slurm_lscratch"
	keyLscratchMkdir      = "lscratch_mkdir"
	keyLscratchRmdir      = "lscratch_rmdir"
	keyLscratchRoot       = "lscratch_root"
)

// UpdateCheckInterval is how often froster checks for a new release
// (Python: check_update's 86400*7 seconds).
const UpdateCheckInterval = 7 * 24 * time.Hour

// Config is froster's parsed config.ini plus the resolved filesystem paths.
// It preserves the order of sections and keys and any keys or sections it
// does not know about, so a Python froster can keep reading a file written
// by this package (important in shared-config mode during the transition).
//
// Setters only mutate the in-memory document; call Save to persist.
type Config struct {
	// Paths holds the resolved froster directories used to locate this
	// config file and its companions.
	Paths Paths

	file *ini.File
}

// Load reads config.ini from p.ConfigFile().
//
//   - If the file does not exist, an empty Config is returned (fresh
//     install; Python's configparser.read silently ignores missing files).
//   - If the file exists but is smaller than CorruptSizeThreshold bytes it
//     is considered corrupted (install.sh commit 6e3f4a9) and a
//     *CorruptedConfigError is returned.
func Load(p Paths) (*Config, error) {
	path := p.ConfigFile()

	st, err := os.Stat(path)
	switch {
	case os.IsNotExist(err):
		return New(p), nil
	case err != nil:
		return nil, fmt.Errorf("reading config file %s: %w", path, err)
	case st.Size() < CorruptSizeThreshold:
		return nil, &CorruptedConfigError{Path: path, Size: st.Size()}
	}

	f, err := ini.LoadSources(loadOptions(), path)
	if err != nil {
		return nil, fmt.Errorf("parsing config file %s: %w", path, err)
	}
	normalizeMultilineValues(f)

	return &Config{Paths: p, file: f}, nil
}

// New returns an empty Config bound to p, as after a fresh install.
func New(p Paths) *Config {
	return &Config{Paths: p, file: ini.Empty(loadOptions())}
}

// Exists reports whether the config file is present on disk.
func (c *Config) Exists() bool {
	_, err := os.Stat(c.Paths.ConfigFile())
	return err == nil
}

// Save writes the config file in configparser-compatible format. The config
// directory is created with mode 0775 if needed (as Python's
// __set_configuration_entry does). The write is atomic (temp file + rename),
// which is an invisible improvement over Python's in-place rewrite.
func (c *Config) Save() error {
	dir := c.Paths.ConfigDir
	if err := os.MkdirAll(dir, 0o775); err != nil {
		return fmt.Errorf("creating config directory %s: %w", dir, err)
	}

	data := marshalINI(c.file)

	tmp, err := os.CreateTemp(dir, ConfigFileName+".tmp*")
	if err != nil {
		return fmt.Errorf("writing config file: %w", err)
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName) // no-op after successful rename

	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return fmt.Errorf("writing config file: %w", err)
	}
	if err := tmp.Chmod(0o644); err != nil {
		tmp.Close()
		return fmt.Errorf("writing config file: %w", err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("writing config file: %w", err)
	}

	if err := os.Rename(tmpName, c.Paths.ConfigFile()); err != nil {
		return fmt.Errorf("writing config file: %w", err)
	}
	return nil
}

// Marshal returns the serialized config file contents without writing them.
func (c *Config) Marshal() []byte {
	return marshalINI(c.file)
}

// ---------------------------------------------------------------------------
// Generic accessors (Python: __get_configuration_entry /
// __set_configuration_entry / __remove_config_option). Kept exported so the
// wizard and future packages can reach keys this package has no typed
// accessor for.
// ---------------------------------------------------------------------------

// Get returns the value of key in section. Missing sections/keys and empty
// values return fallback (Python's helper coerces "" to the fallback too).
func (c *Config) Get(section, key, fallback string) string {
	sec, err := c.file.GetSection(section)
	if err != nil {
		return fallback
	}
	k, err := sec.GetKey(strings.ToLower(key))
	if err != nil || k.Value() == "" {
		return fallback
	}
	return k.Value()
}

// GetBool returns the boolean value of key in section, accepting the same
// spellings as configparser.getboolean (1/yes/true/on, 0/no/false/off,
// case-insensitive). Missing, empty, or unparseable values return fallback.
func (c *Config) GetBool(section, key string, fallback bool) bool {
	v := c.Get(section, key, "")
	if v == "" {
		return fallback
	}
	if b, ok := parseConfigparserBool(v); ok {
		return b
	}
	return fallback
}

// GetInt returns the integer value of key in section; missing, empty or
// unparseable values return fallback.
func (c *Config) GetInt(section, key string, fallback int64) int64 {
	v := c.Get(section, key, "")
	if v == "" {
		return fallback
	}
	n, err := strconv.ParseInt(strings.TrimSpace(v), 10, 64)
	if err != nil {
		return fallback
	}
	return n
}

// Set stores value under section/key, creating the section as needed. The
// key is lowercased like configparser's optionxform does.
func (c *Config) Set(section, key, value string) {
	sec := c.file.Section(section)
	sec.Key(strings.ToLower(key)).SetValue(value)
}

// Delete removes key from section if present (Python: __remove_config_option).
func (c *Config) Delete(section, key string) {
	sec, err := c.file.GetSection(section)
	if err != nil {
		return
	}
	sec.DeleteKey(strings.ToLower(key))
}

// DeleteSection removes an entire section if present.
func (c *Config) DeleteSection(section string) {
	c.file.DeleteSection(section)
}

// Sections returns all section names in file order (excluding go-ini's
// implicit default section).
func (c *Config) Sections() []string {
	var out []string
	for _, sec := range c.file.Sections() {
		if sec.Name() == ini.DefaultSection {
			continue
		}
		out = append(out, sec.Name())
	}
	return out
}

// ---------------------------------------------------------------------------
// [USER]
// ---------------------------------------------------------------------------

// Name returns [USER] name (the user's full name), or "".
func (c *Config) Name() string { return c.Get(sectionUser, keyName, "") }

// SetName sets [USER] name.
func (c *Config) SetName(name string) { c.Set(sectionUser, keyName, name) }

// Email returns [USER] email, or "".
func (c *Config) Email() string { return c.Get(sectionUser, keyEmail, "") }

// SetEmail sets [USER] email.
func (c *Config) SetEmail(email string) { c.Set(sectionUser, keyEmail, email) }

// ---------------------------------------------------------------------------
// [SHARED] — shared-config redirection
// ---------------------------------------------------------------------------

// IsShared reports whether shared-config mode is enabled
// ([SHARED] is_shared, default false).
func (c *Config) IsShared() bool { return c.GetBool(sectionShared, keyIsShared, false) }

// SharedDir returns [SHARED] shared_dir when shared-config mode is enabled,
// otherwise "" (mirroring Python, which only reads shared_dir when
// is_shared is true).
func (c *Config) SharedDir() string {
	if !c.IsShared() {
		return ""
	}
	return c.Get(sectionShared, keySharedDir, "")
}

// SetShared enables shared-config mode with the given shared directory
// (Python: set_shared answering yes). It does not copy any files; moving
// the archive database and hotspots into the shared directory is the
// wizard's job.
func (c *Config) SetShared(sharedDir string) {
	c.Set(sectionShared, keyIsShared, pythonBool(true))
	c.Set(sectionShared, keySharedDir, sharedDir)
}

// SetNotShared disables shared-config mode and removes shared_dir
// (Python: set_shared answering no).
func (c *Config) SetNotShared() {
	c.Set(sectionShared, keyIsShared, pythonBool(false))
	c.Delete(sectionShared, keySharedDir)
}

// ArchiveJSON returns the path of the archive database
// (froster-archives.json): inside shared_dir in shared mode, otherwise in
// the local data directory.
func (c *Config) ArchiveJSON() string {
	if dir := c.SharedDir(); dir != "" {
		return filepath.Join(dir, ArchiveJSONFileName)
	}
	return c.Paths.LocalArchiveJSON()
}

// HotspotsDir returns the hotspots directory: <shared_dir>/hotspots in
// shared mode, otherwise <data_dir>/hotspots.
func (c *Config) HotspotsDir() string {
	if dir := c.SharedDir(); dir != "" {
		return filepath.Join(dir, hotspotsDirName)
	}
	return c.Paths.LocalHotspotsDir()
}

// ---------------------------------------------------------------------------
// [NIH]
// ---------------------------------------------------------------------------

// IsNIH reports whether NIH grant linking is enabled ([NIH] is_nih,
// default false).
func (c *Config) IsNIH() bool { return c.GetBool(sectionNIH, keyIsNIH, false) }

// SetIsNIH sets [NIH] is_nih.
func (c *Config) SetIsNIH(v bool) { c.Set(sectionNIH, keyIsNIH, pythonBool(v)) }

// ---------------------------------------------------------------------------
// [UPDATE]
// ---------------------------------------------------------------------------

// UpdateTimestamp returns the unix time of the last release check
// ([UPDATE] timestamp, default 0).
func (c *Config) UpdateTimestamp() int64 { return c.GetInt(sectionUpdate, keyTimestamp, 0) }

// SetUpdateTimestamp sets [UPDATE] timestamp.
func (c *Config) SetUpdateTimestamp(ts int64) {
	c.Set(sectionUpdate, keyTimestamp, strconv.FormatInt(ts, 10))
}

// CheckUpdateDue mirrors Python's ConfigManager.check_update: it returns
// false when the last check happened less than UpdateCheckInterval ago;
// otherwise it records now as the last check time, saves the config file
// (Python's setter writes immediately), and returns true.
func (c *Config) CheckUpdateDue(now time.Time) (bool, error) {
	if now.Unix()-c.UpdateTimestamp() < int64(UpdateCheckInterval/time.Second) {
		return false, nil
	}
	c.SetUpdateTimestamp(now.Unix())
	if err := c.Save(); err != nil {
		return false, err
	}
	return true, nil
}

// ---------------------------------------------------------------------------
// [SLURM]
// ---------------------------------------------------------------------------

// SlurmWalltimeDays returns [SLURM] slurm_walltime_days (default 7).
func (c *Config) SlurmWalltimeDays() int64 { return c.GetInt(sectionSlurm, keySlurmWalltimeDays, 7) }

// SlurmWalltimeHours returns [SLURM] slurm_walltime_hours (default 0).
func (c *Config) SlurmWalltimeHours() int64 { return c.GetInt(sectionSlurm, keySlurmWalltimeHours, 0) }

// SlurmPartition returns [SLURM] slurm_partition, or "".
func (c *Config) SlurmPartition() string { return c.Get(sectionSlurm, keySlurmPartition, "") }

// SlurmQOS returns [SLURM] slurm_qos, or "".
func (c *Config) SlurmQOS() string { return c.Get(sectionSlurm, keySlurmQOS, "") }

// SlurmLscratch returns [SLURM] slurm_lscratch (how to request local
// scratch, e.g. "--gres lscratch:%d"), or "".
func (c *Config) SlurmLscratch() string { return c.Get(sectionSlurm, keySlurmLscratch, "") }

// LscratchMkdir returns [SLURM] lscratch_mkdir, or "".
func (c *Config) LscratchMkdir() string { return c.Get(sectionSlurm, keyLscratchMkdir, "") }

// LscratchRmdir returns [SLURM] lscratch_rmdir, or "".
func (c *Config) LscratchRmdir() string { return c.Get(sectionSlurm, keyLscratchRmdir, "") }

// LscratchRoot returns [SLURM] lscratch_root, or "".
func (c *Config) LscratchRoot() string { return c.Get(sectionSlurm, keyLscratchRoot, "") }

// SlurmSettings bundles every [SLURM] key for SetSlurm.
type SlurmSettings struct {
	WalltimeDays  int64
	WalltimeHours int64
	Partition     string
	QOS           string
	Lscratch      string
	LscratchMkdir string
	LscratchRmdir string
	LscratchRoot  string
}

// SetSlurm writes the [SLURM] section in the order Python's set_slurm does.
// Empty string values are written as empty entries ("key = "), matching the
// Python wizard when a prompt is skipped.
func (c *Config) SetSlurm(s SlurmSettings) {
	c.Set(sectionSlurm, keySlurmWalltimeDays, strconv.FormatInt(s.WalltimeDays, 10))
	c.Set(sectionSlurm, keySlurmWalltimeHours, strconv.FormatInt(s.WalltimeHours, 10))
	c.Set(sectionSlurm, keySlurmPartition, s.Partition)
	c.Set(sectionSlurm, keySlurmQOS, s.QOS)
	c.Set(sectionSlurm, keySlurmLscratch, s.Lscratch)
	c.Set(sectionSlurm, keyLscratchMkdir, s.LscratchMkdir)
	c.Set(sectionSlurm, keyLscratchRmdir, s.LscratchRmdir)
	c.Set(sectionSlurm, keyLscratchRoot, s.LscratchRoot)
}

// ---------------------------------------------------------------------------
// [CLOULD] (sic) — stubbed cloud-restore features
// ---------------------------------------------------------------------------

// EC2LastInstance returns [CLOULD] ec2_last_instance, or "". The section
// name reproduces a typo in the Python source; files written by Python
// froster use "CLOULD".
func (c *Config) EC2LastInstance() string { return c.Get(sectionCloud, keyEC2Last, "") }

// SetEC2LastInstance sets [CLOULD] ec2_last_instance
// (Python: set_ec2_last_instance).
func (c *Config) SetEC2LastInstance(instance string) { c.Set(sectionCloud, keyEC2Last, instance) }

// SetSESVerifyRequestsSent stores the list of emails that received an SES
// verification request, rendered as a Python list literal (str(list)) for
// byte compatibility with what Python froster writes.
func (c *Config) SetSESVerifyRequestsSent(emails []string) {
	quoted := make([]string, len(emails))
	for i, e := range emails {
		quoted[i] = "'" + e + "'"
	}
	c.Set(sectionCloud, keySESVerify, "["+strings.Join(quoted, ", ")+"]")
}

// SESVerifyRequestsSent returns the raw stored value of
// [CLOULD] ses_verify_requests_sent (a Python list literal), or "".
func (c *Config) SESVerifyRequestsSent() string { return c.Get(sectionCloud, keySESVerify, "") }
