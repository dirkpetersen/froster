// froster is a user-friendly archiving tool for teams that move data
// between high-cost POSIX file systems and low-cost S3-like object
// storage systems. This is the Go implementation (see GO-ARCHITECTURE.md
// at the repository root); it is a drop-in replacement for the Python
// froster CLI.
package main

import (
	"fmt"
	"os"

	"github.com/dirkpetersen/froster/go/internal/app"
	"github.com/dirkpetersen/froster/go/internal/cli"
	"github.com/dirkpetersen/froster/go/internal/workflow"
)

func main() {
	// `froster mount` leaves a detached copy of this binary behind to
	// serve the FUSE mount (like Python's background rclone process);
	// that copy is diverted here before any CLI parsing.
	if workflow.IsMountDaemon() {
		if err := workflow.RunMountDaemon(); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		return
	}

	err := cli.Execute(app.New())
	if err != nil && !cli.Silent(err) {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
	}
	os.Exit(cli.ExitCode(err))
}
