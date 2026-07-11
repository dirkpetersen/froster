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
	if err := cli.Execute(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}
