#!/usr/bin/env bash
# rice-doctor behaviour (track B1, docs/ROADMAP.md). Fakes chezmoi, Hyprland,
# pgrep, fc-list, systemctl on PATH. Read-only: never touches the real
# environment, and the test never runs the real binary either.
set -u

test_dir=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$test_dir/.." && pwd)
src="$repo/dot_local/bin"
fail=0
pass()  { printf '  ok   %s\n' "$1"; }
flunk() { printf '  FAIL %s\n' "$1"; fail=1; }

sandbox=$(mktemp -d)
trap 'rm -rf "${sandbox:?}"' EXIT
mkdir -p "$sandbox/home" "$sandbox/bin" "$sandbox/src"
cp "$src/executable_rice-doctor" "$sandbox/bin/rice-doctor"
chmod +x "$sandbox/bin/rice-doctor"

cat > "$sandbox/bin/chezmoi" <<'FAKE'
#!/usr/bin/env bash
case "$1" in
	source-path) echo "$SB/src" ;;
	execute-template)
		shift
		[ "$1" = "-f" ] && shift
		content=$(cat "$1")
		if [ "$content" = "FAIL" ]; then
			echo "template error: broken on purpose" >&2
			exit 1
		fi
		echo "rendered ok" ;;
	data) cat "$SB/data.json" 2>/dev/null || echo '{}' ;;
	*) exit 0 ;;
esac
FAKE
chmod +x "$sandbox/bin/chezmoi"

cat > "$sandbox/bin/Hyprland" <<'FAKE'
#!/usr/bin/env bash
if [ "$1" = "--verify-config" ]; then
	if [ -f "$SB/hyprland-verify-fails" ]; then
		echo "config has errors" >&2
		exit 1
	fi
	echo "config ok"
fi
FAKE
chmod +x "$sandbox/bin/Hyprland"

cat > "$sandbox/bin/pgrep" <<'FAKE'
#!/usr/bin/env bash
# usage in rice-doctor: pgrep -f '...grootshell' | pgrep -x hypridle
running_file="$SB/running-procs"
[ -f "$running_file" ] || exit 1
pattern=${*: -1}
grep -qE -- "$pattern" "$running_file"
FAKE
chmod +x "$sandbox/bin/pgrep"

cat > "$sandbox/bin/fc-list" <<'FAKE'
#!/usr/bin/env bash
cat "$SB/fc-list-output" 2>/dev/null
FAKE
chmod +x "$sandbox/bin/fc-list"

cat > "$sandbox/bin/systemctl" <<'FAKE'
#!/usr/bin/env bash
# rice-doctor calls: systemctl --user is-active --quiet <svc>
svc=${*: -1}
grep -qxF "$svc" "$SB/active-services" 2>/dev/null
FAKE
chmod +x "$sandbox/bin/systemctl"

export SB="$sandbox"
export HOME="$sandbox/home"
export PATH="$sandbox/bin:$PATH"
run() { "$sandbox/bin/rice-doctor"; }

# A large, realistic fc-list dump with the wanted fonts interspersed early
# and late — regression coverage for the printf|grep-q SIGPIPE/pipefail bug
# (grep -q exits on first match, killing printf's write with SIGPIPE, which
# pipefail then reports as pipeline failure even though grep matched).
# >64KB of padding before each match: the default Linux pipe buffer is
# 64KB, past which a `printf ... | grep -q` producer can get SIGPIPE'd by
# grep's early exit — this must stay big enough to trigger that reliably.
gen_pad() { for i in $(seq "$1" "$2"); do printf '/usr/share/fonts/pad/Filler%d.ttf: Filler Font %d:style=Regular\n' "$i" "$i"; done; }
all_fonts=$(
	gen_pad 1 2000
	printf 'Material Symbols Rounded\n'
	gen_pad 2001 4000
	printf 'Rubik\n'
	gen_pad 4001 6000
	printf 'CaskaydiaCove Nerd Font Mono\n'
)

reset_healthy() {
	rm -rf "${sandbox:?}/src" "${sandbox:?}/home"
	mkdir -p "$sandbox/src" "$sandbox/home/.config/hypr" "$sandbox/home/.config/kitty"
	printf 'rendered ok' > "$sandbox/src/a.tmpl"
	# chezmoi's own init-time template — execute-template can't render it
	# outside `chezmoi init` (promptStringOnce undefined); doctor must skip it.
	printf 'FAIL' > "$sandbox/src/.chezmoi.toml.tmpl"
	rm -f "$SB/hyprland-verify-fails"
	printf '%s\n' "qs -p /home/user/.config/quickshell/grootshell" "hypridle" > "$SB/running-procs"
	printf '%s\n' "$all_fonts" > "$SB/fc-list-output"
	: > "$SB/active-services"
	printf '{"wallpaper_path":"%s"}' "$sandbox/home/wall.jpg" > "$SB/data.json"
	touch "$sandbox/home/wall.jpg"
	printf 'x' > "$sandbox/home/.config/hypr/colors-grootshell.lua"
	printf 'x' > "$sandbox/home/.config/kitty/colors-grootshell.conf"
}

# --- 1. everything healthy -> exit 0, no FAIL/WARN ------------------------
reset_healthy
out=$(run 2>&1); rc=$?
if [ "$rc" -eq 0 ] && ! printf '%s' "$out" | grep -qE 'FAIL|WARN'; then
	pass "doctor: healthy machine -> exit 0, no FAIL/WARN"
else
	flunk "doctor: healthy machine (rc=$rc out=<$out>)"
fi

# --- 2. broken template -> FAIL, exit 1 ------------------------------------
reset_healthy
printf 'FAIL' > "$sandbox/src/broken.tmpl"
out=$(run 2>&1); rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q "FAIL.*broken.tmpl"; then
	pass "doctor: broken template -> FAIL, exit 1"
else
	flunk "doctor: broken template (rc=$rc out=<$out>)"
fi

# --- 3. grootshell not running -> FAIL, exit 1 -----------------------------
reset_healthy
printf 'hypridle\n' > "$SB/running-procs"
out=$(run 2>&1); rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qi "FAIL.*grootshell"; then
	pass "doctor: grootshell not running -> FAIL, exit 1"
else
	flunk "doctor: grootshell not running (rc=$rc out=<$out>)"
fi

# --- 4. missing font -> FAIL, exit 1 ---------------------------------------
reset_healthy
printf 'Rubik\nCaskaydiaCove Nerd Font Mono\n' > "$SB/fc-list-output"
out=$(run 2>&1); rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qi "FAIL.*Material Symbols Rounded"; then
	pass "doctor: missing font -> FAIL, exit 1"
else
	flunk "doctor: missing font (rc=$rc out=<$out>)"
fi

# --- 5. wallpaper_path unset -> ok (optional), exit 0 --------------------------
reset_healthy
printf '{}' > "$SB/data.json"
out=$(run 2>&1); rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qi "ok .*wallpaper_path not set"; then
	pass "doctor: wallpaper_path unset -> ok, exit 0"
else
	flunk "doctor: wallpaper_path unset (rc=$rc out=<$out>)"
fi

# --- 6. wallpaper_path set but file missing -> FAIL, exit 1 ----------------
reset_healthy
printf '{"wallpaper_path":"%s"}' "$sandbox/home/gone.jpg" > "$SB/data.json"
out=$(run 2>&1); rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qi "FAIL.*gone.jpg"; then
	pass "doctor: wallpaper_path set but missing -> FAIL, exit 1"
else
	flunk "doctor: wallpaper_path missing file (rc=$rc out=<$out>)"
fi

# --- 7. retired service (mako) active -> WARN only, exit 0 -----------------
reset_healthy
printf 'mako.service\n' > "$SB/active-services"
out=$(run 2>&1); rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qi "WARN.*mako"; then
	pass "doctor: mako.service active -> WARN, exit 0"
else
	flunk "doctor: mako.service active (rc=$rc out=<$out>)"
fi

# --- 8. generated theme files missing -> WARN only, exit 0 -----------------
reset_healthy
rm -f "$sandbox/home/.config/hypr/colors-grootshell.lua" "$sandbox/home/.config/kitty/colors-grootshell.conf"
out=$(run 2>&1); rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qi "WARN.*colors-grootshell"; then
	pass "doctor: generated theme files missing -> WARN, exit 0"
else
	flunk "doctor: generated theme files missing (rc=$rc out=<$out>)"
fi

exit $fail
