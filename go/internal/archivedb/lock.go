//go:build unix

package archivedb

import (
	"os"

	"golang.org/x/sys/unix"
)

// lockFile takes an exclusive advisory flock on path (creating it if
// needed) and returns a function that releases the lock. A sidecar lock
// file is used instead of locking froster-archives.json itself because the
// database file is replaced by rename on every write, which would leave
// waiters holding a lock on a dead inode.
//
// Python froster performs no locking at all, so this only serializes Go
// writers; the lock file is invisible to (and ignored by) Python clients.
func lockFile(path string) (func(), error) {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o644)
	if err != nil {
		return nil, err
	}
	if err := unix.Flock(int(f.Fd()), unix.LOCK_EX); err != nil {
		f.Close()
		return nil, err
	}
	return func() {
		// Closing the descriptor releases the flock; ignore errors on
		// release (nothing actionable for the caller).
		unix.Flock(int(f.Fd()), unix.LOCK_UN)
		f.Close()
	}, nil
}
