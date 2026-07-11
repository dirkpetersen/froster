package config

import (
	"path/filepath"
	"testing"
)

func TestDefaultPathsXDGOverrides(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("XDG_CONFIG_HOME", filepath.Join(home, "xdg-config"))
	t.Setenv("XDG_DATA_HOME", filepath.Join(home, "xdg-data"))

	p, err := DefaultPaths()
	if err != nil {
		t.Fatal(err)
	}
	if want := filepath.Join(home, "xdg-config", "froster"); p.ConfigDir != want {
		t.Errorf("ConfigDir = %q, want %q", p.ConfigDir, want)
	}
	if want := filepath.Join(home, "xdg-data", "froster"); p.DataDir != want {
		t.Errorf("DataDir = %q, want %q", p.DataDir, want)
	}
	if want := filepath.Join(home, ".aws"); p.AWSDir != want {
		t.Errorf("AWSDir = %q, want %q", p.AWSDir, want)
	}
	if want := filepath.Join(home, "xdg-config", "froster", "config.ini"); p.ConfigFile() != want {
		t.Errorf("ConfigFile = %q, want %q", p.ConfigFile(), want)
	}
	// Backup roots are siblings of the froster dirs (install.sh layout).
	if want := filepath.Join(home, "xdg-config", "froster_backups"); p.ConfigBackupsRoot() != want {
		t.Errorf("ConfigBackupsRoot = %q, want %q", p.ConfigBackupsRoot(), want)
	}
	if want := filepath.Join(home, "xdg-data", "froster_backups"); p.DataBackupsRoot() != want {
		t.Errorf("DataBackupsRoot = %q, want %q", p.DataBackupsRoot(), want)
	}
}

func TestDefaultPathsWithoutXDG(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("XDG_CONFIG_HOME", "")
	t.Setenv("XDG_DATA_HOME", "")

	p, err := DefaultPaths()
	if err != nil {
		t.Fatal(err)
	}
	if want := filepath.Join(home, ".config", "froster"); p.ConfigDir != want {
		t.Errorf("ConfigDir = %q, want %q", p.ConfigDir, want)
	}
	if want := filepath.Join(home, ".local", "share", "froster"); p.DataDir != want {
		t.Errorf("DataDir = %q, want %q", p.DataDir, want)
	}
	if want := filepath.Join(home, ".local", "share", "froster", "slurm"); p.SlurmDir() != want {
		t.Errorf("SlurmDir = %q, want %q", p.SlurmDir(), want)
	}
	if want := filepath.Join(home, ".local", "share", "froster", "froster.log"); p.LogFile() != want {
		t.Errorf("LogFile = %q, want %q", p.LogFile(), want)
	}
}

// TestSharedRedirection traces exactly which paths move to the shared
// directory: the archive database and the hotspots dir move; the Slurm dir
// and the log file stay local (as in Python's ConfigManager.__init__).
func TestSharedRedirection(t *testing.T) {
	c, p := loadFixture(t, "shared.ini")

	if !c.IsShared() {
		t.Fatal("shared fixture not detected as shared")
	}
	if got, want := c.SharedDir(), "/srv/froster-shared"; got != want {
		t.Errorf("SharedDir = %q, want %q", got, want)
	}
	if got, want := c.ArchiveJSON(), "/srv/froster-shared/froster-archives.json"; got != want {
		t.Errorf("ArchiveJSON = %q, want %q", got, want)
	}
	if got, want := c.HotspotsDir(), "/srv/froster-shared/hotspots"; got != want {
		t.Errorf("HotspotsDir = %q, want %q", got, want)
	}
	// Not redirected.
	if got, want := c.Paths.SlurmDir(), filepath.Join(p.DataDir, "slurm"); got != want {
		t.Errorf("SlurmDir = %q, want %q (must stay local)", got, want)
	}
	if got, want := c.Paths.LogFile(), filepath.Join(p.DataDir, "froster.log"); got != want {
		t.Errorf("LogFile = %q, want %q (must stay local)", got, want)
	}
}

// TestLocalPathsWhenNotShared verifies the non-shared layout.
func TestLocalPathsWhenNotShared(t *testing.T) {
	c, p := loadFixture(t, "basic.ini")

	if c.IsShared() {
		t.Fatal("basic fixture detected as shared")
	}
	if got, want := c.ArchiveJSON(), filepath.Join(p.DataDir, "froster-archives.json"); got != want {
		t.Errorf("ArchiveJSON = %q, want %q", got, want)
	}
	if got, want := c.HotspotsDir(), filepath.Join(p.DataDir, "hotspots"); got != want {
		t.Errorf("HotspotsDir = %q, want %q", got, want)
	}
}

// TestSharedDirIgnoredWhenNotShared: Python only reads shared_dir when
// is_shared is true; a leftover shared_dir with is_shared = False must not
// redirect anything.
func TestSharedDirIgnoredWhenNotShared(t *testing.T) {
	c, p := loadFixture(t, "basic.ini")
	c.Set("SHARED", "shared_dir", "/srv/leftover")

	if c.SharedDir() != "" {
		t.Errorf("SharedDir = %q, want empty when is_shared is false", c.SharedDir())
	}
	if got, want := c.ArchiveJSON(), filepath.Join(p.DataDir, "froster-archives.json"); got != want {
		t.Errorf("ArchiveJSON = %q, want local %q", got, want)
	}
}
