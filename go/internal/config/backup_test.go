package config

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestLoadCorruptedConfig(t *testing.T) {
	p := testPaths(t)
	if err := os.MkdirAll(p.ConfigDir, 0o775); err != nil {
		t.Fatal(err)
	}
	fixture, err := os.ReadFile(filepath.Join("testdata", "corrupt.ini"))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p.ConfigFile(), fixture, 0o644); err != nil {
		t.Fatal(err)
	}

	_, err = Load(p)
	var ce *CorruptedConfigError
	if !errors.As(err, &ce) {
		t.Fatalf("Load = %v, want *CorruptedConfigError", err)
	}
	if ce.Path != p.ConfigFile() || ce.Size != int64(len(fixture)) {
		t.Errorf("CorruptedConfigError = %+v", ce)
	}
	if !IsConfigCorrupted(p.ConfigFile()) {
		t.Error("IsConfigCorrupted = false for corrupt file")
	}
}

func TestIsConfigCorrupted(t *testing.T) {
	p := testPaths(t)

	// Missing file is not corrupted (fresh install).
	if IsConfigCorrupted(p.ConfigFile()) {
		t.Error("missing file reported as corrupted")
	}

	// A valid-size file is not corrupted.
	if err := os.MkdirAll(p.ConfigDir, 0o775); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p.ConfigFile(), make([]byte, CorruptSizeThreshold), 0o644); err != nil {
		t.Fatal(err)
	}
	if IsConfigCorrupted(p.ConfigFile()) {
		t.Errorf("file of %d bytes reported as corrupted", CorruptSizeThreshold)
	}
}

// makeBackup creates a backup pair (config + data) with the given timestamp.
func makeBackup(t *testing.T, p Paths, ts string, withData bool) {
	t.Helper()
	cdir := filepath.Join(p.ConfigBackupsRoot(), "froster_"+ts+".bak")
	if err := os.MkdirAll(cdir, 0o775); err != nil {
		t.Fatal(err)
	}
	fixture, err := os.ReadFile(filepath.Join("testdata", "basic.ini"))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(cdir, ConfigFileName), fixture, 0o644); err != nil {
		t.Fatal(err)
	}
	if withData {
		ddir := filepath.Join(p.DataBackupsRoot(), "froster_"+ts+".bak")
		if err := os.MkdirAll(ddir, 0o775); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(ddir, ArchiveJSONFileName), []byte("{}\n"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
}

func TestFindLatestBackupAndRestore(t *testing.T) {
	p := testPaths(t)

	// No backups root at all.
	b, err := FindLatestBackup(p)
	if err != nil || b != nil {
		t.Fatalf("FindLatestBackup on empty tree = %v, %v", b, err)
	}

	// An older complete backup and a newer incomplete one (config only):
	// the older complete pair must win, like install.sh's scan.
	makeBackup(t, p, "20250101120000", true)
	makeBackup(t, p, "20261231235959", false)

	b, err = FindLatestBackup(p)
	if err != nil {
		t.Fatal(err)
	}
	if b == nil || b.Timestamp != "20250101120000" {
		t.Fatalf("FindLatestBackup = %+v, want complete backup 20250101120000", b)
	}
	if got := b.Date(); got.Year() != 2025 || got.Month() != time.January {
		t.Errorf("Date = %v", got)
	}

	// Restore is offered only when config is corrupt/missing AND data is
	// missing.
	if !ShouldOfferRestore(p) {
		t.Error("ShouldOfferRestore = false with nothing in place")
	}

	// Corrupted config, no data: still offer.
	if err := os.MkdirAll(p.ConfigDir, 0o775); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p.ConfigFile(), []byte("[US"), 0o644); err != nil {
		t.Fatal(err)
	}
	if !ShouldOfferRestore(p) {
		t.Error("ShouldOfferRestore = false with corrupted config and no data")
	}

	// Restore overwrites the corrupted config and recreates the data file.
	if err := RestoreBackup(p, *b); err != nil {
		t.Fatal(err)
	}
	c, err := Load(p)
	if err != nil {
		t.Fatalf("Load after restore: %v", err)
	}
	if c.Name() != "Jane Doe" {
		t.Errorf("restored config Name = %q", c.Name())
	}
	if _, err := os.Stat(p.LocalArchiveJSON()); err != nil {
		t.Errorf("archive database not restored: %v", err)
	}

	// With valid files in place, no restore is offered anymore.
	if ShouldOfferRestore(p) {
		t.Error("ShouldOfferRestore = true with valid config and data present")
	}
}

func TestShouldOfferRestoreWithValidConfigOnly(t *testing.T) {
	// A valid config with missing data means the user is set up but has not
	// archived anything: no restore (matches install.sh's OR condition).
	_, p := loadFixture(t, "basic.ini")
	if ShouldOfferRestore(p) {
		t.Error("ShouldOfferRestore = true with a valid config file present")
	}
}
