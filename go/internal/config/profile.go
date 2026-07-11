package config

import (
	"fmt"
	"strings"
)

// Profile section keys, exactly as Python's ConfigManager writes them.
const (
	keyProvider     = "provider"
	keyCredentials  = "credentials"
	keyBucketName   = "bucket_name"
	keyArchiveDir   = "archive_dir"
	keyStorageClass = "storage_class"

	// exported_region / exported_endpoint only appear in configuration
	// templates produced by "froster config --export"; they carry the
	// region/endpoint of the exporting user (whose ~/.aws/config we cannot
	// see) and are removed again once the importing user runs the wizard.
	keyExportedRegion   = "exported_region"
	keyExportedEndpoint = "exported_endpoint"
)

// Providers froster's wizard offers (Python: PROVIDERS_LIST).
var Providers = []string{"AWS", "GCS", "Wasabi", "IDrive", "Ceph", "Minio", "Other"}

// Profile is one [profile <name>] section of config.ini.
//
// Note that region and endpoint are NOT stored here: Python froster keeps
// them in ~/.aws/config under the credentials profile (see AWSFiles); a
// profile only records which credentials profile it uses.
type Profile struct {
	// Name is the full section name including the "profile " prefix,
	// e.g. "profile froster".
	Name string

	// Provider is one of Providers (e.g. "AWS").
	Provider string
	// Credentials is the name of the profile in ~/.aws/credentials and
	// ~/.aws/config that holds keys, region and endpoint.
	Credentials string
	// BucketName is the S3 bucket archives are written to.
	BucketName string
	// ArchiveDir is the prefix directory inside the bucket (default
	// "froster" in the wizard).
	ArchiveDir string
	// StorageClass is the S3 storage class (e.g. "DEEP_ARCHIVE").
	StorageClass string

	// ExportedRegion/ExportedEndpoint are only present in exported
	// configuration templates; see the key documentation above.
	ExportedRegion   string
	ExportedEndpoint string
}

// CanonicalProfileName prepends the "profile " prefix if name does not
// already carry it (Python: ConfigManager.__init__ use_profile handling).
func CanonicalProfileName(name string) string {
	if strings.HasPrefix(name, profilePrefix) {
		return name
	}
	return profilePrefix + name
}

// ShortProfileName strips the "profile " prefix if present.
func ShortProfileName(name string) string {
	return strings.TrimPrefix(name, profilePrefix)
}

// ProfileNames returns the full names of all [profile <name>] sections in
// file order.
func (c *Config) ProfileNames() []string {
	var out []string
	for _, name := range c.Sections() {
		if strings.HasPrefix(name, profilePrefix) {
			out = append(out, name)
		}
	}
	return out
}

// HasProfile reports whether the profile section exists. The match is
// case-sensitive, like Python's configparser section lookup.
func (c *Config) HasProfile(name string) bool {
	_, err := c.file.GetSection(CanonicalProfileName(name))
	return err == nil
}

// Profile returns the named profile. The name may be given with or without
// the "profile " prefix.
func (c *Config) Profile(name string) (Profile, error) {
	canonical := CanonicalProfileName(name)
	if !c.HasProfile(canonical) {
		return Profile{}, fmt.Errorf("%q does not exist in the configuration file (remember case sensitive)", canonical)
	}
	return Profile{
		Name:             canonical,
		Provider:         c.Get(canonical, keyProvider, ""),
		Credentials:      c.Get(canonical, keyCredentials, ""),
		BucketName:       c.Get(canonical, keyBucketName, ""),
		ArchiveDir:       c.Get(canonical, keyArchiveDir, ""),
		StorageClass:     c.Get(canonical, keyStorageClass, ""),
		ExportedRegion:   c.Get(canonical, keyExportedRegion, ""),
		ExportedEndpoint: c.Get(canonical, keyExportedEndpoint, ""),
	}, nil
}

// SetProfile creates or updates a profile section. The five core keys are
// written in the order the Python wizard creates them (provider,
// credentials, bucket_name, archive_dir, storage_class). Exported keys are
// written only when non-empty and removed when empty (Python's wizard
// removes them after the region/endpoint have been configured locally).
// Unknown keys already present in the section are preserved.
func (c *Config) SetProfile(p Profile) {
	name := CanonicalProfileName(p.Name)
	c.Set(name, keyProvider, p.Provider)
	c.Set(name, keyCredentials, p.Credentials)
	c.Set(name, keyBucketName, p.BucketName)
	c.Set(name, keyArchiveDir, p.ArchiveDir)
	c.Set(name, keyStorageClass, p.StorageClass)

	setOrDelete := func(key, value string) {
		if value != "" {
			c.Set(name, key, value)
		} else {
			c.Delete(name, key)
		}
	}
	setOrDelete(keyExportedRegion, p.ExportedRegion)
	setOrDelete(keyExportedEndpoint, p.ExportedEndpoint)
}

// DeleteProfile removes a profile section. If it was the default profile,
// the [DEFAULT_PROFILE] selection is cleared as well. It reports whether
// the profile existed.
func (c *Config) DeleteProfile(name string) bool {
	canonical := CanonicalProfileName(name)
	if !c.HasProfile(canonical) {
		return false
	}
	c.DeleteSection(canonical)
	if c.DefaultProfileName() == canonical {
		c.Delete(sectionDefaultProfile, keyProfile)
	}
	return true
}

// DefaultProfileName returns the full section name selected in
// [DEFAULT_PROFILE] (e.g. "profile froster"), or "" when none is set.
func (c *Config) DefaultProfileName() string {
	return c.Get(sectionDefaultProfile, keyProfile, "")
}

// SetDefaultProfile records name (with or without prefix) as the default
// profile in [DEFAULT_PROFILE].
func (c *Config) SetDefaultProfile(name string) {
	c.Set(sectionDefaultProfile, keyProfile, CanonicalProfileName(name))
}

// ResolveProfile implements the profile selection from Python's
// ConfigManager.__init__: when useProfile (the --profile flag) is non-empty
// it is canonicalized and must exist (case-sensitively) or an error is
// returned; otherwise the [DEFAULT_PROFILE] selection is returned, which
// may be "" on an unconfigured system.
func (c *Config) ResolveProfile(useProfile string) (string, error) {
	if useProfile == "" {
		return c.DefaultProfileName(), nil
	}
	canonical := CanonicalProfileName(useProfile)
	if !c.HasProfile(canonical) {
		return "", fmt.Errorf("%q does not exist in the configuration file (remember case sensitive)", canonical)
	}
	return canonical, nil
}

// ExportedRegion returns the exported_region key of a profile, or ""
// (Python: get_exported_region).
func (c *Config) ExportedRegion(profile string) string {
	return c.Get(CanonicalProfileName(profile), keyExportedRegion, "")
}

// ExportedEndpoint returns the exported_endpoint key of a profile, or ""
// (Python: get_exported_endpoint).
func (c *Config) ExportedEndpoint(profile string) string {
	return c.Get(CanonicalProfileName(profile), keyExportedEndpoint, "")
}
