// Package transfer wraps rclone's Go packages (github.com/rclone/rclone,
// pinned per release) to provide the data-plane operations froster needs:
// copy to/from S3-compatible object storage, md5 checksum verification
// against a md5sum-format file, and the rclone version string. FUSE
// mounting lives in the sibling package internal/mount.
//
// Only the s3 and local rclone backends are linked in (see rclone.go);
// importing backend/all would roughly double the binary size.
//
// Remotes use froster's on-disk format ":s3:bucket/prefix" (as stored in
// froster-archives.json); anything else is treated as a local path.
// Credentials, endpoint, provider and region are injected in-process via
// rclone connection strings synthesized from S3Config — no rclone.conf is
// ever read from or written to disk, mirroring the Python implementation's
// environment-variable approach.
package transfer

import (
	"context"
	"time"
)

// S3Config carries the per-profile settings for an S3-compatible remote,
// mirroring the RCLONE_S3_* environment variables the Python implementation
// exports (see class Rclone in froster/froster.py).
type S3Config struct {
	// Provider is the rclone S3 provider name, e.g. "AWS", "Ceph",
	// "Minio", "Wasabi", "IDrive", "GCS", "Other".
	Provider string
	// Endpoint is the S3 endpoint URL. Empty for AWS.
	Endpoint string
	// Region is the S3 region; it is also used as the location
	// constraint, matching RCLONE_S3_LOCATION_CONSTRAINT in Python.
	Region string
	// AccessKeyID and SecretAccessKey are the static credentials.
	// Leave empty and set EnvAuth to use the standard AWS environment
	// variables / IAM metadata instead.
	AccessKeyID     string
	SecretAccessKey string
	// SessionToken is the optional STS session token.
	SessionToken string
	// EnvAuth makes rclone read credentials from the runtime
	// (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars, IAM role),
	// equivalent to RCLONE_S3_ENV_AUTH=true in the Python version.
	EnvAuth bool
	// StorageClass is the default storage class for uploads, e.g.
	// "DEEP_ARCHIVE", "GLACIER", "STANDARD_IA".
	StorageClass string
	// NoCheckBucket skips the bucket-exists check / implicit bucket
	// creation on upload. It is forced on when Provider is "Ceph",
	// matching the Python implementation's --s3-no-check-bucket flag.
	NoCheckBucket bool
}

// CopyOptions holds the per-call knobs for Engine.Copy. They cover the
// exact flag set the Python implementation passes to rclone copy:
// --max-depth 1, --links (uploads only), --transfers N, --checkers N,
// --multi-thread-streams 4, --exclude=…, and per-call storage class
// (Froster.allfiles.csv is uploaded separately with INTELLIGENT_TIERING
// while the main upload uses the profile's class).
type CopyOptions struct {
	// StorageClass overrides S3Config.StorageClass for this copy.
	StorageClass string
	// NoCheckBucket skips the bucket-exists check for this copy
	// (also implied by S3Config.NoCheckBucket or Provider "Ceph").
	NoCheckBucket bool
	// MaxDepth limits recursion depth like --max-depth; froster always
	// copies with MaxDepth 1 (recursion is per-directory calls).
	// 0 means unlimited.
	MaxDepth int
	// Links translates symlinks to .rclonelink objects like --links.
	// Froster sets it on uploads but not on restores.
	Links bool
	// Exclude lists filename patterns to skip, like repeated --exclude
	// flags (froster excludes .froster.md5sum, .froster-restored.md5sum,
	// Froster.allfiles.csv and Where-did-the-files-go.txt on upload).
	Exclude []string
	// Transfers is the number of concurrent file transfers
	// (froster: number of cores). 0 uses the rclone default (4).
	Transfers int
	// Checkers is the number of concurrent checkers (froster: cores/2).
	// 0 uses the rclone default (8).
	Checkers int
	// MultiThreadStreams is the number of streams per large-file
	// transfer, like --multi-thread-streams (froster: 4). 0 uses the
	// rclone default.
	MultiThreadStreams int
	// Progress, when non-nil, is called with a stats snapshot every
	// ProgressInterval while the copy runs, and once with the final
	// stats just before Copy returns.
	Progress func(Stats)
	// ProgressInterval defaults to 1s when Progress is set.
	ProgressInterval time.Duration
}

// CheckOptions holds the per-call knobs for Engine.CheckMD5; froster
// verifies with --max-depth 1 and --checkers max(1, cores/2).
type CheckOptions struct {
	// MaxDepth limits the remote listing depth like --max-depth.
	// 0 means unlimited.
	MaxDepth int
	// Checkers is the number of concurrent checkers. 0 uses the rclone
	// default (8).
	Checkers int
}

// Stats is a snapshot of rclone transfer accounting for one operation
// (the typed replacement for scraping `rclone -vvv` output).
type Stats struct {
	// Bytes transferred so far.
	Bytes int64
	// Transfers is the number of files fully transferred.
	Transfers int64
	// Checks is the number of files checked (checksum / size compares).
	Checks int64
	// Errors is the number of errors counted by rclone accounting.
	Errors int64
	// LastError is the text of the most recent error, if any.
	LastError string
	// Elapsed is the wall-clock time since the operation started.
	Elapsed time.Duration
	// BytesPerSecond is the average throughput over Elapsed.
	BytesPerSecond float64
}

// Engine is froster's transfer abstraction. The production implementation
// (New) drives rclone's fs packages in-process; the interface exists so the
// implementation could be swapped for librclone RPC (or a test fake)
// without touching workflow code — see GO-ARCHITECTURE.md §6.2.
type Engine interface {
	// Copy copies src to dst, either of which may be a local path or a
	// ":s3:bucket/prefix" remote. A local src that is a regular file is
	// copied as a single file; otherwise src is treated as a directory
	// tree, reproducing `rclone copy src dst` semantics (empty source
	// directories are not created on the destination).
	Copy(ctx context.Context, src, dst string, opts CopyOptions) (Stats, error)

	// CheckMD5 verifies every file listed in md5sumFile (md5sum -c
	// format: "<hex md5>  <relative path>" per line) against the files
	// under remote, reproducing `rclone checksum md5 md5sumFile remote:`
	// semantics: a hash mismatch, a listed file missing from the remote,
	// or a remote file missing from the list all make it return an
	// error describing the number of differences.
	CheckMD5(ctx context.Context, md5sumFile, remote string, opts CheckOptions) error

	// Version returns the embedded rclone library version, e.g. "v1.74.4".
	Version() string
}
