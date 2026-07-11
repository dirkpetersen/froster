package logging

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLogTeesToFileOnlyInDebug(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sub", "froster.log")

	l := New(path, false)
	l.Log("not recorded")
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("log file should not exist without debug, stat err = %v", err)
	}

	l = New(path, true)
	l.Log("hello", "world")
	l.Logf("count=%d", 42)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	got := string(data)
	if !strings.Contains(got, "hello world\n") || !strings.Contains(got, "count=42\n") {
		t.Errorf("log file content = %q", got)
	}
}

func TestDebugfSuppressedWithoutDebug(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "froster.log")
	l := New(path, false)
	l.Debugf("secret %s", "stuff")
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("debug output must be suppressed, stat err = %v", err)
	}
}

func TestPrintLogFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "froster.log")

	var buf bytes.Buffer
	if err := PrintLogFile(&buf, path); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(buf.String(), "No log file found") {
		t.Errorf("missing-file notice not printed, got %q", buf.String())
	}

	if err := os.WriteFile(path, []byte("line1\nline2\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	buf.Reset()
	if err := PrintLogFile(&buf, path); err != nil {
		t.Fatal(err)
	}
	if buf.String() != "line1\nline2\n" {
		t.Errorf("PrintLogFile = %q", buf.String())
	}
}
