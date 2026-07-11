// Package awsx is froster's AWS control plane (GO-ARCHITECTURE.md §6.5).
//
// It mirrors the boto3-based AWSBoto class from froster/froster.py: bucket
// management, Glacier restore triggering and status polling, and storage
// class (tier) changes. Data transfers stay with rclone (internal/transfer);
// this package only performs control-plane calls via aws-sdk-go-v2.
//
// All errors returned by Client methods are annotated with the active AWS
// credentials profile name, matching the Python behavior introduced in
// commit 95b9adf ("include AWS profile in error messages").
package awsx

import (
	"context"
	"fmt"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/sts"
)

// GlacierStorageClasses are the storage classes that require a restore
// before objects can be read or re-tiered (Python: glacier_tiers).
var GlacierStorageClasses = map[string]bool{
	"GLACIER":      true,
	"DEEP_ARCHIVE": true,
}

// StandardMetadataFiles are froster metadata artifacts that must always
// remain in the STANDARD storage class (Python: standard_files in
// change_storage_class).
var StandardMetadataFiles = map[string]bool{
	"Froster.allfiles.csv":     true,
	".froster.md5sum":          true,
	".froster-restored.md5sum": true,
}

// Options configures a Client. It carries the values that froster's
// ConfigManager stores per profile: the shared-credentials profile name,
// the provider, the region, and an optional custom endpoint.
type Options struct {
	// Profile is the AWS shared-credentials profile name (ConfigManager's
	// "credentials" key). Required. It is loaded via SharedConfigProfile,
	// so ~/.aws/credentials and ~/.aws/config are honored exactly like
	// boto3.Session(profile_name=...).
	Profile string

	// Region is the region to use. If empty, the region from the shared
	// config profile (or SDK defaults) applies.
	Region string

	// Endpoint is a custom S3-compatible endpoint URL for non-AWS
	// providers (Ceph, Minio, Wasabi, IDrive, GCS interop). Empty means
	// standard AWS endpoints. When set, path-style addressing is enabled,
	// since most S3-compatible endpoints do not support virtual-hosted
	// bucket DNS.
	Endpoint string

	// Provider is the provider label from froster's config ("AWS", "GCS",
	// "Wasabi", "IDrive", "Ceph", "Minio", ...). Provider "AWS" enables
	// AWS-only behaviors such as default bucket encryption on creation.
	Provider string

	// HTTPClient optionally overrides the HTTP client used by all AWS
	// service clients (primarily for tests).
	HTTPClient aws.HTTPClient
}

// Client exposes froster's AWS control-plane operations. Construct it with
// New; the zero value is not usable.
type Client struct {
	profile  string
	provider string
	region   string
	endpoint string

	s3  *s3.Client
	sts *sts.Client
}

// New builds a Client from the given options. Credentials are resolved from
// the shared config/credentials files using opts.Profile, mirroring
// boto3.Session(profile_name=...).
func New(ctx context.Context, opts Options) (*Client, error) {
	if opts.Profile == "" {
		return nil, fmt.Errorf("awsx: no AWS credentials profile provided")
	}

	loadOpts := []func(*config.LoadOptions) error{
		config.WithSharedConfigProfile(opts.Profile),
	}
	if opts.Region != "" {
		loadOpts = append(loadOpts, config.WithRegion(opts.Region))
	}
	if opts.HTTPClient != nil {
		loadOpts = append(loadOpts, config.WithHTTPClient(opts.HTTPClient))
	}

	cfg, err := config.LoadDefaultConfig(ctx, loadOpts...)
	if err != nil {
		return nil, fmt.Errorf("awsx: loading AWS config (AWS profile: %s): %w", opts.Profile, err)
	}

	s3Client := s3.NewFromConfig(cfg, func(o *s3.Options) {
		if opts.Endpoint != "" {
			o.BaseEndpoint = aws.String(opts.Endpoint)
			// S3-compatible endpoints (Minio, Ceph, ...) generally require
			// path-style addressing; bucket-DNS resolution is AWS-only.
			o.UsePathStyle = true
		}
	})
	stsClient := sts.NewFromConfig(cfg, func(o *sts.Options) {
		if opts.Endpoint != "" {
			o.BaseEndpoint = aws.String(opts.Endpoint)
		}
	})

	return &Client{
		profile:  opts.Profile,
		provider: opts.Provider,
		region:   cfg.Region,
		endpoint: opts.Endpoint,
		s3:       s3Client,
		sts:      stsClient,
	}, nil
}

// Profile returns the AWS credentials profile the client was built with.
func (c *Client) Profile() string { return c.profile }

// Region returns the resolved region.
func (c *Client) Region() string { return c.region }

// wrapErr annotates an AWS error with the operation and the active profile
// name, so users can tell which credentials were in play (Python parity:
// commit 95b9adf).
func (c *Client) wrapErr(op string, err error) error {
	return fmt.Errorf("awsx: %s (AWS profile: %s): %w", op, c.profile, err)
}

// CallerIdentity is the result of an STS GetCallerIdentity call.
type CallerIdentity struct {
	Account string
	Arn     string
	UserID  string
}

// CheckCredentials validates the active credentials via STS
// GetCallerIdentity and returns the caller identity.
func (c *Client) CheckCredentials(ctx context.Context) (CallerIdentity, error) {
	out, err := c.sts.GetCallerIdentity(ctx, &sts.GetCallerIdentityInput{})
	if err != nil {
		return CallerIdentity{}, c.wrapErr("checking credentials", err)
	}
	return CallerIdentity{
		Account: aws.ToString(out.Account),
		Arn:     aws.ToString(out.Arn),
		UserID:  aws.ToString(out.UserId),
	}, nil
}

// baseName returns the final path element of an S3 key (Python:
// key.split('/')[-1]).
func baseName(key string) string {
	if i := strings.LastIndexByte(key, '/'); i >= 0 {
		return key[i+1:]
	}
	return key
}
