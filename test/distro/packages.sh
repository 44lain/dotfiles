#!/usr/bin/env bash
# Do the package names in .chezmoidata/packages.toml exist in each distro's
# real repos? Needs docker + network; run with `make distro-check`.
#   hard images  -> a MISSING/TOO OLD package fails the run
#   soft images  -> reported for information only (may lack Hyprland legitimately)
set -uo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
if ! command -v docker >/dev/null 2>&1; then
	echo "docker not found — skipped"
	[ "${CI:-}" = true ] && { echo "FAIL: CI must not skip the distro check"; exit 1; }
	exit 0
fi

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

fail=0; hard_total=0; hard_checked=0
for entry in "${images[@]}"; do
	IFS='|' read -r family image mode <<<"$entry"
	echo "== $image ($family, $mode) =="
	[ "$mode" = hard ] && hard_total=$((hard_total + 1))
	if ! docker pull -q "$image" >/dev/null 2>&1; then
		echo "  cannot pull $image — skipped"; continue
	fi
	[ "$mode" = hard ] && hard_checked=$((hard_checked + 1))
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
echo "$hard_checked of $hard_total hard images checked"
# A hard image that could not be pulled was not checked: never a silent pass in CI.
if [ "$hard_checked" -lt "$hard_total" ] && [ "${CI:-}" = true ]; then
	echo "FAIL: hard images were skipped in CI"; fail=1
fi
exit $fail
