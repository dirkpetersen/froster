#!/bin/bash

# Compatibility shim: the Python implementation of Froster (and its
# installer) moved to the 'python-froster' branch; this repo's main branch
# now hosts the Go implementation (see README.md and go/README.md).
#
# The URL https://raw.githubusercontent.com/dirkpetersen/froster/main/install.sh
# is widely published, so this shim keeps existing instructions working by
# fetching and running the real installer from the python-froster branch.

set -euo pipefail

echo "NOTE: the Python froster installer now lives on the 'python-froster' branch;"
echo "      fetching it from there. (This repo's main branch hosts froster.)"
echo ""

curl -fsS "https://raw.githubusercontent.com/dirkpetersen/froster/python-froster/install.sh?$(date +%s)" | bash -s -- "$@"
