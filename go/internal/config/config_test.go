package config

import (
	"os"
	"strings"
	"testing"
	"time"
)

func TestFreshInitMissingFile(t *testing.T) {
	p := testPaths(t)

	c, err := Load(p)
	if err != nil {
		t.Fatalf("Load on missing file must succeed (fresh install): %v", err)
	}
	if c.Exists() {
		t.Error("Exists() = true for missing file")
	}

	// Python defaults.
	if c.Name() != "" || c.Email() != "" {
		t.Error("fresh config has non-empty user")
	}
	if c.IsShared() || c.IsNIH() {
		t.Error("fresh config has shared/NIH enabled")
	}
	if c.UpdateTimestamp() != 0 {
		t.Error("fresh config has non-zero update timestamp")
	}
	if c.SlurmWalltimeDays() != 7 || c.SlurmWalltimeHours() != 0 {
		t.Errorf("slurm walltime defaults = %d/%d, want 7/0", c.SlurmWalltimeDays(), c.SlurmWalltimeHours())
	}
	if c.DefaultProfileName() != "" {
		t.Error("fresh config has a default profile")
	}

	// Configure and persist like the wizard would.
	c.SetName("Jane Doe")
	c.SetEmail("jane.doe@example.com")
	if err := c.Save(); err != nil {
		t.Fatalf("Save: %v", err)
	}
	if !c.Exists() {
		t.Fatal("config file not created by Save")
	}

	c2, err := Load(p)
	if err != nil {
		t.Fatal(err)
	}
	if c2.Name() != "Jane Doe" || c2.Email() != "jane.doe@example.com" {
		t.Errorf("reloaded user = %q/%q", c2.Name(), c2.Email())
	}
}

func TestTypedAccessors(t *testing.T) {
	c, _ := loadFixture(t, "multi_profile.ini")

	if got := c.Name(); got != "Jane Doe" {
		t.Errorf("Name = %q", got)
	}
	if got := c.Email(); got != "jane.doe@example.com" {
		t.Errorf("Email = %q", got)
	}
	if !c.IsNIH() {
		t.Error("IsNIH = false, want true")
	}
	if c.IsShared() {
		t.Error("IsShared = true, want false")
	}
	if got := c.UpdateTimestamp(); got != 1760666753 {
		t.Errorf("UpdateTimestamp = %d", got)
	}

	// SLURM section.
	if got := c.SlurmPartition(); got != "exacloud" {
		t.Errorf("SlurmPartition = %q", got)
	}
	if got := c.SlurmQOS(); got != "normal" {
		t.Errorf("SlurmQOS = %q", got)
	}
	if got := c.SlurmLscratch(); got != "" {
		t.Errorf("SlurmLscratch = %q, want empty", got)
	}

	// CLOULD (sic) section.
	if got := c.EC2LastInstance(); got != "i-0abc123def4567890" {
		t.Errorf("EC2LastInstance = %q", got)
	}
	if got := c.SESVerifyRequestsSent(); got != "['jane.doe@example.com']" {
		t.Errorf("SESVerifyRequestsSent = %q", got)
	}
}

// TestBoolParsing checks configparser.getboolean spellings.
func TestBoolParsing(t *testing.T) {
	c := New(testPaths(t))
	for _, tc := range []struct {
		raw  string
		want bool
	}{
		{"True", true}, {"true", true}, {"TRUE", true}, {"yes", true},
		{"on", true}, {"1", true},
		{"False", false}, {"no", false}, {"off", false}, {"0", false},
	} {
		c.Set("NIH", "is_nih", tc.raw)
		if got := c.IsNIH(); got != tc.want {
			t.Errorf("is_nih=%q parsed as %v, want %v", tc.raw, got, tc.want)
		}
	}

	// Invalid and empty values fall back to the default.
	c.Set("NIH", "is_nih", "garbage")
	if c.IsNIH() {
		t.Error("invalid bool did not fall back to default false")
	}
	c.Set("NIH", "is_nih", "")
	if c.IsNIH() {
		t.Error("empty bool did not fall back to default false")
	}
}

// TestEmptyValueTreatedAsUnset mirrors Python's __get_configuration_entry,
// which coerces "" to the fallback.
func TestEmptyValueTreatedAsUnset(t *testing.T) {
	c := New(testPaths(t))
	c.Set("SLURM", "slurm_partition", "")
	if got := c.Get("SLURM", "slurm_partition", "fallback"); got != "fallback" {
		t.Errorf("empty value returned %q, want fallback", got)
	}
	c.Set("SLURM", "slurm_walltime_days", "")
	if got := c.SlurmWalltimeDays(); got != 7 {
		t.Errorf("empty int returned %d, want default 7", got)
	}
}

func TestSetSharedAndSetNotShared(t *testing.T) {
	c, _ := loadFixture(t, "basic.ini")

	c.SetShared("/srv/froster-shared")
	if !c.IsShared() || c.SharedDir() != "/srv/froster-shared" {
		t.Errorf("after SetShared: IsShared=%v SharedDir=%q", c.IsShared(), c.SharedDir())
	}

	c.SetNotShared()
	if c.IsShared() {
		t.Error("after SetNotShared: still shared")
	}
	// shared_dir must be removed from the file, like Python's
	// __remove_config_option.
	if got := c.Get("SHARED", "shared_dir", ""); got != "" {
		t.Errorf("shared_dir still present: %q", got)
	}
}

func TestCheckUpdateDue(t *testing.T) {
	p := testPaths(t)
	c := New(p)
	now := time.Now()

	due, err := c.CheckUpdateDue(now)
	if err != nil {
		t.Fatal(err)
	}
	if !due {
		t.Fatal("first check must be due (timestamp 0)")
	}
	if !c.Exists() {
		t.Error("CheckUpdateDue(true) must persist the timestamp")
	}

	due, err = c.CheckUpdateDue(now.Add(time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	if due {
		t.Error("check within a week must not be due")
	}

	due, err = c.CheckUpdateDue(now.Add(UpdateCheckInterval + time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	if !due {
		t.Error("check after a week must be due")
	}
}

func TestSetSESVerifyRequestsSent(t *testing.T) {
	c := New(testPaths(t))
	c.SetSESVerifyRequestsSent([]string{"a@example.com", "b@example.com"})
	if got, want := c.SESVerifyRequestsSent(), "['a@example.com', 'b@example.com']"; got != want {
		t.Errorf("SESVerifyRequestsSent = %q, want %q", got, want)
	}
}

// TestSaveFormat checks the emitted format on a freshly created file:
// lowercase keys, "key = value", blank line after every section.
func TestSaveFormat(t *testing.T) {
	p := testPaths(t)
	c := New(p)
	c.Set("USER", "Name", "Jane Doe") // mixed-case key must be lowercased
	c.SetEmail("jane.doe@example.com")
	c.SetIsNIH(false)
	if err := c.Save(); err != nil {
		t.Fatal(err)
	}

	data, err := os.ReadFile(p.ConfigFile())
	if err != nil {
		t.Fatal(err)
	}
	want := "[USER]\nname = Jane Doe\nemail = jane.doe@example.com\n\n[NIH]\nis_nih = False\n\n"
	if string(data) != want {
		t.Errorf("saved format:\n--- want ---\n%q\n--- got ---\n%q", want, string(data))
	}
	if strings.Contains(string(data), "Name") {
		t.Error("mixed-case key not lowercased")
	}
}
