#!/usr/bin/env bash
# Runs the installer's unit tests (standard-library unittest, no pytest).
set -u
repo=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo" || exit 1
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
	echo "  FAIL installer tests need python3 >= 3.11"
	exit 1
fi
python3 -m unittest discover -s installer/tests -t . 2>&1
