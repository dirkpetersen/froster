package transfer

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"time"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/accounting"
	"github.com/rclone/rclone/fs/config"
	"github.com/rclone/rclone/fs/filter"
	"github.com/rclone/rclone/fs/hash"
	"github.com/rclone/rclone/fs/operations"
	rsync "github.com/rclone/rclone/fs/sync"

	// Link in only the backends froster supports. AWS, GCS (S3 interop),
	// Wasabi, IDrive, Ceph and Minio are all S3-compatible providers of
	// the s3 backend. Importing backend/all instead would roughly double
	// the binary size.
	_ "github.com/rclone/rclone/backend/local"
	_ "github.com/rclone/rclone/backend/s3"
)

var initOnce sync.Once

// Initialize prepares the embedded rclone library for in-process use. It is
// idempotent and called automatically by New; internal/mount calls it too.
//
// Crucially it forces rclone's config to be memory-only so that the user's
// ~/.config/rclone/rclone.conf is never read and nothing is ever written:
// all remote parameters arrive via connection strings (see ConnString).
func Initialize() {
	initOnce.Do(func() {
		// Empty path selects rclone's in-memory config storage.
		if err := config.SetConfigPath(""); err != nil {
			fs.Errorf(nil, "transfer: failed to set memory-only rclone config: %v", err)
		}
		// Start the accounting machinery (token bucket, global stats).
		accounting.Start(context.Background())
	})
}

// copySeq disambiguates the per-operation accounting stats groups.
var copySeq atomic.Int64

// Rclone is the production Engine backed by rclone's fs packages running
// in-process (direct fs-API integration, GO-ARCHITECTURE.md §6.2).
type Rclone struct {
	cfg S3Config
}

var _ Engine = (*Rclone)(nil)

// New returns an Engine for the given S3 profile. The zero S3Config is
// valid for purely local operations (local→local copies, local checks).
func New(cfg S3Config) *Rclone {
	Initialize()
	return &Rclone{cfg: cfg}
}

// Version returns the embedded rclone library version, e.g. "v1.74.4".
// It replaces shelling out to `rclone version`.
func (r *Rclone) Version() string {
	return fs.Version
}

// Copy implements Engine.Copy using fs/sync.CopyDir (or operations.CopyFile
// for a single-file source), the in-process equivalent of
// `rclone copy src dst -vvv [--s3-no-check-bucket]`.
func (r *Rclone) Copy(ctx context.Context, src, dst string, opts CopyOptions) (Stats, error) {
	ctx, ci := fs.AddConfig(ctx)
	if opts.Transfers > 0 {
		ci.Transfers = opts.Transfers
	}
	if opts.Checkers > 0 {
		ci.Checkers = opts.Checkers
	}
	if opts.MaxDepth > 0 {
		ci.MaxDepth = opts.MaxDepth
	}
	if opts.MultiThreadStreams > 0 {
		ci.MultiThreadStreams = opts.MultiThreadStreams
		ci.MultiThreadSet = true
	}
	if len(opts.Exclude) > 0 {
		var err error
		ctx, err = withExcludes(ctx, opts.Exclude)
		if err != nil {
			return Stats{}, err
		}
	}

	// Give this operation its own stats group so concurrent operations
	// (and prior runs) don't pollute each other's numbers.
	ctx = accounting.WithStatsGroup(ctx, fmt.Sprintf("froster-copy-%d", copySeq.Add(1)))
	stats := accounting.Stats(ctx)
	start := time.Now()

	if opts.Progress != nil {
		interval := opts.ProgressInterval
		if interval <= 0 {
			interval = time.Second
		}
		done := make(chan struct{})
		defer close(done)
		go func() {
			ticker := time.NewTicker(interval)
			defer ticker.Stop()
			for {
				select {
				case <-done:
					return
				case <-ticker.C:
					opts.Progress(snapshot(stats, start))
				}
			}
		}()
	}

	cfg := r.cfg
	if opts.StorageClass != "" {
		cfg.StorageClass = opts.StorageClass
	}
	if opts.NoCheckBucket {
		cfg.NoCheckBucket = true
	}

	err := r.copy(ctx, src, dst, cfg, opts.Links)

	final := snapshot(stats, start)
	if opts.Progress != nil {
		opts.Progress(final)
	}
	return final, err
}

func (r *Rclone) copy(ctx context.Context, src, dst string, cfg S3Config, links bool) error {
	fdst, err := newFs(ctx, dst, cfg, links)
	if err != nil {
		return fmt.Errorf("destination %q: %w", dst, err)
	}

	// A local regular file is copied as a single file into dst,
	// matching `rclone copy /path/file remote:` semantics.
	if !IsS3Remote(src) {
		if fi, statErr := os.Stat(src); statErr == nil && fi.Mode().IsRegular() {
			dir, name := filepath.Split(src)
			fsrc, err := newFs(ctx, dir, cfg, links)
			if err != nil {
				return fmt.Errorf("source %q: %w", src, err)
			}
			return operations.CopyFile(ctx, fdst, fsrc, name, name)
		}
	}

	fsrc, err := newFs(ctx, src, cfg, links)
	if err != nil {
		return fmt.Errorf("source %q: %w", src, err)
	}
	// false: like `rclone copy` without --create-empty-src-dirs.
	return rsync.CopyDir(ctx, fdst, fsrc, false)
}

// withExcludes derives a context whose filter config excludes the given
// glob patterns, the in-process equivalent of repeated --exclude flags.
func withExcludes(ctx context.Context, patterns []string) (context.Context, error) {
	f, err := filter.NewFilter(nil)
	if err != nil {
		return ctx, err
	}
	for _, pattern := range patterns {
		if err := f.Add(false, pattern); err != nil {
			return ctx, fmt.Errorf("exclude pattern %q: %w", pattern, err)
		}
	}
	return filter.ReplaceConfig(ctx, f), nil
}

// CheckMD5 implements Engine.CheckMD5 via operations.CheckSum, the exact
// code path behind `rclone checksum md5 md5sumFile remote:`.
func (r *Rclone) CheckMD5(ctx context.Context, md5sumFile, remote string, opts CheckOptions) error {
	ctx, ci := fs.AddConfig(ctx)
	if opts.Checkers > 0 {
		ci.Checkers = opts.Checkers
	}
	if opts.MaxDepth > 0 {
		ci.MaxDepth = opts.MaxDepth
	}
	ctx = accounting.WithStatsGroup(ctx, fmt.Sprintf("froster-check-%d", copySeq.Add(1)))

	dir, name := filepath.Split(filepath.Clean(md5sumFile))
	if dir == "" {
		dir = "."
	}
	fsum, err := newFs(ctx, dir, r.cfg, false)
	if err != nil {
		return fmt.Errorf("md5sum file directory %q: %w", dir, err)
	}
	frem, err := newFs(ctx, remote, r.cfg, false)
	if err != nil {
		return fmt.Errorf("remote %q: %w", remote, err)
	}

	// A non-nil CheckOpt keeps CheckSum from writing per-file result
	// lines to stdout; failures are reported through the returned error
	// (and rclone's logger).
	return operations.CheckSum(ctx, frem, fsum, name, hash.MD5, &operations.CheckOpt{}, false)
}

// newFs builds an fs.Fs for a froster remote or local path, injecting cfg
// (and the local backend's links option) via an in-memory connection string.
func newFs(ctx context.Context, remote string, cfg S3Config, links bool) (fs.Fs, error) {
	target, err := ConnString(remote, cfg)
	if err != nil {
		return nil, err
	}
	if links && !IsS3Remote(remote) {
		// Equivalent of --links for the local backend: symlinks are
		// translated to/from ".rclonelink" objects.
		target = ":local,links=true:" + target
	}
	return fs.NewFs(ctx, target)
}

// snapshot converts rclone accounting into a transfer.Stats.
func snapshot(s *accounting.StatsInfo, start time.Time) Stats {
	elapsed := time.Since(start)
	st := Stats{
		Bytes:     s.GetBytes(),
		Transfers: s.GetTransfers(),
		Checks:    s.GetChecks(),
		Errors:    s.GetErrors(),
		Elapsed:   elapsed,
	}
	if err := s.GetLastError(); err != nil {
		st.LastError = err.Error()
	}
	if secs := elapsed.Seconds(); secs > 0 {
		st.BytesPerSecond = float64(st.Bytes) / secs
	}
	return st
}
