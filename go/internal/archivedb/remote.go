package archivedb

import (
	"fmt"
	"strings"
)

// Remote is a parsed rclone-style archive destination as stored in the
// archive_folder key, e.g. ":s3:froster-dipeit/froster/home/dp/data".
// Bucket is the S3 bucket name; Prefix is everything after the first slash
// (no leading slash, no ":s3:" tag).
type Remote struct {
	Bucket string
	Prefix string
}

// remoteTag is the rclone on-the-fly S3 backend prefix used by Python
// (f':s3:{bucket}' in Archiver.archive).
const remoteTag = ":s3:"

// ParseRemote splits an archive_folder value into bucket and prefix using
// the same string operations as Python's archive_get_bucket_info:
// split on the first "/", then strip ":s3:" from the bucket part.
func ParseRemote(archiveFolder string) (Remote, error) {
	bucket, prefix, found := strings.Cut(archiveFolder, "/")
	if !found {
		return Remote{}, fmt.Errorf("archivedb: invalid archive_folder %q: no bucket/prefix separator", archiveFolder)
	}
	// Python uses bucket.replace(':s3:', ''), which removes the tag
	// wherever it appears; mirror that exactly.
	bucket = strings.ReplaceAll(bucket, remoteTag, "")
	return Remote{Bucket: bucket, Prefix: prefix}, nil
}

// String renders the remote in the exact format Python constructs:
// ":s3:" + bucket + "/" + prefix.
func (r Remote) String() string {
	return remoteTag + r.Bucket + "/" + r.Prefix
}

// BucketInfo is the result of resolving an entry for a specific folder,
// mirroring Python's Archiver.archive_get_bucket_info return values
// (bucket, prefix, is_recursive, is_glacier, profile, user).
type BucketInfo struct {
	Bucket    string
	Prefix    string // prefix for the requested folder, always "/"-terminated
	Recursive bool
	Glacier   bool
	Profile   string
	User      string
}

// BucketInfo resolves the S3 location of folder within this entry, exactly
// as Python's archive_get_bucket_info does. folder may be the entry's own
// local_folder or (for a Recursive entry) a subfolder of it; the prefix is
// rewritten so that it points at the requested folder:
//
//	bucket, prefix = archive_folder.split('/', 1)
//	bucket = bucket.replace(':s3:', '')
//	prefix = prefix.replace(local_folder, '') + folder + '/'
func (e *Entry) BucketInfo(folder string) (BucketInfo, error) {
	r, err := ParseRemote(e.ArchiveFolder)
	if err != nil {
		return BucketInfo{}, err
	}
	// Python str.replace removes every occurrence; mirror it.
	prefix := strings.ReplaceAll(r.Prefix, e.LocalFolder, "") + folder + "/"
	return BucketInfo{
		Bucket:    r.Bucket,
		Prefix:    prefix,
		Recursive: e.IsRecursive(),
		Glacier:   e.IsGlacier(),
		Profile:   e.Profile,
		User:      e.User,
	}, nil
}
