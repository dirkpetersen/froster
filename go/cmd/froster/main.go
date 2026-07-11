// froster is a user-friendly archiving tool for teams that move data
// between high-cost POSIX file systems and low-cost S3-like object
// storage systems. This is the Go implementation (see GO-ARCHITECTURE.md
// at the repository root); it is a drop-in replacement for the Python
// froster CLI.
package main

import (
	"fmt"
	"os"

	"github.com/dirkpetersen/froster/go/internal/cli"
)

func main() {
	// NotImplementedApp is the placeholder until the workflow packages are
	// wired in; the full CLI surface (flags, help, aliases) already works.
	err := cli.Execute(cli.NotImplementedApp{})
	if err != nil && !cli.Silent(err) {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
	}
	os.Exit(cli.ExitCode(err))
}
