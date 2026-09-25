#!/usr/bin/env bash
# Does hyprland.lua load on the Hyprland Debian's backports ships (0.55.x)?
# Needs docker + network. Run: bash test/distro/hyprland-verify.sh
#
# `Hyprland --verify-config` runs headless (no display/GPU needed): it loads
# the Lua config and prints "config ok" or the errors. It does NOT run bind
# callbacks or the hyprland.start handler, and a Lua runtime error stops the
# load at that line, so fix errors one at a time.
set -uo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
command -v docker >/dev/null 2>&1 || { echo "docker not found — skipped"; exit 0; }
tmp=$(mktemp -d); trap 'rm -rf "${tmp:?}"' EXIT
chmod 755 "$tmp"

# machine.lua is a template; render it for a neutral host outside the container.
chezmoi --source "$repo" execute-template \
	--override-data '{"host":"pentest","profile":"guest"}' \
	< "$repo/dot_config/hypr/machine.lua.tmpl" > "$tmp/machine.lua" || exit 1
cp "$repo/dot_config/hypr/hyprland.lua" "$tmp/hyprland.lua"

# Runs inside the container as a normal user (Hyprland refuses to run as root).
cat > "$tmp/run.sh" <<'EOF'
set -u
export XDG_RUNTIME_DIR=/tmp/xdg-$USER   # Hyprland aborts without one
mkdir -p -m 700 "$XDG_RUNTIME_DIR" ~/.config/hypr
cp /rice/hyprland.lua /rice/machine.lua ~/.config/hypr/
Hyprland --version | head -1
# Negative control: an unknown key must be reported, or a "config ok" below
# would prove nothing.
echo 'hl.config({ misc = { no_such_option = 1 } })' > /tmp/bad.lua
if ! Hyprland --verify-config -c /tmp/bad.lua 2>&1 | grep -q "unknown config key"; then
	echo "FAIL: --verify-config did not reject an unknown key; check is not meaningful"
	exit 1
fi
out=$(Hyprland --verify-config -c ~/.config/hypr/hyprland.lua 2>&1); rc=$?
printf '%s\n' "$out" | sed -n '/Config parsing result/,$p'
[ "$rc" -eq 0 ] && printf '%s\n' "$out" | grep -qx "config ok"
EOF

# SYS_NICE: Debian's Hyprland binary carries cap_sys_nice=ep, and exec fails
# with "Operation not permitted" when the container's bounding set lacks it.
# shellcheck disable=SC2016  # expanded inside the container
docker run --rm --cap-add SYS_NICE -v "$tmp:/rice:ro" debian:trixie bash -c '
	set -e
	export DEBIAN_FRONTEND=noninteractive
	echo "deb http://deb.debian.org/debian trixie-backports main" > /etc/apt/sources.list.d/bp.list
	apt-get update -qq >/dev/null
	apt-get install -y -qq -t trixie-backports hyprland >/dev/null 2>&1
	useradd -m rice
	su rice -c "bash /rice/run.sh"
'
