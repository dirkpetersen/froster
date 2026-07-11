// Package version holds build-time version information, injected via
// -ldflags "-X github.com/dirkpetersen/froster/go/internal/version.Version=…".
package version

var (
	Version = "0.0.0-dev"
	Commit  = "unknown"
)
