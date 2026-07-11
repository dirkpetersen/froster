package awsx

import (
	"context"
	"errors"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	s3types "github.com/aws/aws-sdk-go-v2/service/s3/types"
)

// ListBuckets returns the names of all buckets visible to the current
// credentials (Python: AWSBoto.get_buckets).
func (c *Client) ListBuckets(ctx context.Context) ([]string, error) {
	out, err := c.s3.ListBuckets(ctx, &s3.ListBucketsInput{})
	if err != nil {
		return nil, c.wrapErr("listing buckets", err)
	}
	names := make([]string, 0, len(out.Buckets))
	for _, b := range out.Buckets {
		names = append(names, aws.ToString(b.Name))
	}
	return names, nil
}

// BucketExists reports whether the bucket exists and is reachable with the
// current credentials, using HeadBucket. A 404/NotFound response yields
// (false, nil); any other failure is returned as an error.
func (c *Client) BucketExists(ctx context.Context, bucket string) (bool, error) {
	if bucket == "" {
		return false, errors.New("awsx: no bucket name provided")
	}
	_, err := c.s3.HeadBucket(ctx, &s3.HeadBucketInput{Bucket: aws.String(bucket)})
	if err != nil {
		var nf *s3types.NotFound
		if errors.As(err, &nf) {
			return false, nil
		}
		return false, c.wrapErr("checking bucket "+bucket, err)
	}
	return true, nil
}

// CreateBucket creates the bucket in the given region (Python:
// AWSBoto.create_bucket). The LocationConstraint is region-aware: AWS
// rejects an explicit "us-east-1" constraint, so it is omitted there.
// For provider "AWS", default AES256 server-side encryption is applied to
// the new bucket, matching the Python behavior.
func (c *Client) CreateBucket(ctx context.Context, bucket, region string) error {
	if bucket == "" {
		return errors.New("awsx: no bucket name provided")
	}

	input := &s3.CreateBucketInput{Bucket: aws.String(bucket)}
	if region != "" && region != "us-east-1" {
		input.CreateBucketConfiguration = &s3types.CreateBucketConfiguration{
			LocationConstraint: s3types.BucketLocationConstraint(region),
		}
	}
	if _, err := c.s3.CreateBucket(ctx, input); err != nil {
		return c.wrapErr("creating bucket "+bucket, err)
	}

	if c.provider == "AWS" {
		_, err := c.s3.PutBucketEncryption(ctx, &s3.PutBucketEncryptionInput{
			Bucket: aws.String(bucket),
			ServerSideEncryptionConfiguration: &s3types.ServerSideEncryptionConfiguration{
				Rules: []s3types.ServerSideEncryptionRule{
					{
						ApplyServerSideEncryptionByDefault: &s3types.ServerSideEncryptionByDefault{
							SSEAlgorithm: s3types.ServerSideEncryptionAes256,
						},
					},
				},
			},
		})
		if err != nil {
			return c.wrapErr("applying AES256 encryption to bucket "+bucket, err)
		}
	}
	return nil
}

// CheckBucketAccess probes the bucket ACL and reports whether the current
// credentials hold the expected grant, mirroring Python's
// AWSBoto.check_bucket_access: the first grant's Permission must be
// FULL_CONTROL for readwrite access, or READ for read access.
//
// A permission mismatch yields (false, nil); an API failure (no access at
// all, missing bucket, provider without ACL support) yields (false, err).
// Python collapses both cases to False — callers that only need the boolean
// can ignore the error.
func (c *Client) CheckBucketAccess(ctx context.Context, bucket string, readwrite bool) (bool, error) {
	if bucket == "" {
		return false, errors.New("awsx: no bucket name provided")
	}
	out, err := c.s3.GetBucketAcl(ctx, &s3.GetBucketAclInput{Bucket: aws.String(bucket)})
	if err != nil {
		return false, c.wrapErr("checking access to bucket "+bucket, err)
	}
	if len(out.Grants) == 0 {
		return false, nil
	}
	permission := out.Grants[0].Permission
	if readwrite {
		return permission == s3types.PermissionFullControl, nil
	}
	return permission == s3types.PermissionRead, nil
}
