package awsx

import (
	"context"
	"errors"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	s3types "github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/aws/smithy-go"
)

// Restore retrieval tiers accepted by TriggerGlacierRestore (froster's
// --retrieve-opt values, passed straight through as boto3 did).
const (
	TierBulk      = "Bulk"
	TierStandard  = "Standard"
	TierExpedited = "Expedited"
)

// restoreState is the classification of a single object during a
// HeadObject sweep, following the exact decision order of Python's
// AWSBoto.glacier_restore.
type restoreState int

const (
	// stateStandard: HeadObject returned no storage class header, i.e. the
	// object is STANDARD. Python skips these entirely (they appear in no
	// result list), because boto3 omits the StorageClass key for STANDARD.
	stateStandard restoreState = iota
	// stateInProgress: x-amz-restore contains ongoing-request="true".
	stateInProgress
	// stateRestored: x-amz-restore contains ongoing-request="false".
	stateRestored
	// stateNotGlacier: a non-STANDARD class outside GLACIER/DEEP_ARCHIVE
	// (e.g. STANDARD_IA, INTELLIGENT_TIERING, GLACIER_IR).
	stateNotGlacier
	// stateCold: GLACIER or DEEP_ARCHIVE with no restore triggered.
	stateCold
)

// parseRestoreHeader interprets the x-amz-restore header value (SDK field
// HeadObjectOutput.Restore), e.g.
//
//	ongoing-request="true"
//	ongoing-request="false", expiry-date="Fri, 21 Dec 2012 00:00:00 GMT"
//
// It uses the same substring matching as the Python implementation.
// present is false when the header is absent or matches neither form.
func parseRestoreHeader(restore string) (ongoing bool, present bool) {
	if strings.Contains(restore, `ongoing-request="true"`) {
		return true, true
	}
	if strings.Contains(restore, `ongoing-request="false"`) {
		return false, true
	}
	return false, false
}

// classifyRestore reproduces the per-object decision order of Python's
// glacier_restore: STANDARD short-circuit first, then the restore header,
// then the storage class.
func classifyRestore(storageClass, restoreHeader string) restoreState {
	if storageClass == "" {
		return stateStandard
	}
	if ongoing, present := parseRestoreHeader(restoreHeader); present {
		if ongoing {
			return stateInProgress
		}
		return stateRestored
	}
	if !GlacierStorageClasses[storageClass] {
		return stateNotGlacier
	}
	return stateCold
}

// RestoreResult reports the outcome of TriggerGlacierRestore, mirroring the
// five key lists returned by Python's glacier_restore.
type RestoreResult struct {
	// Triggered: cold objects for which a restore was requested now.
	Triggered []string
	// InProgress: objects whose Glacier retrieval is still ongoing
	// (including objects that raced into RestoreAlreadyInProgress).
	InProgress []string
	// Restored: objects already retrieved and readable.
	Restored []string
	// NotGlacier: objects in a non-STANDARD, non-Glacier class. As in
	// Python, Froster.allfiles.csv is silently excluded from this list.
	NotGlacier []string
	// NotSupported: DEEP_ARCHIVE objects when Expedited retrieval was
	// requested (Expedited is not available for DEEP_ARCHIVE).
	NotSupported []string
}

// RestoreStatus reports the outcome of a status-only HeadObject sweep.
type RestoreStatusResult struct {
	// NotGlacier: objects in a non-STANDARD, non-Glacier storage class
	// (Froster.allfiles.csv excluded, as in Python).
	NotGlacier []string
	// InProgress: restore ongoing (ongoing-request="true").
	InProgress []string
	// Restored: restore complete (ongoing-request="false").
	Restored []string
	// NotTriggered: cold GLACIER/DEEP_ARCHIVE objects with no restore
	// requested.
	NotTriggered []string
}

// sweepObject holds one object plus its HeadObject classification.
type sweepObject struct {
	key   string
	class string
	state restoreState
}

// sweepRestoreStates lists the objects directly under prefix (objects in
// deeper subfolders are skipped, exactly like Python's
// `if '/' in remaining_path: continue`) and classifies each via HeadObject.
func (c *Client) sweepRestoreStates(ctx context.Context, bucket, prefix string) ([]sweepObject, error) {
	if bucket == "" {
		return nil, errors.New("awsx: no bucket name provided")
	}

	input := &s3.ListObjectsV2Input{Bucket: aws.String(bucket)}
	if prefix != "" {
		input.Prefix = aws.String(prefix)
	}

	var result []sweepObject
	paginator := s3.NewListObjectsV2Paginator(c.s3, input)
	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)
		if err != nil {
			return nil, c.wrapErr("listing objects in bucket "+bucket, err)
		}
		for _, obj := range page.Contents {
			key := aws.ToString(obj.Key)

			// Skip objects in subfolders below the prefix.
			remaining := strings.TrimPrefix(key, prefix)
			if strings.Contains(remaining, "/") {
				continue
			}

			head, err := c.s3.HeadObject(ctx, &s3.HeadObjectInput{
				Bucket: aws.String(bucket),
				Key:    aws.String(key),
			})
			if err != nil {
				return nil, c.wrapErr("reading object status for "+key, err)
			}

			class := string(head.StorageClass)
			result = append(result, sweepObject{
				key:   key,
				class: class,
				state: classifyRestore(class, aws.ToString(head.Restore)),
			})
		}
	}
	return result, nil
}

// TriggerGlacierRestore requests Glacier retrieval for every cold object
// directly under prefix (Python: AWSBoto.glacier_restore). days is how long
// the restored copy stays available; tier is one of TierBulk, TierStandard,
// TierExpedited.
//
// Objects already restoring or restored are reported, not re-triggered. A
// RestoreAlreadyInProgress error from S3 (a race with another requester) is
// handled gracefully: the object is counted as InProgress.
func (c *Client) TriggerGlacierRestore(ctx context.Context, bucket, prefix string, days int32, tier string) (RestoreResult, error) {
	var res RestoreResult

	sweep, err := c.sweepRestoreStates(ctx, bucket, prefix)
	if err != nil {
		return res, err
	}

	for _, obj := range sweep {
		switch obj.state {
		case stateStandard:
			// STANDARD objects are skipped entirely (Python parity).
		case stateInProgress:
			res.InProgress = append(res.InProgress, obj.key)
		case stateRestored:
			res.Restored = append(res.Restored, obj.key)
		case stateNotGlacier:
			if !strings.HasSuffix(obj.key, "Froster.allfiles.csv") {
				res.NotGlacier = append(res.NotGlacier, obj.key)
			}
		case stateCold:
			if obj.class == "DEEP_ARCHIVE" && tier == TierExpedited {
				// Expedited retrieval is not available for DEEP_ARCHIVE.
				res.NotSupported = append(res.NotSupported, obj.key)
				continue
			}
			_, err := c.s3.RestoreObject(ctx, &s3.RestoreObjectInput{
				Bucket: aws.String(bucket),
				Key:    aws.String(obj.key),
				RestoreRequest: &s3types.RestoreRequest{
					Days: aws.Int32(days),
					GlacierJobParameters: &s3types.GlacierJobParameters{
						Tier: s3types.Tier(tier),
					},
				},
			})
			if err != nil {
				var apiErr smithy.APIError
				if errors.As(err, &apiErr) && apiErr.ErrorCode() == "RestoreAlreadyInProgress" {
					res.InProgress = append(res.InProgress, obj.key)
					continue
				}
				return res, c.wrapErr("restore request for "+obj.key, err)
			}
			res.Triggered = append(res.Triggered, obj.key)
		}
	}
	return res, nil
}

// RestoreStatus sweeps the objects directly under prefix with HeadObject
// and classifies each by parsing the Restore field, without triggering any
// retrieval. Use it to poll whether a previously requested Glacier restore
// has finished.
func (c *Client) RestoreStatus(ctx context.Context, bucket, prefix string) (RestoreStatusResult, error) {
	var res RestoreStatusResult

	sweep, err := c.sweepRestoreStates(ctx, bucket, prefix)
	if err != nil {
		return res, err
	}

	for _, obj := range sweep {
		switch obj.state {
		case stateStandard:
			// STANDARD objects are skipped entirely (Python parity).
		case stateInProgress:
			res.InProgress = append(res.InProgress, obj.key)
		case stateRestored:
			res.Restored = append(res.Restored, obj.key)
		case stateNotGlacier:
			if !strings.HasSuffix(obj.key, "Froster.allfiles.csv") {
				res.NotGlacier = append(res.NotGlacier, obj.key)
			}
		case stateCold:
			res.NotTriggered = append(res.NotTriggered, obj.key)
		}
	}
	return res, nil
}
