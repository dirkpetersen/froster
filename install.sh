#!/bin/bash

# Installs froster: detects OS/architecture, downloads the matching release
# binary from GitHub, verifies its checksum, and installs it.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/dirkpetersen/froster/main/install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- --version 0.23.0
#   curl -fsSL .../install.sh | bash -s -- --dir /opt/froster/bin
#
# Install directory, highest priority first:
#   1. --dir/-d flag (or FROSTER_INSTALL_DIR env var)
#   2. /usr/local/bin, when run as root
#   3. ~/.local/bin, when it is already on PATH
#   4. ~/bin (created if necessary)

set -euo pipefail

REPO="dirkpetersen/froster"
VERSION="${FROSTER_VERSION:-}"
INSTALL_DIR="${FROSTER_INSTALL_DIR:-}"
VERBOSE=0

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Options:
  -v, --version VERSION   Install a specific version, e.g. 0.23.0 (default: latest release)
  -d, --dir DIR            Install directory (default: auto-detected; see script header)
      --verbose            Print extra diagnostic output
  -h, --help               Show this help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -v|--version) VERSION="$2"; shift 2 ;;
    -d|--dir) INSTALL_DIR="$2"; shift 2 ;;
    --verbose) VERBOSE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

vlog() { [ "$VERBOSE" = 1 ] && echo "$@" || true; }

if ! command -v curl >/dev/null 2>&1; then
  echo "Error: curl is required but was not found on PATH." >&2
  exit 1
fi

# --- detect OS/arch ---
case "$(uname -s)" in
  Linux) goos=linux ;;
  Darwin) goos=darwin ;;
  *) echo "Error: unsupported OS '$(uname -s)'. froster supports Linux and macOS." >&2; exit 1 ;;
esac

case "$(uname -m)" in
  x86_64|amd64) goarch=amd64 ;;
  arm64|aarch64) goarch=arm64 ;;
  *) echo "Error: unsupported architecture '$(uname -m)'. froster supports amd64 and arm64." >&2; exit 1 ;;
esac

echo "Detected platform: ${goos}-${goarch}"

# --- resolve version (GitHub's /releases/latest redirect, no API/JSON needed) ---
if [ -z "$VERSION" ]; then
  vlog "Resolving the latest release..."
  latest_url="$(curl -fsSLI -o /dev/null -w '%{url_effective}' "https://github.com/${REPO}/releases/latest")"
  VERSION="${latest_url##*/}"
  if [ -z "$VERSION" ] || [ "$VERSION" = "latest" ]; then
    echo "Error: could not determine the latest froster version from GitHub." >&2
    echo "Specify one explicitly: install.sh --version X.Y.Z" >&2
    exit 1
  fi
fi
VERSION="${VERSION#v}"
echo "Installing froster v${VERSION}"

# --- resolve install directory ---
path_contains() {
  case ":${PATH}:" in
    *":$1:"*) return 0 ;;
    *) return 1 ;;
  esac
}

if [ -z "$INSTALL_DIR" ]; then
  if [ "$(id -u)" -eq 0 ]; then
    INSTALL_DIR="/usr/local/bin"
  elif path_contains "${HOME}/.local/bin"; then
    INSTALL_DIR="${HOME}/.local/bin"
  else
    INSTALL_DIR="${HOME}/bin"
  fi
fi

mkdir -p "$INSTALL_DIR"
echo "Install directory: ${INSTALL_DIR}"

if ! path_contains "$INSTALL_DIR"; then
  echo ""
  echo "NOTE: ${INSTALL_DIR} is not in your PATH."
  echo "      Add it, e.g.: export PATH=\"${INSTALL_DIR}:\$PATH\""
  echo ""
fi

# --- download + verify ---
asset="froster-${VERSION}-${goos}-${goarch}"
base_url="https://github.com/${REPO}/releases/download/v${VERSION}"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

vlog "Downloading ${base_url}/${asset}"
curl_opts=(-fsSL)
[ "$VERBOSE" = 1 ] && curl_opts+=(-v)
curl "${curl_opts[@]}" "${base_url}/${asset}" -o "${tmpdir}/${asset}"

checksums="froster-${VERSION}-checksums.txt"
if curl -fsSL "${base_url}/${checksums}" -o "${tmpdir}/${checksums}" 2>/dev/null; then
  vlog "Verifying checksum..."
  expected="$(awk -v f="$asset" '{fn=$2; sub(/^\*/, "", fn); if (fn == f) print $1}' "${tmpdir}/${checksums}")"
  if [ -n "$expected" ]; then
    if command -v sha256sum >/dev/null 2>&1; then
      actual="$(sha256sum "${tmpdir}/${asset}" | awk '{print $1}')"
    else
      actual="$(shasum -a 256 "${tmpdir}/${asset}" | awk '{print $1}')"
    fi
    if [ "$expected" != "$actual" ]; then
      echo "Error: checksum mismatch for ${asset}" >&2
      echo "  expected: ${expected}" >&2
      echo "  actual:   ${actual}" >&2
      exit 1
    fi
    echo "Checksum verified."
  fi
else
  echo "NOTE: no checksums file found for this release; skipping verification."
fi

chmod +x "${tmpdir}/${asset}"
mv "${tmpdir}/${asset}" "${INSTALL_DIR}/froster"

echo ""
echo "froster installed to ${INSTALL_DIR}/froster"
"${INSTALL_DIR}/froster" --version
