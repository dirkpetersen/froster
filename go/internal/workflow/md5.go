package workflow

import (
	"bufio"
	"crypto/md5" //nolint:gosec // rclone/S3 verification is md5-based by design
	"encoding/hex"
	"io"
	"os"
	"path/filepath"
	"sync"
)

// genMD5Sums reproduces Archiver._gen_md5sums (spec §1.6): it writes
// <dir>/<hashFileName> with one "<md5><space><space><name>" line per
// top-level file, hashing in parallel with max(4, cores) workers (line
// order is completion order, i.e. unordered). Excluded from hashing: the
// hash file itself, Where-did-the-files-go.txt, .froster.md5sum and
// .froster-restored.md5sum — so Froster.smallfiles.tar and
// Froster.allfiles.csv ARE hashed. Broken symlinks are skipped; good
// symlinks are hashed through the link.
//
// A resulting empty hash file is deleted and reported as failure
// (returning errEmptyMD5), matching Python's `return False`.
func (w *Workflow) genMD5Sums(dir, hashFileName string) error {
	files, err := topFiles(dir)
	if err != nil {
		return err
	}

	hashPath := filepath.Join(dir, hashFileName)
	out, err := os.Create(hashPath)
	if err != nil {
		return err
	}

	var candidates []string
	for _, name := range files {
		if name == hashFileName ||
			name == WhereDidTheFilesGoFileName ||
			name == MD5SumFileName ||
			name == MD5SumRestoredFileName {
			continue
		}
		// Python: os.path.isfile(file_path) — follows symlinks, so broken
		// symlinks are skipped and good ones hashed through the target.
		if info, err := os.Stat(filepath.Join(dir, name)); err != nil || !info.Mode().IsRegular() {
			continue
		}
		candidates = append(candidates, name)
	}

	workers := w.Cores
	if workers < 4 {
		workers = 4
	}

	type result struct {
		name string
		md5  string
		err  error
	}
	jobs := make(chan string)
	results := make(chan result)
	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for name := range jobs {
				sum, err := md5File(filepath.Join(dir, name))
				results <- result{name: name, md5: sum, err: err}
			}
		}()
	}
	go func() {
		for _, name := range candidates {
			jobs <- name
		}
		close(jobs)
		wg.Wait()
		close(results)
	}()

	bw := bufio.NewWriter(out)
	var firstErr error
	for r := range results {
		if r.err != nil {
			if firstErr == nil {
				firstErr = r.err
			}
			continue
		}
		// md5sum-compatible: hash, two spaces, bare file name.
		if _, err := bw.WriteString(r.md5 + "  " + r.name + "\n"); err != nil && firstErr == nil {
			firstErr = err
		}
	}
	if err := bw.Flush(); err != nil && firstErr == nil {
		firstErr = err
	}
	if err := out.Close(); err != nil && firstErr == nil {
		firstErr = err
	}
	if firstErr != nil {
		return firstErr
	}

	info, err := os.Stat(hashPath)
	if err != nil {
		return err
	}
	if info.Size() == 0 {
		os.Remove(hashPath)
		return errEmptyMD5
	}
	return nil
}

// errEmptyMD5 is returned when no file could be hashed (empty hash file,
// deleted again) — Python's silent `return False` from _gen_md5sums.
var errEmptyMD5 = errorString("no files to checksum (empty md5 file removed)")

type errorString string

func (e errorString) Error() string { return string(e) }

// md5File hashes one file. Python hashes files > 100 MiB in parallel
// 100 MiB chunks purely as a read-ahead optimization (the digest is updated
// sequentially, so the result is identical); a straight sequential read is
// equivalent here.
func md5File(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := md5.New() //nolint:gosec
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
