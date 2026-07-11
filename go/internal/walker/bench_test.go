package walker

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

// genBenchTree builds a tree of roughly nDirs*filesPerDir files under dir.
// Files are empty: the walker's cost is readdir+lstat, not content I/O.
func genBenchTree(tb testing.TB, dir string, nDirs, filesPerDir int) {
	tb.Helper()
	for d := range nDirs {
		sub := filepath.Join(dir, fmt.Sprintf("d%03d", d/100), fmt.Sprintf("dir%05d", d))
		if err := os.MkdirAll(sub, 0o755); err != nil {
			tb.Fatal(err)
		}
		for f := range filesPerDir {
			if err := os.WriteFile(filepath.Join(sub, fmt.Sprintf("file%04d.dat", f)), nil, 0o644); err != nil {
				tb.Fatal(err)
			}
		}
	}
}

// BenchmarkWalk measures a full walk of a 2,000-dir / 50,000-file tree.
func BenchmarkWalk(b *testing.B) {
	root := b.TempDir()
	genBenchTree(b, root, 2000, 25)
	b.ResetTimer()
	for b.Loop() {
		if _, err := Walk(root, io.Discard, Options{NoSnap: true, OneFS: true, Header: true}); err != nil {
			b.Fatal(err)
		}
	}
}

// TestBenchmarkVsCPwalk compares wall-clock time against the reference C
// binary on a >=200k-file tree. It is expensive, so it only runs when
// WALKER_BENCH_VS_C=1 is set, e.g.:
//
//	WALKER_BENCH_VS_C=1 go test -run TestBenchmarkVsCPwalk -v ./internal/walker
func TestBenchmarkVsCPwalk(t *testing.T) {
	if os.Getenv("WALKER_BENCH_VS_C") != "1" {
		t.Skip("set WALKER_BENCH_VS_C=1 to run the C pwalk wall-clock comparison")
	}
	bin := cPwalkBin(t)

	root, err := os.MkdirTemp("/tmp", "walker-bench-")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(root)

	const nDirs, filesPerDir = 4000, 50 // 200k files + 4k dirs
	t.Logf("generating %d files in %d dirs under %s ...", nDirs*filesPerDir, nDirs, root)
	genBenchTree(t, root, nDirs, filesPerDir)

	timeIt := func(name string, f func() error) time.Duration {
		best := time.Duration(1<<63 - 1)
		for range 3 {
			start := time.Now()
			if err := f(); err != nil {
				t.Fatalf("%s: %v", name, err)
			}
			if d := time.Since(start); d < best {
				best = d
			}
		}
		t.Logf("%-10s best of 3: %v", name, best)
		return best
	}

	null, err := os.OpenFile(os.DevNull, os.O_WRONLY, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer null.Close()

	// Warm the dentry/inode caches once so both contenders race warm.
	if _, err := Walk(root, io.Discard, Options{}); err != nil {
		t.Fatal(err)
	}

	cTime := timeIt("C pwalk", func() error {
		cmd := exec.Command(bin, "--NoSnap", "--one-file-system", "--header", root)
		cmd.Stdout = null
		cmd.Stderr = io.Discard
		return cmd.Run()
	})
	goTime := timeIt("Go walker", func() error {
		_, err := Walk(root, null, Options{NoSnap: true, OneFS: true, Header: true})
		return err
	})
	t.Logf("Go/C wall-clock ratio: %.2f (lower is better for Go)", float64(goTime)/float64(cTime))
}
