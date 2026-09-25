#!/usr/bin/env bash
# docs/dependencies.md must equal what docs/dependencies.md.tmpl renders to.
set -u
repo=$(cd "$(dirname "$0")/.." && pwd)
fail=0
if ! command -v chezmoi >/dev/null 2>&1; then echo "  skip chezmoi not installed"; exit 0; fi
if out=$(chezmoi --source "$repo" execute-template < "$repo/docs/dependencies.md.tmpl" 2>&1) \
	&& [ "$out" = "$(cat "$repo/docs/dependencies.md")" ]; then
	printf '  ok   dependencies.md is up to date\n'
else
	printf '  FAIL dependencies.md is stale or does not render — run: make docs\n'; fail=1
fi
exit $fail
