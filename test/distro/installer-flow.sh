#!/usr/bin/env bash
# The guided installer end to end in clean containers: python3 -m installer
# --plain fed answers on stdin (screens 1-8: profile, host, preferences, scan,
# plan, configure with the real chezmoi + rice-onboard + rice apply, verify
# with the real rice doctor). The plan screen selects NOTHING, so no package is
# installed: the point is the flow, the onboard flags and the doctor path.
# Not covered here (needs a real machine / systemd / a session): package
# installs, hyprland --verify-config, fonts. See the acceptance step in the plan.
# Needs docker + network; run with `make distro-check`.
set -uo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
if ! command -v docker >/dev/null 2>&1; then
	echo "docker not found — skipped"
	[ "${CI:-}" = true ] && { echo "FAIL: CI must not skip the installer flow test"; exit 1; }
	exit 0
fi

tmp=$(mktemp -d); trap 'rm -rf "${tmp:?}"' EXIT

# Each answer is "prompt text|answer": it is sent only once that prompt (its
# n-th appearance, counting equal prompts above it) is on the transcript. Not a
# fixed delay: the scan and apply take a variable time, and Python buffers a
# pipe it reads, so an early line would be swallowed by Python instead of
# reaching rice-onboard / rice apply, which read the same stdin for their own
# prompts. A terminal delivers one line per prompt; this imitates it.
#   welcome: continue | profile: guest | host name | git name | git e-mail
#   wallpaper folder (empty = skip) | lock image: skip | plan: n = none, then
#   empty = confirm | [Debian family only] ~/.bashrc loader: y | configure: y
#   | rice apply: y
base_answers='What now?|1
(recommended)|1
Name for this machine|ci-box
Git name for this machine|CI Bot
Git e-mail for this machine|ci@example.com
Wallpaper folder (empty|
Lock-screen image|2
numbers toggle|n
numbers toggle|
'
final_answers='Apply the configuration now?|y
apply? [y/N]|y
'
loader_answer='Add the loader?|y
'

# Runs inside the container (as root, so no sudo). $PREP installs the stranger's
# prerequisites with the distro's own package manager.
cat > "$tmp/flow.sh" <<'FLOW'
set -u
bad=0
ok()   { printf '  ok   %s\n' "$*"; }
fail() { printf '  FAIL %s\n' "$*"; bad=1; }
eval "$PREP" || { echo "  FAIL: prerequisites did not install"; exit 1; }
sh -c "$(curl -fsLS get.chezmoi.io)" -- -b ~/.local/bin >/dev/null || { echo "  FAIL: chezmoi did not install"; exit 1; }
export PATH="$HOME/.local/bin:$PATH"

# The repo where chezmoi expects it. cp -r (not -a): files must belong to root
# or git refuses the checkout; .git is recreated because a worktree's .git is
# a pointer to a host path.
mkdir -p ~/.local/share
cp -r /repo ~/.local/share/chezmoi
cd ~/.local/share/chezmoi || exit 1
rm -rf .git; git init -q; git add -A
git -c user.name=ci -c user.email=ci@example.com commit -qm source

if python3 -c 'import curses, tomllib' 2>/dev/null; then ok "$(python3 --version 2>&1): import curses, tomllib"; else fail "python3 lacks curses or tomllib"; fi

: > /tmp/transcript
feed() {
	declare -A seen=()
	while IFS='|' read -r prompt answer; do
		[ -n "$prompt" ] || continue
		seen[$prompt]=$(( ${seen[$prompt]:-0} + 1 ))
		for _ in $(seq 1 600); do   # up to 60 s per prompt
			[ "$(grep -cF -- "$prompt" /tmp/transcript)" -ge "${seen[$prompt]}" ] && break
			sleep 0.1
		done
		[ "$(grep -cF -- "$prompt" /tmp/transcript)" -ge "${seen[$prompt]}" ] || return 0   # prompt never came: close stdin
		sleep 0.3
		printf '%s\n' "$answer"
	done < /rice/answers
}
feed | python3 -u -m installer --plain --lang en > /tmp/transcript 2>&1
rc=${PIPESTATUS[1]}
cat /tmp/transcript

if [ "$rc" -eq 0 ]; then ok "flow exit code 0"
elif [ "$rc" -eq 1 ] && grep -q 'Stopped' /tmp/transcript; then fail "flow stopped early (cancel), exit 1"
else fail "flow exit code $rc"; fi
grep -q '8/8' /tmp/transcript && ok "reached screen 8/8" || fail "transcript has no 8/8"
grep -q 'host    = "ci-box"' ~/.config/chezmoi/chezmoi.toml 2>/dev/null && ok "chezmoi.toml has host ci-box" || fail "chezmoi.toml lacks host ci-box"
[ -e ~/.local/bin/rice ] && ok "~/.local/bin/rice exists" || fail "~/.local/bin/rice missing"

# Parity: what the scan calls not-ok is what rice doctor calls missing
python3 - > /tmp/scan.txt <<'PY'
import sys
sys.path.insert(0, ".")
from installer import model
pk = model.load_packages(".chezmoidata/packages.toml")
bins = {p.key: p.bin for p in pk}
for s in model.scan(pk, model.os_family(), model.default_env()):
    if s.state != "ok" and bins.get(s.key):  # doctor checks binaries; fonts and clones have their own sections
        print(s.key)
PY
rice-doctor 2>&1 | sed -n 's/^  \(WARN\|FAIL\) missing\( (required)\)\?: \([^ ]*\) .*/\3/p' | sort > /tmp/doctor.txt
sort -o /tmp/scan.txt /tmp/scan.txt
if [ -s /tmp/scan.txt ] && [ "$(cat /tmp/scan.txt)" = "$(cat /tmp/doctor.txt)" ]; then ok "scan and rice doctor list the same $(wc -l < /tmp/scan.txt) missing items"
else fail "scan and rice doctor disagree"; echo "scan:"; cat /tmp/scan.txt; echo "doctor:"; cat /tmp/doctor.txt; fi
exit $bad
FLOW

# image|prepare command|is the ~/.bashrc loader asked (stock ~/.bashrc without ~/.bashrc.d)
cases=(
	"fedora:43|dnf install -y -q python3 git curl jq >/dev/null|no"
	"debian:trixie|DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 git curl jq ca-certificates >/dev/null|yes"
	"archlinux:latest|pacman -Syu --noconfirm --needed -q python git jq >/dev/null && if [ ! -f /root/.bashrc ]; then cp /etc/skel/.bashrc /root/; fi|yes"
)

fail=0; total=${#cases[@]}; checked=0
for c in "${cases[@]}"; do
	IFS='|' read -r image prep loader <<<"$c"
	if [ "$loader" = yes ]; then printf '%s%s%s' "$base_answers" "$loader_answer" "$final_answers" > "$tmp/answers"
	else printf '%s%s' "$base_answers" "$final_answers" > "$tmp/answers"; fi
	echo "== $image =="
	if ! docker pull -q "$image" >/dev/null 2>&1; then echo "  cannot pull — skipped"; continue; fi
	checked=$((checked + 1))
	if docker run --rm -v "$repo:/repo:ro" -v "$tmp:/rice:ro" -e PREP="$prep" "$image" bash /rice/flow.sh > "$tmp/out" 2>&1; then
		grep '^  ok ' "$tmp/out"; echo "  ok: guided flow passed on $image"
	else
		echo "  FAIL: guided flow failed on $image (transcript below)"; cat "$tmp/out"; fail=1
	fi
done
echo "$checked of $total images checked"
if [ "$checked" -lt "$total" ] && [ "${CI:-}" = true ]; then
	echo "FAIL: images were skipped in CI"; fail=1
fi
exit $fail
