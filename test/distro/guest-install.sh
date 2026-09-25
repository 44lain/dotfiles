#!/usr/bin/env bash
# What a stranger does, in a clean container: install chezmoi the documented
# way, apply as profile=guest, run `rice doctor`. Every template must render
# and doctor must print the right install command for the distro family.
# Needs docker + network; run with `make distro-check`.
set -uo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
command -v docker >/dev/null 2>&1 || { echo "docker not found — skipped"; exit 0; }

tmp=$(mktemp -d); trap 'rm -rf "${tmp:?}"' EXIT

# Runs inside the container. $PREP installs the stranger's prerequisites
# (curl, git, jq) with the distro's own package manager.
cat > "$tmp/guest.sh" <<'GUEST'
set -e
eval "$PREP"
# same install path as the README (~/.local/bin, put on PATH by hand)
sh -c "$(curl -fsLS get.chezmoi.io)" -- -b ~/.local/bin >/dev/null
export PATH="$HOME/.local/bin:$PATH"
mkdir -p ~/.config/chezmoi
printf 'sourceDir = "/src"\n[data]\n    profile = "guest"\n    host    = "pentest"\n' > ~/.config/chezmoi/chezmoi.toml
chezmoi apply --force
set +e
~/.local/bin/rice-doctor
GUEST

# image|prepare command|install command doctor must print
cases=(
	"debian:trixie|apt-get update -qq && apt-get install -y -qq curl git jq ca-certificates >/dev/null|sudo apt install"
	"ubuntu:24.04|apt-get update -qq && apt-get install -y -qq curl git jq ca-certificates >/dev/null|sudo apt install"
	"fedora:43|dnf install -y -q curl git jq >/dev/null|sudo dnf install"
)

fail=0
for c in "${cases[@]}"; do
	IFS='|' read -r image prep want <<<"$c"
	echo "== $image =="
	if ! docker pull -q "$image" >/dev/null 2>&1; then echo "  cannot pull — skipped"; continue; fi
	out=$(docker run --rm -v "$repo:/src:ro" -v "$tmp:/rice:ro" -e PREP="$prep" "$image" bash /rice/guest.sh 2>&1) || true
	if printf '%s' "$out" | grep -q 'FAIL template renders'; then
		echo "  FAIL: a template did not render"; printf '%s\n' "$out" | grep 'template renders'; fail=1
	elif ! printf '%s' "$out" | grep -qF "$want"; then
		echo "  FAIL: doctor did not print '$want'"; printf '%s\n' "$out" | tail -25; fail=1
	elif [ "$image" = debian:trixie ] && ! printf '%s' "$out" | grep -q backports; then
		# Stock Debian has backports off: the stranger must be told to enable it.
		echo "  FAIL: doctor did not mention 'backports' on stock $image"; printf '%s\n' "$out" | tail -25; fail=1
	else
		echo "  ok: templates render, doctor prints '$want'"
	fi
done
exit $fail
