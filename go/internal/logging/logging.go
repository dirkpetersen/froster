// Package logging mirrors the Python froster logging behavior: user-facing
// output goes to stdout; when debug mode is active it is also appended to
// froster.log under the data directory, which `froster --log-print` dumps.
package logging

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"
)

// Logger writes user-facing output and optionally tees it to a log file.
type Logger struct {
	mu      sync.Mutex
	logPath string
	debug   bool
}

// New returns a Logger. logPath is the froster.log location (typically
// <data-dir>/froster.log); the file is only written when debug is true,
// matching the Python implementation (which gates on DEBUG=1).
func New(logPath string, debug bool) *Logger {
	return &Logger{logPath: logPath, debug: debug}
}

// Log prints to stdout and, in debug mode, appends the same line to the
// log file. Errors writing the log file are ignored (as in Python).
func (l *Logger) Log(a ...any) {
	fmt.Println(a...)
	l.tee(fmt.Sprintln(a...))
}

// Logf is Log with formatting.
func (l *Logger) Logf(format string, a ...any) {
	fmt.Printf(format+"\n", a...)
	l.tee(fmt.Sprintf(format+"\n", a...))
}

// Debugf prints only when debug mode is active (console and log file).
func (l *Logger) Debugf(format string, a ...any) {
	if !l.debug {
		return
	}
	l.Logf(format, a...)
}

func (l *Logger) tee(line string) {
	if !l.debug || l.logPath == "" {
		return
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	if err := os.MkdirAll(filepath.Dir(l.logPath), 0o775); err != nil {
		return
	}
	f, err := os.OpenFile(l.logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o664)
	if err != nil {
		return
	}
	defer f.Close()
	_, _ = f.WriteString(line)
}

// PrintLogFile copies the log file to w (the --log-print behavior).
// A missing log file is not an error; it prints a notice like Python does.
func PrintLogFile(w io.Writer, logPath string) error {
	f, err := os.Open(logPath)
	if os.IsNotExist(err) {
		fmt.Fprintf(w, "No log file found at %s (log entries are only written in --debug mode)\n", logPath)
		return nil
	}
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = io.Copy(w, f)
	return err
}
