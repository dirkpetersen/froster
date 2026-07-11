package config

import (
	"reflect"
	"strings"
	"testing"
)

func TestProfileNamesAndDefault(t *testing.T) {
	c, _ := loadFixture(t, "multi_profile.ini")

	want := []string{"profile aws-deep", "profile ceph-lab", "profile imported"}
	if got := c.ProfileNames(); !reflect.DeepEqual(got, want) {
		t.Errorf("ProfileNames = %v, want %v", got, want)
	}
	if got := c.DefaultProfileName(); got != "profile aws-deep" {
		t.Errorf("DefaultProfileName = %q", got)
	}
}

func TestGetProfileFields(t *testing.T) {
	c, _ := loadFixture(t, "multi_profile.ini")

	p, err := c.Profile("aws-deep") // short name accepted
	if err != nil {
		t.Fatal(err)
	}
	want := Profile{
		Name:         "profile aws-deep",
		Provider:     "AWS",
		Credentials:  "froster-aws",
		BucketName:   "froster-deep-archive",
		ArchiveDir:   "froster",
		StorageClass: "DEEP_ARCHIVE",
	}
	if p != want {
		t.Errorf("Profile = %+v, want %+v", p, want)
	}

	// Exported template keys.
	imp, err := c.Profile("profile imported")
	if err != nil {
		t.Fatal(err)
	}
	if imp.ExportedRegion != "us-west-2" || imp.ExportedEndpoint != "https://s3.us-west-2.amazonaws.com" {
		t.Errorf("exported keys = %q/%q", imp.ExportedRegion, imp.ExportedEndpoint)
	}
	if imp.Credentials != "" {
		t.Errorf("imported profile has credentials %q, want empty (stripped on export)", imp.Credentials)
	}
}

func TestProfileCaseSensitive(t *testing.T) {
	c, _ := loadFixture(t, "multi_profile.ini")

	if _, err := c.Profile("AWS-DEEP"); err == nil {
		t.Error("profile lookup must be case-sensitive like configparser sections")
	} else if !strings.Contains(err.Error(), "case sensitive") {
		t.Errorf("error should mention case sensitivity (Python parity): %v", err)
	}
}

func TestResolveProfile(t *testing.T) {
	c, _ := loadFixture(t, "multi_profile.ini")

	// No --profile flag: default profile.
	got, err := c.ResolveProfile("")
	if err != nil || got != "profile aws-deep" {
		t.Errorf("ResolveProfile(\"\") = %q, %v", got, err)
	}

	// Short and canonical forms.
	for _, in := range []string{"ceph-lab", "profile ceph-lab"} {
		got, err := c.ResolveProfile(in)
		if err != nil || got != "profile ceph-lab" {
			t.Errorf("ResolveProfile(%q) = %q, %v", in, got, err)
		}
	}

	// Missing profile errors.
	if _, err := c.ResolveProfile("nope"); err == nil {
		t.Error("ResolveProfile of missing profile must error")
	}

	// Unconfigured system: empty default, no error.
	fresh := New(testPaths(t))
	got, err = fresh.ResolveProfile("")
	if err != nil || got != "" {
		t.Errorf("fresh ResolveProfile(\"\") = %q, %v", got, err)
	}
}

func TestProfileCRUD(t *testing.T) {
	c, p := loadFixture(t, "basic.ini")

	// Create.
	c.SetProfile(Profile{
		Name:         "wasabi-cold",
		Provider:     "Wasabi",
		Credentials:  "wasabi-keys",
		BucketName:   "wasabi-archive",
		ArchiveDir:   "froster",
		StorageClass: "STANDARD",
	})
	if err := c.Save(); err != nil {
		t.Fatal(err)
	}

	c2, err := Load(p)
	if err != nil {
		t.Fatal(err)
	}
	np, err := c2.Profile("wasabi-cold")
	if err != nil {
		t.Fatalf("created profile not found after reload: %v", err)
	}
	if np.Provider != "Wasabi" || np.BucketName != "wasabi-archive" {
		t.Errorf("created profile = %+v", np)
	}

	// Update: change one field, unknown keys must survive.
	c2.Set("profile wasabi-cold", "future_key", "keep-me")
	np.StorageClass = "DEEP_ARCHIVE"
	c2.SetProfile(np)
	upd, err := c2.Profile("wasabi-cold")
	if err != nil {
		t.Fatal(err)
	}
	if upd.StorageClass != "DEEP_ARCHIVE" {
		t.Errorf("StorageClass not updated: %q", upd.StorageClass)
	}
	if got := c2.Get("profile wasabi-cold", "future_key", ""); got != "keep-me" {
		t.Errorf("unknown key lost on update: %q", got)
	}

	// Default profile selection.
	c2.SetDefaultProfile("wasabi-cold")
	if got := c2.DefaultProfileName(); got != "profile wasabi-cold" {
		t.Errorf("DefaultProfileName = %q", got)
	}

	// Delete clears the default selection too.
	if !c2.DeleteProfile("wasabi-cold") {
		t.Fatal("DeleteProfile returned false for existing profile")
	}
	if c2.HasProfile("wasabi-cold") {
		t.Error("profile still present after delete")
	}
	if got := c2.DefaultProfileName(); got != "" {
		t.Errorf("default profile not cleared after delete: %q", got)
	}
	if c2.DeleteProfile("wasabi-cold") {
		t.Error("DeleteProfile returned true for missing profile")
	}
}

// TestSetProfileClearsEmptyExportedKeys mirrors Python's wizard, which
// removes exported_region/exported_endpoint once region and endpoint are
// configured locally.
func TestSetProfileClearsEmptyExportedKeys(t *testing.T) {
	c, _ := loadFixture(t, "multi_profile.ini")

	imp, err := c.Profile("imported")
	if err != nil {
		t.Fatal(err)
	}
	imp.Credentials = "my-creds"
	imp.ExportedRegion = ""
	imp.ExportedEndpoint = ""
	c.SetProfile(imp)

	if got := c.Get("profile imported", "exported_region", ""); got != "" {
		t.Errorf("exported_region not removed: %q", got)
	}
	if got := c.Get("profile imported", "exported_endpoint", ""); got != "" {
		t.Errorf("exported_endpoint not removed: %q", got)
	}
}

func TestCanonicalProfileName(t *testing.T) {
	if got := CanonicalProfileName("x"); got != "profile x" {
		t.Errorf("CanonicalProfileName(x) = %q", got)
	}
	if got := CanonicalProfileName("profile x"); got != "profile x" {
		t.Errorf("CanonicalProfileName(profile x) = %q", got)
	}
	if got := ShortProfileName("profile x"); got != "x" {
		t.Errorf("ShortProfileName = %q", got)
	}
}
