package config

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"
)

// testAWSFiles copies the AWS fixtures into a temp dir.
func testAWSFiles(t *testing.T) AWSFiles {
	t.Helper()
	dir := t.TempDir()
	a := AWSFiles{
		ConfigFile:      filepath.Join(dir, "config"),
		CredentialsFile: filepath.Join(dir, "credentials"),
	}
	for fixture, dst := range map[string]string{
		"aws_config":      a.ConfigFile,
		"aws_credentials": a.CredentialsFile,
	} {
		data, err := os.ReadFile(filepath.Join("testdata", fixture))
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(dst, data, 0o600); err != nil {
			t.Fatal(err)
		}
	}
	return a
}

func TestAWSRegionAndEndpoint(t *testing.T) {
	a := testAWSFiles(t)

	// [default] section: bare name, no "profile " prefix.
	if got := a.Region("default"); got != "us-east-1" {
		t.Errorf("Region(default) = %q", got)
	}
	if got := a.Endpoint("default"); got != "" {
		t.Errorf("Endpoint(default) = %q, want empty (no s3 key)", got)
	}

	// Named profiles, including the nested s3.endpoint_url value.
	if got := a.Region("froster-example"); got != "us-west-2" {
		t.Errorf("Region(froster-example) = %q", got)
	}
	if got, want := a.Endpoint("froster-example"), "https://s3.us-west-2.amazonaws.com"; got != want {
		t.Errorf("Endpoint(froster-example) = %q, want %q", got, want)
	}
	if got, want := a.Endpoint("lab-ceph"), "https://ceph.example.edu:7480"; got != want {
		t.Errorf("Endpoint(lab-ceph) = %q, want %q", got, want)
	}

	// Missing profile or empty profile name.
	if got := a.Region("nope"); got != "" {
		t.Errorf("Region(nope) = %q", got)
	}
	if got := a.Region(""); got != "" {
		t.Errorf("Region(\"\") = %q", got)
	}

	// Missing files return "".
	empty := AWSFiles{
		ConfigFile:      filepath.Join(t.TempDir(), "config"),
		CredentialsFile: filepath.Join(t.TempDir(), "credentials"),
	}
	if got := empty.Region("froster-example"); got != "" {
		t.Errorf("Region with missing file = %q", got)
	}
}

func TestAWSCredentials(t *testing.T) {
	a := testAWSFiles(t)

	if got := a.Credential("froster-example", "aws_access_key_id"); got != "AKIAEXAMPLEEXAMPLE00" {
		t.Errorf("Credential access key = %q", got)
	}
	if got := a.Credential("lab-ceph", "aws_secret_access_key"); got != "CephExampleSecretCephExampleSecret000000" {
		t.Errorf("Credential secret = %q", got)
	}
	if got := a.Credential("nope", "aws_access_key_id"); got != "" {
		t.Errorf("Credential of missing profile = %q", got)
	}

	want := []string{"froster-example", "lab-ceph"}
	if got := a.CredentialProfiles(); !reflect.DeepEqual(got, want) {
		t.Errorf("CredentialProfiles = %v, want %v", got, want)
	}
}

func TestSetCredentials(t *testing.T) {
	a := testAWSFiles(t)

	if err := a.SetCredentials("new-profile", "AKIANEWKEYEXAMPLE000", "NewSecretExampleNewSecretExample00000000"); err != nil {
		t.Fatal(err)
	}

	// New profile present, existing profiles preserved.
	if got := a.Credential("new-profile", "aws_access_key_id"); got != "AKIANEWKEYEXAMPLE000" {
		t.Errorf("new credential = %q", got)
	}
	if got := a.Credential("froster-example", "aws_access_key_id"); got != "AKIAEXAMPLEEXAMPLE00" {
		t.Errorf("existing credential lost: %q", got)
	}

	// File mode 0600 like Python's os.chmod.
	if runtime.GOOS != "windows" {
		st, err := os.Stat(a.CredentialsFile)
		if err != nil {
			t.Fatal(err)
		}
		if st.Mode().Perm() != 0o600 {
			t.Errorf("credentials file mode = %o, want 0600", st.Mode().Perm())
		}
	}

	// Validation errors.
	if err := a.SetCredentials("", "k", "s"); err == nil {
		t.Error("SetCredentials with empty profile must error")
	}
	if err := a.SetCredentials("p", "", "s"); err == nil {
		t.Error("SetCredentials with empty key must error")
	}
	if err := a.SetCredentials("p", "k", ""); err == nil {
		t.Error("SetCredentials with empty secret must error")
	}
}

func TestSetConfig(t *testing.T) {
	dir := t.TempDir()
	a := AWSFiles{
		ConfigFile:      filepath.Join(dir, "aws", "config"),
		CredentialsFile: filepath.Join(dir, "aws", "credentials"),
	}

	// Fresh file: region + endpoint + output written in configparser style.
	if err := a.SetConfig("myprofile", "us-west-2", "https://s3.us-west-2.amazonaws.com"); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(a.ConfigFile)
	if err != nil {
		t.Fatal(err)
	}
	want := "[profile myprofile]\nregion = us-west-2\ns3 = \n\tendpoint_url = https://s3.us-west-2.amazonaws.com\noutput = json\n\n"
	if string(data) != want {
		t.Errorf("SetConfig output:\n--- want ---\n%q\n--- got ---\n%q", want, string(data))
	}

	// The value written must read back through our own parser.
	if got := a.Endpoint("myprofile"); got != "https://s3.us-west-2.amazonaws.com" {
		t.Errorf("Endpoint after SetConfig = %q", got)
	}
	if got := a.Region("myprofile"); got != "us-west-2" {
		t.Errorf("Region after SetConfig = %q", got)
	}

	// Updating only the region keeps the endpoint.
	if err := a.SetConfig("myprofile", "eu-central-1", ""); err != nil {
		t.Fatal(err)
	}
	if got := a.Region("myprofile"); got != "eu-central-1" {
		t.Errorf("Region after update = %q", got)
	}
	if got := a.Endpoint("myprofile"); got != "https://s3.us-west-2.amazonaws.com" {
		t.Errorf("Endpoint lost on region update: %q", got)
	}

	// Default profile uses the bare [default] section (read/write symmetric;
	// Python's write path has a known bug here that we do not reproduce).
	if err := a.SetConfig("default", "us-east-1", ""); err != nil {
		t.Fatal(err)
	}
	if got := a.Region("default"); got != "us-east-1" {
		t.Errorf("Region(default) after SetConfig = %q", got)
	}

	if err := a.SetConfig("", "r", ""); err == nil {
		t.Error("SetConfig with empty profile must error")
	}

	if runtime.GOOS != "windows" {
		st, err := os.Stat(a.ConfigFile)
		if err != nil {
			t.Fatal(err)
		}
		if st.Mode().Perm() != 0o600 {
			t.Errorf("config file mode = %o, want 0600", st.Mode().Perm())
		}
	}
}

// TestAWSConfigRoundTripStable: rewriting the fixture must not mangle the
// nested s3 value (no accumulating indentation).
func TestAWSConfigRoundTripStable(t *testing.T) {
	a := testAWSFiles(t)

	for i := 0; i < 3; i++ {
		if err := a.SetConfig("froster-example", "us-west-2", ""); err != nil {
			t.Fatal(err)
		}
	}
	if got, want := a.Endpoint("froster-example"), "https://s3.us-west-2.amazonaws.com"; got != want {
		t.Errorf("Endpoint after rewrites = %q, want %q", got, want)
	}
	data, err := os.ReadFile(a.ConfigFile)
	if err != nil {
		t.Fatal(err)
	}
	if want := "s3 = \n\tendpoint_url = https://s3.us-west-2.amazonaws.com\n"; strings.Count(string(data), want) != 1 {
		t.Errorf("nested value drifted:\n%q", string(data))
	}
	// Other profiles preserved.
	if got := a.Endpoint("lab-ceph"); got != "https://ceph.example.edu:7480" {
		t.Errorf("lab-ceph endpoint lost: %q", got)
	}
}
