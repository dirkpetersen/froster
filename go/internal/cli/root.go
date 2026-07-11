// Package cli defines the froster command tree. The surface (subcommands,
// aliases, flags, defaults) must match the Python implementation exactly;
// the contract lives in go/testdata/cli-contract.json and is enforced by
// contract_test.go.
package cli

import (
	"fmt"

	"github.com/dirkpetersen/froster/go/internal/version"
)

// Execute runs the froster CLI. Placeholder until internal/cli is fully
// implemented (branch go-pkg/cli).
func Execute() error {
	fmt.Printf("froster %s (go, commit %s) — under construction\n", version.Version, version.Commit)
	return nil
}
