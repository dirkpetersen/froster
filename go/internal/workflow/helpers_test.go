package workflow

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
	"github.com/dirkpetersen/froster/go/internal/logging"
	"github.com/dirkpetersen/froster/go/internal/transfer"
)

// captureStdout runs fn while os.Stdout is redirected and returns
// everything printed (the logging package writes straight to stdout, as
// Python's log() does).
var stdoutMu sync.Mutex

func captureStdout(t *testing.T, fn func()) string {
	t.Helper()
	stdoutMu.Lock()
	defer stdoutMu.Unlock()

	old := os.Stdout
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	os.Stdout = w
	done := make(chan string)
	go func() {
		var buf bytes.Buffer
		io.Copy(&buf, r) //nolint:errcheck
		done <- buf.String()
	}()
	defer func() {
		os.Stdout = old
	}()
	fn()
	w.Close()
	os.Stdout = old
	return <-done
}

// copyCall records one Engine.Copy invocation.
type copyCall struct {
	Src, Dst string
	Opts     transfer.CopyOptions
}

// checkCall records one Engine.CheckMD5 invocation.
type checkCall struct {
	MD5File, Remote string
	Opts            transfer.CheckOptions
}

// fakeEngine is an in-memory transfer.Engine for workflow tests.
type fakeEngine struct {
	mu     sync.Mutex
	Copies []copyCall
	Checks []checkCall

	// CopyErr / CheckErr make the corresponding operation fail when they
	// return a non-nil error.
	CopyErr  func(src, dst string) error
	CheckErr func(md5file, remote string) error
	// OnCopy can materialize files (e.g. simulate a download).
	OnCopy func(src, dst string, opts transfer.CopyOptions) error
}

var _ transfer.Engine = (*fakeEngine)(nil)

func (f *fakeEngine) Copy(_ context.Context, src, dst string, opts transfer.CopyOptions) (transfer.Stats, error) {
	f.mu.Lock()
	f.Copies = append(f.Copies, copyCall{Src: src, Dst: dst, Opts: opts})
	f.mu.Unlock()
	if f.CopyErr != nil {
		if err := f.CopyErr(src, dst); err != nil {
			return transfer.Stats{}, err
		}
	}
	if f.OnCopy != nil {
		return transfer.Stats{}, f.OnCopy(src, dst, opts)
	}
	return transfer.Stats{}, nil
}

func (f *fakeEngine) CheckMD5(_ context.Context, md5file, remote string, opts transfer.CheckOptions) error {
	f.mu.Lock()
	f.Checks = append(f.Checks, checkCall{MD5File: md5file, Remote: remote, Opts: opts})
	f.mu.Unlock()
	if f.CheckErr != nil {
		return f.CheckErr(md5file, remote)
	}
	return nil
}

func (f *fakeEngine) Version() string { return "fake" }

// fixedNow is the injectable clock used in golden tests.
var fixedNow = time.Date(2026, 7, 10, 23, 40, 25, 780537000, time.Local)

// newTestWorkflow builds a Workflow around a fake engine and a temp DB.
func newTestWorkflow(t *testing.T) (*Workflow, *fakeEngine) {
	t.Helper()
	engine := &fakeEngine{}
	db, err := archivedb.Load(filepath.Join(t.TempDir(), "froster-archives.json"))
	if err != nil {
		t.Fatal(err)
	}
	w := &Workflow{
		Log:          logging.New("", false),
		Stderr:       io.Discard,
		Engine:       engine,
		DB:           db,
		Provider:     "Minio",
		Profile:      "profile minio",
		Credentials:  "minio",
		Endpoint:     "http://localhost:9201",
		Bucket:       "froster-golden",
		ArchiveDir:   "froster",
		StorageClass: "STANDARD",
		Email:        "golden@example.com",
		User:         "dp",
		Cores:        4,
		Now:          func() time.Time { return fixedNow },
	}
	return w, engine
}

// writeFile creates a file with content, creating parents as needed.
func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

// writeBytes creates a file of the given size filled with a pattern,
// creating parents as needed.
func writeBytes(t *testing.T, path string, size int) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	buf := make([]byte, size)
	for i := range buf {
		buf[i] = byte('a' + i%26)
	}
	if err := os.WriteFile(path, buf, 0o644); err != nil {
		t.Fatal(err)
	}
}

// mustNotExist fails when path exists.
func mustNotExist(t *testing.T, path string) {
	t.Helper()
	if _, err := os.Lstat(path); err == nil {
		t.Errorf("%s still exists", path)
	}
}

// mustExist fails when path does not exist.
func mustExist(t *testing.T, path string) {
	t.Helper()
	if _, err := os.Lstat(path); err != nil {
		t.Errorf("%s missing: %v", path, err)
	}
}

// upsertEntry stores an entry in the test DB.
func upsertEntry(t *testing.T, w *Workflow, e *archivedb.Entry) {
	t.Helper()
	if err := w.DB.Upsert(e); err != nil {
		t.Fatal(err)
	}
}

// goldenEntry returns an archive entry shaped like the golden fixture,
// with the local folder replaced.
func goldenEntry(localFolder string) *archivedb.Entry {
	return &archivedb.Entry{
		LocalFolder:      localFolder,
		ArchiveFolder:    ":s3:froster-golden/froster" + localFolder,
		S3StorageClass:   "STANDARD",
		Profile:          "minio",
		Provider:         "Minio",
		Endpoint:         "http://localhost:9201",
		ArchiveMode:      archivedb.ModeSingle,
		Timestamp:        "2026-07-10T23:40:24.832029",
		TimestampArchive: "2026-07-10T23:40:24.832029",
		User:             "dp",
	}
}

// readLines splits a file into lines, dropping a trailing empty line.
func readLines(t *testing.T, path string) []string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(string(data), "\n")
	if len(lines) > 0 && lines[len(lines)-1] == "" {
		lines = lines[:len(lines)-1]
	}
	return lines
}

var _ = fmt.Sprintf
