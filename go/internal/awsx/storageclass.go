package awsx

import (
	"context"
	"errors"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	s3types "github.com/aws/aws-sdk-go-v2/service/s3/types"
)

// StorageClassChange summarizes a ChangeStorageClass run. It carries the
// same information as the Python tuple
// (success, total_objects, changed_objects, skipped_objects, total_size_bytes);
// success maps to the method's error return.
type StorageClassChange struct {
	TotalObjects   int
	ChangedObjects int
	SkippedObjects int
	TotalSizeBytes int64
}

// ErrGlacierSource is returned by ChangeStorageClass when the current
// storage class is GLACIER or DEEP_ARCHIVE: moving data out of a Glacier
// tier requires an explicit restore first (Python: the glacier_tiers guard
// in change_storage_class).
var ErrGlacierSource = errors.New(
	"cannot change storage class from a Glacier tier; restore the data first")

// ChangeStorageClass re-tiers every object under prefix to newClass by
// copying each object onto itself with MetadataDirective=COPY (Python:
// AWSBoto.change_storage_class).
//
// Rules, mirroring the Python implementation:
//   - The operation is refused outright (ErrGlacierSource) when
//     currentClass is GLACIER or DEEP_ARCHIVE.
//   - Froster metadata files (Froster.allfiles.csv, .froster.md5sum,
//     .froster-restored.md5sum) always stay in STANDARD and are skipped.
//   - Objects already in newClass are skipped.
//   - Objects that are individually in GLACIER/DEEP_ARCHIVE and have not
//     been restored cannot be copied and are skipped (S3 would reject the
//     CopyObject anyway; Python surfaces this as a per-object warning).
//   - Per-object copy failures are counted as skipped; the sweep continues.
//
// The returned StorageClassChange is valid even when err != nil is not —
// i.e. a nil error means the sweep completed (possibly with skips), like
// Python's success=True.
func (c *Client) ChangeStorageClass(ctx context.Context, bucket, prefix, newClass, currentClass string) (StorageClassChange, error) {
	var res StorageClassChange

	if bucket == "" {
		return res, errors.New("awsx: no bucket name provided")
	}
	if GlacierStorageClasses[currentClass] {
		return res, fmt.Errorf("awsx: %w (current class: %s)", ErrGlacierSource, currentClass)
	}

	input := &s3.ListObjectsV2Input{Bucket: aws.String(bucket)}
	if prefix != "" {
		input.Prefix = aws.String(prefix)
	}

	paginator := s3.NewListObjectsV2Paginator(c.s3, input)
	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)
		if err != nil {
			return res, c.wrapErr("listing objects in bucket "+bucket, err)
		}

		for _, obj := range page.Contents {
			key := aws.ToString(obj.Key)
			res.TotalObjects++
			res.TotalSizeBytes += aws.ToInt64(obj.Size)

			// Froster metadata files always stay in STANDARD.
			if StandardMetadataFiles[baseName(key)] {
				res.SkippedObjects++
				continue
			}

			objClass := string(obj.StorageClass)

			// Already in the target class: nothing to do.
			if objClass == newClass {
				res.SkippedObjects++
				continue
			}

			// Objects sitting in a Glacier tier can only be copied after a
			// restore; refuse un-restored ones instead of letting S3 fail.
			if GlacierStorageClasses[objClass] {
				restored, err := c.isRestored(ctx, bucket, key)
				if err != nil || !restored {
					res.SkippedObjects++
					continue
				}
			}

			_, err := c.s3.CopyObject(ctx, &s3.CopyObjectInput{
				Bucket:            aws.String(bucket),
				Key:               aws.String(key),
				CopySource:        aws.String(bucket + "/" + key),
				StorageClass:      s3types.StorageClass(newClass),
				MetadataDirective: s3types.MetadataDirectiveCopy,
			})
			if err != nil {
				// Python logs a warning and keeps going.
				res.SkippedObjects++
				continue
			}
			res.ChangedObjects++
		}
	}
	return res, nil
}

// isRestored reports whether a Glacier-tier object currently has a
// completed restore (x-amz-restore: ongoing-request="false").
func (c *Client) isRestored(ctx context.Context, bucket, key string) (bool, error) {
	head, err := c.s3.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return false, c.wrapErr("reading object status for "+key, err)
	}
	ongoing, present := parseRestoreHeader(aws.ToString(head.Restore))
	return present && !ongoing, nil
}
