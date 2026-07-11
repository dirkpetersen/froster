package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	ini "gopkg.in/ini.v1"
)

// AWSFiles reads and writes ~/.aws/credentials and ~/.aws/config the way
// Python froster's ConfigManager does:
//
//   - ~/.aws/credentials holds [<name>] sections with aws_access_key_id and
//     aws_secret_access_key.
//   - ~/.aws/config holds [default] or [profile <name>] sections with
//     region, output, and a configparser-style nested value
//     "s3 = \n endpoint_url = <url>" for non-default S3 endpoints.
//
// Both files are rewritten wholesale on updates (like Python, which
// round-trips them through configparser), preserving key order and unknown
// keys; unlike Python, comments are preserved too. Files are written with
// mode 0600 and the AWS directory is created with mode 0775, matching
// Python.
//
// Construct via Paths.AWS, or fill the struct directly in tests.
type AWSFiles struct {
	// ConfigFile is the path of the AWS config file (~/.aws/config).
	ConfigFile string
	// CredentialsFile is the path of the AWS credentials file
	// (~/.aws/credentials).
	CredentialsFile string
}

// awsConfigSection maps a credentials profile name to its section name in
// ~/.aws/config: "default" stays bare, anything else gets the "profile "
// prefix. (Python's read path, get_aws_config_option, does exactly this.
// Python's write path, __set_aws_config, has a bug: it always writes
// "profile <name>", producing an unreadable "[profile default]" section for
// the default profile. We deliberately use the read mapping on both paths.)
func awsConfigSection(credentialsProfile string) string {
	if credentialsProfile == "default" {
		return "default"
	}
	return "profile " + credentialsProfile
}

func loadAWSFile(path string) (*ini.File, error) {
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return ini.Empty(loadOptions()), nil
	}
	f, err := ini.LoadSources(loadOptions(), path)
	if err != nil {
		return nil, fmt.Errorf("parsing %s: %w", path, err)
	}
	normalizeMultilineValues(f)
	return f, nil
}

// ConfigOption returns an option for the given credentials profile from the
// AWS config file (Python: get_aws_config_option). A dotted option such as
// "s3.endpoint_url" is resolved inside the configparser-style nested value
// of the parent key. Returns "" when the file, section or option is absent.
func (a AWSFiles) ConfigOption(credentialsProfile, option string) string {
	if credentialsProfile == "" {
		return ""
	}
	f, err := loadAWSFile(a.ConfigFile)
	if err != nil {
		return ""
	}
	sec, err := f.GetSection(awsConfigSection(credentialsProfile))
	if err != nil {
		return ""
	}

	parent, child, nested := strings.Cut(option, ".")
	if nested {
		k, err := sec.GetKey(strings.ToLower(parent))
		if err != nil {
			return ""
		}
		return nestedValue(k.Value(), child)
	}

	k, err := sec.GetKey(strings.ToLower(option))
	if err != nil {
		return ""
	}
	return k.Value()
}

// nestedValue parses a configparser-style nested value (lines of
// "key = value") and returns the entry named child, or "". It mirrors the
// Python parse: spaces are stripped and each line is split on '='.
func nestedValue(value, child string) string {
	for _, line := range strings.Split(value, "\n") {
		line = strings.ReplaceAll(strings.ReplaceAll(line, " ", ""), "\t", "")
		if line == "" {
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if ok && k == child {
			return v
		}
	}
	return ""
}

// Region returns the region configured for the credentials profile
// (Python: get_region), or "".
func (a AWSFiles) Region(credentialsProfile string) string {
	return a.ConfigOption(credentialsProfile, "region")
}

// Endpoint returns the S3 endpoint_url configured for the credentials
// profile (Python: get_endpoint), or "".
func (a AWSFiles) Endpoint(credentialsProfile string) string {
	return a.ConfigOption(credentialsProfile, "s3.endpoint_url")
}

// Credential returns a key (e.g. "aws_access_key_id") from the credentials
// file for the given profile (Python: get_credential), or "".
func (a AWSFiles) Credential(credentialsProfile, keyName string) string {
	if credentialsProfile == "" {
		return ""
	}
	f, err := loadAWSFile(a.CredentialsFile)
	if err != nil {
		return ""
	}
	sec, err := f.GetSection(credentialsProfile)
	if err != nil {
		return ""
	}
	k, err := sec.GetKey(strings.ToLower(keyName))
	if err != nil {
		return ""
	}
	return k.Value()
}

// CredentialProfiles returns the section names of the credentials file in
// file order (Python: the choices listed by set_credentials).
func (a AWSFiles) CredentialProfiles() []string {
	f, err := loadAWSFile(a.CredentialsFile)
	if err != nil {
		return nil
	}
	var out []string
	for _, sec := range f.Sections() {
		if sec.Name() == ini.DefaultSection {
			continue
		}
		out = append(out, sec.Name())
	}
	return out
}

// SetConfig updates the AWS config file for a credentials profile
// (Python: __set_aws_config). A non-empty region and/or endpoint is written;
// "output = json" is always set. The whole file is rewritten in
// configparser style and chmod'ed to 0600.
func (a AWSFiles) SetConfig(credentialsProfile, region, endpoint string) error {
	if credentialsProfile == "" {
		return fmt.Errorf("no AWS credentials profile provided")
	}

	f, err := loadAWSFile(a.ConfigFile)
	if err != nil {
		return err
	}

	sec := f.Section(awsConfigSection(credentialsProfile))
	if region != "" {
		sec.Key("region").SetValue(region)
	}
	if endpoint != "" {
		// configparser-style nested value; Python writes
		// "\n  endpoint_url = <url>", which normalizes to this form after
		// one configparser read/write cycle.
		sec.Key("s3").SetValue("\nendpoint_url = " + endpoint)
	}
	sec.Key("output").SetValue("json")

	return writeAWSFile(a.ConfigFile, f)
}

// SetCredentials creates or updates a profile in the credentials file with
// the given access key pair (Python: __set_aws_credentials). The whole file
// is rewritten and chmod'ed to 0600.
func (a AWSFiles) SetCredentials(profileName, accessKeyID, secretAccessKey string) error {
	switch {
	case profileName == "":
		return fmt.Errorf("no AWS profile provided")
	case accessKeyID == "":
		return fmt.Errorf("no AWS access key id provided")
	case secretAccessKey == "":
		return fmt.Errorf("no AWS secret access key provided")
	}

	f, err := loadAWSFile(a.CredentialsFile)
	if err != nil {
		return err
	}

	sec := f.Section(profileName)
	sec.Key("aws_access_key_id").SetValue(accessKeyID)
	sec.Key("aws_secret_access_key").SetValue(secretAccessKey)

	return writeAWSFile(a.CredentialsFile, f)
}

// writeAWSFile writes an AWS ini file atomically with the permissions
// Python uses (directory 0775, file 0600).
func writeAWSFile(path string, f *ini.File) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o775); err != nil {
		return fmt.Errorf("creating directory %s: %w", dir, err)
	}

	tmp, err := os.CreateTemp(dir, filepath.Base(path)+".tmp*")
	if err != nil {
		return fmt.Errorf("writing %s: %w", path, err)
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName)

	if _, err := tmp.Write(marshalINI(f)); err != nil {
		tmp.Close()
		return fmt.Errorf("writing %s: %w", path, err)
	}
	if err := tmp.Chmod(0o600); err != nil {
		tmp.Close()
		return fmt.Errorf("writing %s: %w", path, err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("writing %s: %w", path, err)
	}
	if err := os.Rename(tmpName, path); err != nil {
		return fmt.Errorf("writing %s: %w", path, err)
	}
	return nil
}
