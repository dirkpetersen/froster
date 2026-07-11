package config

import (
	"os"
	"os/exec"
	"testing"
)

// pythonCrossCheck feeds files written by this package to Python's
// configparser and asserts they parse the way Python froster would read
// them. This is the cross-implementation contract test from
// GO-ARCHITECTURE.md §10; it is skipped when python3 is unavailable.
const pythonCrossCheck = `
import configparser, sys
cfg_file, aws_cfg, aws_creds = sys.argv[1:4]

cfg = configparser.ConfigParser()
cfg.read(cfg_file)
assert cfg.get('USER', 'name') == 'Jane Doe', cfg.get('USER', 'name')
assert cfg.getboolean('SHARED', 'is_shared') is False
assert cfg.getboolean('NIH', 'is_nih') is False
assert cfg.get('DEFAULT_PROFILE', 'profile') == 'profile froster'
assert cfg.get('profile froster', 'provider') == 'AWS'
assert cfg.get('profile froster', 'storage_class') == 'DEEP_ARCHIVE'
assert cfg.getint('UPDATE', 'timestamp') == 1760666753

aws = configparser.ConfigParser()
aws.read(aws_cfg)
assert aws.get('profile froster-example', 'region') == 'us-west-2'
# Replicate froster's nested endpoint parse (get_aws_config_option).
section = dict(aws.items('profile froster-example'))
nested = dict(item.replace(' ', '').split('=')
              for item in section['s3'].split('\n') if item)
assert nested['endpoint_url'] == 'https://s3.us-west-2.amazonaws.com', nested
assert aws.get('profile froster-example', 'output') == 'json'

creds = configparser.ConfigParser()
creds.read(aws_creds)
assert creds.get('froster-example', 'aws_access_key_id') == 'AKIAEXAMPLEEXAMPLE00'
print('ok')
`

func TestPythonConfigparserCrossCheck(t *testing.T) {
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 not available; skipping cross-implementation check")
	}

	p := testPaths(t)

	c := New(p)
	c.SetName("Jane Doe")
	c.SetEmail("jane.doe@example.com")
	c.SetNotShared()
	c.SetIsNIH(false)
	c.SetProfile(Profile{
		Name:         "froster",
		Provider:     "AWS",
		Credentials:  "froster-example",
		BucketName:   "froster-example-bucket",
		ArchiveDir:   "froster",
		StorageClass: "DEEP_ARCHIVE",
	})
	c.SetDefaultProfile("froster")
	c.SetUpdateTimestamp(1760666753)
	if err := c.Save(); err != nil {
		t.Fatal(err)
	}

	a := p.AWS()
	if err := a.SetCredentials("froster-example", "AKIAEXAMPLEEXAMPLE00", "ExampleSecretKeyExampleSecretKeyExample0"); err != nil {
		t.Fatal(err)
	}
	if err := a.SetConfig("froster-example", "us-west-2", "https://s3.us-west-2.amazonaws.com"); err != nil {
		t.Fatal(err)
	}

	cmd := exec.Command(python, "-c", pythonCrossCheck,
		p.ConfigFile(), a.ConfigFile, a.CredentialsFile)
	cmd.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("python configparser cross-check failed: %v\n%s", err, out)
	}
}
