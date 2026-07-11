package transfer

import (
	"errors"
	"fmt"
	"strings"
)

// s3Prefix is froster's remote notation, as stored in froster-archives.json.
const s3Prefix = ":s3:"

// IsS3Remote reports whether remote uses froster's ":s3:bucket/prefix"
// notation (as opposed to a local path).
func IsS3Remote(remote string) bool {
	return strings.HasPrefix(remote, s3Prefix)
}

// ConnString translates a froster remote into a string accepted by rclone's
// fs.NewFs. Local paths pass through unchanged. ":s3:bucket/prefix" becomes
// an on-the-fly connection-string remote (":s3,provider=…,endpoint=…:bucket/prefix")
// carrying cfg entirely in memory, so credentials never touch disk. rclone
// displays connection-string remotes as ":s3{hash}:bucket/prefix", so the
// synthesized parameters do not leak into logs either.
func ConnString(remote string, cfg S3Config) (string, error) {
	if !IsS3Remote(remote) {
		return remote, nil
	}
	bucketPath := strings.TrimPrefix(remote, s3Prefix)

	if !cfg.EnvAuth && (cfg.AccessKeyID == "" || cfg.SecretAccessKey == "") {
		return "", errors.New("no S3 credentials configured: set AccessKeyID/SecretAccessKey or EnvAuth")
	}

	var params []string
	add := func(key, value string) {
		if value != "" {
			params = append(params, key+"="+quoteConnValue(value))
		}
	}
	if cfg.EnvAuth {
		add("env_auth", "true")
	}
	add("provider", cfg.Provider)
	add("endpoint", cfg.Endpoint)
	add("region", cfg.Region)
	// The Python implementation always sets the location constraint to
	// the region (RCLONE_S3_LOCATION_CONSTRAINT).
	add("location_constraint", cfg.Region)
	add("access_key_id", cfg.AccessKeyID)
	add("secret_access_key", cfg.SecretAccessKey)
	add("session_token", cfg.SessionToken)
	add("storage_class", cfg.StorageClass)
	if cfg.NoCheckBucket || cfg.Provider == "Ceph" {
		add("no_check_bucket", "true")
	}

	return fmt.Sprintf(":s3,%s:%s", strings.Join(params, ","), bucketPath), nil
}

// quoteConnValue quotes a connection-string parameter value if it contains
// characters that are significant to rclone's fspath grammar (comma ends the
// parameter, colon ends the config section, quotes start quoting). Embedded
// double quotes are doubled, per the grammar.
func quoteConnValue(v string) string {
	if !strings.ContainsAny(v, `,:'" `) {
		return v
	}
	return `"` + strings.ReplaceAll(v, `"`, `""`) + `"`
}
