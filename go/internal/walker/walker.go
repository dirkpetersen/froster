// Package walker is a native Go replacement for the C pwalk binary
// (John F Dey's pwalk 3.0.0, filesystem-reporting-tools) that froster
// historically shelled out to as:
//
//	pwalk --NoSnap --one-file-system --header <folder>
//
// It walks a directory tree with a bounded goroutine worker pool and emits
// one CSV row per inode, byte-compatible with pwalk's output format, so the
// downstream consumers keep working unchanged:
//
//   - the "file row" filter `grep -v ",-1,0$"` (file rows end in ",-1,0"),
//   - the DuckDB hotspot query selecting directory rows with
//     `pw_fcount > -1 AND pw_dirsum > 0`.
//
// # CSV schema
//
// The header line (emitted when Options.Header is set) is byte-identical to
// C pwalk's:
//
//	inode,parent-inode,directory-depth,"filename","fileExtension",UID,GID,st_size,st_dev,st_blocks,st_nlink,"st_mode",st_atime,st_mtime,st_ctime,pw_fcount,pw_dirsum
//
// Row semantics (matching the C implementation exactly):
//
//   - filename is the full path (root path as given + "/" + components).
//   - The filename and fileExtension fields are always double-quoted; a
//     literal double quote is doubled (""), bytes < 32 (newline, tab, ...)
//     are stripped from the name and counted in Summary.BadNames, and all
//     other bytes -- including non-UTF-8 ones such as Latin-1 -- pass
//     through raw.
//   - st_mode is a quoted 7-digit zero-padded octal of the full mode
//     (e.g. "0100644" for a regular 0644 file, "0040755" for a directory).
//   - directory-depth: the walk root's own row has -1; entries directly in
//     the root have 0, entries one level down have 1, and so on. A
//     directory's own row uses the same depth as its sibling files.
//   - pw_fcount/pw_dirsum: file (non-directory) rows always carry -1 and 0.
//     Directory rows carry the count of directory entries ("." and ".."
//     excluded) and the sum of st_size of those entries (including
//     subdirectory inode sizes).
//
// # Quirks deliberately reproduced from C pwalk
//
//   - pw_fcount counts entries whose lstat failed; pw_dirsum does not
//     include them (the C code increments the counter before lstat).
//   - With Options.NoSnap, a ".snapshot" directory is not traversed and
//     gets no row, but it is still counted in the parent's pw_fcount and
//     its st_size still contributes to the parent's pw_dirsum.
//   - With Options.OneFS, an entry on a different device than the root is
//     counted in pw_fcount but contributes nothing to pw_dirsum, gets no
//     row, and is not traversed.
//   - An unreadable directory (opendir failure) gets no row at all -- not
//     even its own directory row -- but is counted in its parent's
//     pw_fcount/pw_dirsum. The error is counted in Summary.OpenErrors.
//   - Directory rows always have an empty fileExtension. (The C code
//     contains a backwards scan that is intended to extract one, but a
//     misplaced break makes it unconditionally discard the result; every
//     directory row it has ever produced has "".)
//   - A file's extension is the substring after the last '.' found at
//     byte offset >= 1 of the basename, so ".bashrc" has no extension
//     while "..leadingdots.txt" has "txt" and "a.tar.gz" has "gz".
//   - Hardlinks are not deduplicated: every link gets its own row with the
//     shared inode number.
//
// # Deliberate deviations from C pwalk
//
//   - A file whose basename ends in '.' (e.g. "trailing.") gets an empty
//     extension "". C pwalk prints uninitialized stack memory here (the
//     escape routine never writes to the output buffer for an empty
//     input), typically leaking the previous row's extension; the output
//     is nondeterministic garbage. Emitting "" is what the code intends
//     and is safe: froster never consumes fileExtension.
//   - pwalk's --exclude, --depth and --chown_* options are not
//     implemented; froster does not use them.
//   - pwalk attempts setuid(0) at startup; we never do.
//
// Row order is nondeterministic (parallel traversal), just like C pwalk.
// Consumers must not rely on row order beyond "header first".
package walker

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"runtime"
	"strings"
	"sync"

	"github.com/klauspost/compress/zstd"
	"golang.org/x/sys/unix"
)

// Header is the CSV header line emitted by C pwalk's --header flag,
// byte-identical including the trailing newline.
const Header = "inode,parent-inode,directory-depth,\"filename\",\"fileExtension\",UID,GID,st_size,st_dev,st_blocks,st_nlink,\"st_mode\",st_atime,st_mtime,st_ctime,pw_fcount,pw_dirsum\n"

// maxWorkers caps the default worker count, matching C pwalk's MAXTHRDS.
const maxWorkers = 32

// maxRecordedErrors caps the number of error strings kept in Summary.Errs.
const maxRecordedErrors = 100

// Options configures a walk.
type Options struct {
	// Workers is the number of concurrent directory workers.
	// If <= 0, min(32, NumCPU) is used.
	Workers int

	// NoSnap skips directories named ".snapshot" (pwalk --NoSnap).
	// See the package documentation for the exact rollup semantics.
	NoSnap bool

	// OneFS skips entries whose st_dev differs from the walk root's
	// (pwalk --one-file-system).
	OneFS bool

	// Header emits the CSV header line before any rows (pwalk --header).
	Header bool

	// Zstd compresses the output stream with zstandard, producing data
	// suitable for a .csv.zst file readable directly by DuckDB.
	Zstd bool
}

// Summary reports what a walk did. Errors are counted, never fatal.
type Summary struct {
	// DirRows and FileRows count emitted CSV rows by kind.
	DirRows  int64
	FileRows int64

	// LstatErrors counts directory entries that could not be lstat'd
	// (typically permission errors). Such entries get no row but are
	// counted in the parent's pw_fcount.
	LstatErrors int64

	// OpenErrors counts directories that could not be opened/read
	// (typically permission errors). Such directories get no row.
	OpenErrors int64

	// BadNames counts name fields from which control bytes (< 32) were
	// stripped, mirroring C pwalk's "Bad File" stderr diagnostics.
	BadNames int64

	// SkippedOtherFS counts entries skipped by Options.OneFS.
	SkippedOtherFS int64

	// RootDev is the st_dev of the walk root, for cross-filesystem
	// detection by callers.
	RootDev uint64

	// Errs holds the first maxRecordedErrors error messages encountered
	// (lstat and directory-read failures).
	Errs []string
}

// dirTask is one directory to process: its full path, the stat of the
// directory itself, its parent directory's inode, and the depth of the
// entries inside it (the root's entries have depth 0).
type dirTask struct {
	path      string
	depth     int64
	stat      unix.Stat_t
	parentIno uint64
}

// walkState is the shared state of one Walk invocation.
type walkState struct {
	opts    Options
	rootDev uint64
	queue   *taskQueue
	chunks  chan []byte

	mu  sync.Mutex // guards sum
	sum Summary
}

// Walk traverses root and writes pwalk-compatible CSV to out.
//
// Permission errors and other per-entry failures are counted in the
// returned Summary and never abort the walk. Walk returns a non-nil error
// only if the root itself cannot be lstat'd (matching C pwalk's only fatal
// error) or if writing to out fails.
//
// The root path is used verbatim as the filename prefix of every row,
// exactly as C pwalk uses its argument (froster passes an absolute path
// without a trailing slash).
func Walk(root string, out io.Writer, opts Options) (Summary, error) {
	var rootStat unix.Stat_t
	if err := unix.Lstat(root, &rootStat); err != nil {
		return Summary{}, fmt.Errorf("walker: lstat %q: %w", root, err)
	}

	workers := opts.Workers
	if workers <= 0 {
		workers = min(maxWorkers, runtime.NumCPU())
	}

	w := &walkState{
		opts:    opts,
		rootDev: rootStat.Dev,
		queue:   newTaskQueue(),
		chunks:  make(chan []byte, workers*2),
	}
	w.sum.RootDev = rootStat.Dev

	// Single writer goroutine: workers hand over whole per-directory
	// buffers, so there is no per-row locking anywhere.
	sink := out
	var zw *zstd.Encoder
	if opts.Zstd {
		var err error
		zw, err = zstd.NewWriter(out)
		if err != nil {
			return Summary{}, fmt.Errorf("walker: zstd writer: %w", err)
		}
		sink = zw
	}
	bw := bufio.NewWriterSize(sink, 1<<20)

	var writeErr error
	var writerWG sync.WaitGroup
	writerWG.Add(1)
	go func() {
		defer writerWG.Done()
		for chunk := range w.chunks {
			if writeErr != nil {
				continue // drain
			}
			if _, err := bw.Write(chunk); err != nil {
				writeErr = err
			}
		}
	}()

	if opts.Header {
		w.chunks <- []byte(Header)
	}

	w.queue.push(dirTask{
		path:      root,
		depth:     0,
		stat:      rootStat,
		parentIno: 0,
	})

	var workerWG sync.WaitGroup
	for range workers {
		workerWG.Add(1)
		go func() {
			defer workerWG.Done()
			for {
				task, ok := w.queue.pop()
				if !ok {
					return
				}
				w.processDir(task)
				w.queue.done()
			}
		}()
	}
	workerWG.Wait()
	close(w.chunks)
	writerWG.Wait()

	if writeErr == nil {
		writeErr = bw.Flush()
	}
	if zw != nil {
		if err := zw.Close(); err != nil && writeErr == nil {
			writeErr = err
		}
	}
	if writeErr != nil {
		return w.sum, fmt.Errorf("walker: writing output: %w", writeErr)
	}
	return w.sum, nil
}

// WalkToFile walks root and writes the CSV to outPath, creating or
// truncating the file. If outPath ends in ".zst", zstd compression is
// enabled regardless of opts.Zstd.
func WalkToFile(root, outPath string, opts Options) (Summary, error) {
	if strings.HasSuffix(outPath, ".zst") {
		opts.Zstd = true
	}
	f, err := os.Create(outPath)
	if err != nil {
		return Summary{}, fmt.Errorf("walker: create %q: %w", outPath, err)
	}
	sum, werr := Walk(root, f, opts)
	if cerr := f.Close(); cerr != nil && werr == nil {
		werr = cerr
	}
	return sum, werr
}

// recordError appends msg to the summary error list (capped) and lets the
// caller bump the matching counter.
func (w *walkState) recordError(msg string) {
	if len(w.sum.Errs) < maxRecordedErrors {
		w.sum.Errs = append(w.sum.Errs, msg)
	}
}

// processDir reads one directory, emits a row per entry that is not a
// traversable directory, enqueues subdirectories, and finally emits the
// directory's own rollup row. All rows for the directory are accumulated
// in a local buffer that is handed to the writer in large chunks.
func (w *walkState) processDir(task dirTask) {
	f, err := os.Open(task.path)
	if err != nil {
		w.mu.Lock()
		w.sum.OpenErrors++
		w.recordError(err.Error())
		w.mu.Unlock()
		return // like C pwalk: no row at all for an unreadable directory
	}
	names, rerr := f.Readdirnames(-1)
	f.Close()
	if rerr != nil {
		// Partial listings are still processed; count the failure.
		w.mu.Lock()
		w.sum.OpenErrors++
		w.recordError(fmt.Sprintf("reading %s: %v", task.path, rerr))
		w.mu.Unlock()
	}

	var (
		buf         []byte
		fcount      int64 // pw_fcount for this directory
		dirsum      int64 // pw_dirsum for this directory
		fileRows    int64
		lstatErrs   int64
		otherFS     int64
		badNames    int64
		deferredErr []string
		st          unix.Stat_t
	)

	for _, name := range names {
		fcount++
		full := task.path + "/" + name
		if err := unix.Lstat(full, &st); err != nil {
			// Counted in pw_fcount, absent from pw_dirsum -- the C
			// code increments its counter before calling lstat.
			lstatErrs++
			if len(deferredErr) < 8 {
				deferredErr = append(deferredErr, err.Error())
			}
			continue
		}
		if w.opts.OneFS && st.Dev != w.rootDev {
			otherFS++
			continue
		}
		dirsum += st.Size

		if st.Mode&unix.S_IFMT == unix.S_IFDIR {
			if w.opts.NoSnap && name == ".snapshot" {
				continue // counted in fcount and dirsum, but invisible
			}
			w.queue.push(dirTask{
				path:      full,
				depth:     task.depth + 1,
				stat:      st,
				parentIno: task.stat.Ino,
			})
			continue // the subdirectory emits its own row
		}

		// File (non-directory) row: pw_fcount=-1, pw_dirsum=0.
		var bad int
		buf, bad = appendRow(buf, rowData{
			ino:    st.Ino,
			pino:   task.stat.Ino,
			depth:  task.depth,
			name:   full,
			ext:    fileExt(name),
			stat:   &st,
			fcount: -1,
			dirsum: 0,
		})
		badNames += int64(bad)
		fileRows++

		if len(buf) >= 1<<16 {
			w.chunks <- buf
			buf = nil
		}
	}

	// The directory's own rollup row. Extension is always empty: the C
	// implementation never produces one for directories (see package doc).
	var bad int
	buf, bad = appendRow(buf, rowData{
		ino:    task.stat.Ino,
		pino:   task.parentIno,
		depth:  task.depth - 1,
		name:   task.path,
		ext:    "",
		stat:   &task.stat,
		fcount: fcount,
		dirsum: dirsum,
	})
	badNames += int64(bad)

	if len(buf) > 0 {
		w.chunks <- buf
	}

	w.mu.Lock()
	w.sum.DirRows++
	w.sum.FileRows += fileRows
	w.sum.LstatErrors += lstatErrs
	w.sum.SkippedOtherFS += otherFS
	w.sum.BadNames += badNames
	for _, e := range deferredErr {
		w.recordError(e)
	}
	w.mu.Unlock()
}

// fileExt extracts a file's extension using C pwalk's rules: the substring
// after the last '.' found at byte offset >= 1 of the basename. A leading
// dot alone (".bashrc") yields no extension. A basename ending in '.'
// yields "" (deviation: C pwalk emits uninitialized memory there).
func fileExt(basename string) string {
	dot := -1
	for i := 1; i < len(basename); i++ {
		if basename[i] == '.' {
			dot = i
		}
	}
	if dot < 0 || dot == len(basename)-1 {
		return ""
	}
	return basename[dot+1:]
}
