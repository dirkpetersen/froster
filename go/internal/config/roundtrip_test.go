package config

import (
	"os"
	"path/filepath"
	"testing"
)

// testPaths returns Paths rooted in a fresh temp directory.
func testPaths(t *testing.T) Paths {
	t.Helper()
	root := t.TempDir()
	return Paths{
		Home:      root,
		ConfigDir: filepath.Join(root, ".config", "froster"),
		DataDir:   filepath.Join(root, ".local", "share", "froster"),
		AWSDir:    filepath.Join(root, ".aws"),
	}
}

// loadFixture copies a testdata fixture into a temp config dir and loads it.
func loadFixture(t *testing.T, name string) (*Config, Paths) {
	t.Helper()
	p := testPaths(t)
	data, err := os.ReadFile(filepath.Join("testdata", name))
	if err != nil {
		t.Fatalf("reading fixture %s: %v", name, err)
	}
	if err := os.MkdirAll(p.ConfigDir, 0o775); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p.ConfigFile(), data, 0o644); err != nil {
		t.Fatal(err)
	}
	c, err := Load(p)
	if err != nil {
		t.Fatalf("loading fixture %s: %v", name, err)
	}
	return c, p
}

// TestRoundTripByteExact verifies that a configparser-written config.ini
// survives Load+Save byte-for-byte. The fixtures were generated with
// Python's configparser, so this is the drop-in compatibility contract:
// zero diff for files Python froster wrote.
func TestRoundTripByteExact(t *testing.T) {
	for _, name := range []string{"basic.ini", "multi_profile.ini", "shared.ini", "minimal.ini"} {
		t.Run(name, func(t *testing.T) {
			c, p := loadFixture(t, name)
			if err := c.Save(); err != nil {
				t.Fatalf("Save: %v", err)
			}
			got, err := os.ReadFile(p.ConfigFile())
			if err != nil {
				t.Fatal(err)
			}
			want, err := os.ReadFile(filepath.Join("testdata", name))
			if err != nil {
				t.Fatal(err)
			}
			if string(got) != string(want) {
				t.Errorf("round trip of %s not byte-identical:\n--- want ---\n%s\n--- got ---\n%s", name, want, got)
			}
		})
	}
}

// TestRoundTripCommented documents the tolerated diff for hand-edited
// files: comments are preserved (Python's configparser would drop them) and
// the layout is normalized to configparser's canonical form (a blank line
// after the last section). The golden file captures that exact output.
func TestRoundTripCommented(t *testing.T) {
	c, p := loadFixture(t, "commented.ini")
	if err := c.Save(); err != nil {
		t.Fatalf("Save: %v", err)
	}
	got, err := os.ReadFile(p.ConfigFile())
	if err != nil {
		t.Fatal(err)
	}
	want, err := os.ReadFile(filepath.Join("testdata", "commented.golden.ini"))
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(want) {
		t.Errorf("commented round trip mismatch:\n--- want ---\n%s\n--- got ---\n%s", want, got)
	}
}

// TestRoundTripStable verifies that repeated Load+Save cycles are stable
// (no drift, e.g. no accumulating indentation in multi-line values).
func TestRoundTripStable(t *testing.T) {
	c, p := loadFixture(t, "multi_profile.ini")
	if err := c.Save(); err != nil {
		t.Fatal(err)
	}
	first, err := os.ReadFile(p.ConfigFile())
	if err != nil {
		t.Fatal(err)
	}
	c2, err := Load(p)
	if err != nil {
		t.Fatal(err)
	}
	if err := c2.Save(); err != nil {
		t.Fatal(err)
	}
	second, err := os.ReadFile(p.ConfigFile())
	if err != nil {
		t.Fatal(err)
	}
	if string(first) != string(second) {
		t.Errorf("second round trip drifted:\n--- first ---\n%s\n--- second ---\n%s", first, second)
	}
}

// TestUnknownKeysAndSectionsPreserved ensures froster does not drop config
// content it does not understand (a Python froster may rely on it).
func TestUnknownKeysAndSectionsPreserved(t *testing.T) {
	c, p := loadFixture(t, "multi_profile.ini")

	// Touch a known key, then rewrite.
	c.SetEmail("jane.doe@example.com")
	if err := c.Save(); err != nil {
		t.Fatal(err)
	}

	c2, err := Load(p)
	if err != nil {
		t.Fatal(err)
	}
	if got := c2.Get("FUTURE_SECTION", "some_key", ""); got != "some value" {
		t.Errorf("unknown section lost: got %q", got)
	}
	if got := c2.Get("profile ceph-lab", "custom_future_key", ""); got != "kept-verbatim" {
		t.Errorf("unknown profile key lost: got %q", got)
	}
}
