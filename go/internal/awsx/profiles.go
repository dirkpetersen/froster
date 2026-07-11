package awsx

import (
	"bufio"
	"fmt"
	"os"
	"strings"

	"github.com/aws/aws-sdk-go-v2/config"
)

// SharedCredentialsFile returns the path of the AWS shared credentials
// file, honoring the AWS_SHARED_CREDENTIALS_FILE environment variable and
// defaulting to ~/.aws/credentials.
func SharedCredentialsFile() string {
	if p := os.Getenv("AWS_SHARED_CREDENTIALS_FILE"); p != "" {
		return p
	}
	return config.DefaultSharedCredentialsFilename()
}

// ListProfiles returns the profile names defined in the AWS shared
// credentials file (used by the config wizard to offer existing
// credentials, like Python's ConfigManager). A missing file yields an
// empty list, not an error.
func ListProfiles() ([]string, error) {
	path := SharedCredentialsFile()
	if path == "" {
		return nil, nil
	}

	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("awsx: reading credentials file %s: %w", path, err)
	}
	defer f.Close()

	var profiles []string
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			name := strings.TrimSpace(line[1 : len(line)-1])
			if name != "" {
				profiles = append(profiles, name)
			}
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("awsx: reading credentials file %s: %w", path, err)
	}
	return profiles, nil
}

// ProfileExists reports whether the named profile is defined in the shared
// credentials file.
func ProfileExists(name string) (bool, error) {
	profiles, err := ListProfiles()
	if err != nil {
		return false, err
	}
	for _, p := range profiles {
		if p == name {
			return true, nil
		}
	}
	return false, nil
}
