#!/usr/bin/env bash
# Do the package names in .chezmoidata/packages.toml exist in each distro's
# real repos? Needs docker + network; run with `make distro-check`.
#   hard images  -> a MISSING/TOO OLD package fails the run
#   soft images  -> reported for information only (may lack Hyprland legitimately)
set -uo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
command -v docker >/dev/null 2>&1 || { echo "docker not found — skipped"; exit 0; }

tmp=$(mktemp -d); trap 'rm -rf "${tmp:?}"' EXIT
# family|image|hard?
images=(
	"debian|debian:trixie|hard"
	"debian|parrotsec/core:latest|hard"
	"fedora|fedora:43|hard"
	"arch|archlinux:latest|hard"
	"debian|ubuntu:24.04|soft"
	"debian|kalilinux/kali-rolling:latest|soft"
)

names_for() {  # names_for <family> -> package<TAB>min_version
	python3 - "$repo/.chezmoidata/packages.toml" "$1" <<'PY'
import sys, tomllib
for p in tomllib.load(open(sys.argv[1], "rb"))["packages"].values():
    n = p.get(sys.argv[2], "")
    if n:
        print(f"{n}\t{p.get('min_version', '')}")
PY
}

fail=0
for entry in "${images[@]}"; do
	IFS='|' read -r family image mode <<<"$entry"
	echo "== $image ($family, $mode) =="
	if ! docker pull -q "$image" >/dev/null 2>&1; then
		echo "  cannot pull $image — skipped"; continue
	fi
	names_for "$family" > "$tmp/names.tsv"
	cp "$repo/test/distro/container-check.sh" "$tmp/container-check.sh"
	if docker run --rm -v "$tmp:/rice:ro" "$image" bash /rice/container-check.sh "$family"; then
		echo "  => all names resolve"
	elif [ "$mode" = hard ]; then
		echo "  => FAILED"; fail=1
	else
		echo "  => gaps on $image (information only)"
	fi
done
exit $fail
