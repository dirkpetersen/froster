package awsx

import (
	"context"
	"errors"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

// Object describes one S3 object as reported by ListObjectsV2.
type Object struct {
	Key  string
	Size int64
	// StorageClass as reported by the listing ("STANDARD", "GLACIER",
	// "DEEP_ARCHIVE", ...). Unlike HeadObject, ListObjectsV2 reports
	// STANDARD explicitly.
	StorageClass string
}

// ListObjects returns all objects under the given prefix, following
// pagination (Python: paginator over list_objects_v2). An empty prefix
// lists the whole bucket.
func (c *Client) ListObjects(ctx context.Context, bucket, prefix string) ([]Object, error) {
	if bucket == "" {
		return nil, errors.New("awsx: no bucket name provided")
	}

	input := &s3.ListObjectsV2Input{Bucket: aws.String(bucket)}
	if prefix != "" {
		input.Prefix = aws.String(prefix)
	}

	var objects []Object
	paginator := s3.NewListObjectsV2Paginator(c.s3, input)
	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)
		if err != nil {
			return nil, c.wrapErr("listing objects in bucket "+bucket, err)
		}
		for _, obj := range page.Contents {
			objects = append(objects, Object{
				Key:          aws.ToString(obj.Key),
				Size:         aws.ToInt64(obj.Size),
				StorageClass: string(obj.StorageClass),
			})
		}
	}
	return objects, nil
}
