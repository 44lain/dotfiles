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

cat > "$sandbox/bin/apt-cache" <<'FAKE'
#!/usr/bin/env bash
# fixtures: $SB/apt/madison-<pkg>, $SB/apt/policy-<pkg>
case "$1" in
	madison) cat "$SB/apt/madison-$2" 2>/dev/null ;;
	policy)  cat "$SB/apt/policy-$2" 2>/dev/null ;;
esac
FAKE
chmod +x "$sandbox/bin/apt-cache"

export SB="$sandbox"
export HOME="$sandbox/home"
export PATH="$sandbox/bin:$PATH"
export RICE_OS_RELEASE="$sandbox/os-release"
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
	rm -rf "$SB/apt"; mkdir -p "$SB/apt"
	rm -f "$SB/os-release"
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

# ===== dependencies section ====================================================
os_release() { printf '%b' "$1" > "$SB/os-release"; }
# two missing tools (binaries that cannot exist on PATH): one required, one optional
pkgs_json() {
	printf '{"packages":{"req":{"desc":"needed thing","bin":"rice-test-req-bin","required":true,"min_version":"0.55","fedora":"pkg-fed","debian":"pkg-deb","arch":"pkg-arch","manual":"build it by hand"},"opt":{"desc":"nice thing","bin":"rice-test-opt-bin","fedora":"opt-fed","debian":"opt-deb","arch":"opt-arch"}}}' > "$SB/data.json"
}
parrot='ID=parrot\nID_LIKE=debian\nVERSION_CODENAME=echo\n'
madison_two() {  # newest in a backports-style suite, default candidate older
	printf ' pkg-deb | 0.55.2+ds-1~bpo13+1 | https://example.test/distro echo-backports/main amd64 Packages\n pkg-deb | 0.52.2+ds-2 | https://example.test/distro echo/main amd64 Packages\n' > "$SB/apt/madison-pkg-deb"
}

# D1. Debian family, newest version only in another suite -> "-t <suite from apt>", FAIL
reset_healthy; pkgs_json; os_release "$parrot"; madison_two
printf '  Candidate: 0.52.2+ds-2\n' > "$SB/apt/policy-pkg-deb"
out=$(run 2>&1); rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q 'FAIL.*req' \
	&& printf '%s' "$out" | grep -q 'sudo apt install -t echo-backports pkg-deb'; then
	pass "doctor D1: apt suite taken from apt's own data, required missing -> FAIL"
else
	flunk "doctor D1 (rc=$rc out=<$out>)"
fi

# D2. default candidate already the newest -> plain install, no -t
reset_healthy; pkgs_json; os_release "$parrot"
printf ' pkg-deb | 0.56.1-1 | https://example.test/distro forky/main amd64 Packages\n' > "$SB/apt/madison-pkg-deb"
printf '  Candidate: 0.56.1-1\n' > "$SB/apt/policy-pkg-deb"
out=$(run 2>&1)
if printf '%s' "$out" | grep -q 'sudo apt install .*pkg-deb' && ! printf '%s' "$out" | grep -q -- '-t '; then
	pass "doctor D2: newest is default -> plain apt install"
else
	flunk "doctor D2 (out=<$out>)"
fi

# D3. newest version apt knows is below min_version -> explains, no bogus command for it
reset_healthy; pkgs_json; os_release "$parrot"
printf ' pkg-deb | 0.52.2+ds-2 | https://example.test/distro echo/main amd64 Packages\n' > "$SB/apt/madison-pkg-deb"
printf '  Candidate: 0.52.2+ds-2\n' > "$SB/apt/policy-pkg-deb"
out=$(run 2>&1)
if printf '%s' "$out" | grep -q '0.55 or newer is needed'; then
	pass "doctor D3: apt release too old -> says so"
else
	flunk "doctor D3 (out=<$out>)"
fi

# D4. apt cache empty -> tells the user to `apt update`, prints manual hint, no apt command for it
reset_healthy; pkgs_json; os_release "$parrot"
out=$(run 2>&1)
if printf '%s' "$out" | grep -q 'sudo apt update' && printf '%s' "$out" | grep -q 'build it by hand' \
	&& ! printf '%s' "$out" | grep -q 'apt install .*pkg-deb'; then
	pass "doctor D4: apt knows nothing -> 'sudo apt update' note + manual hint"
else
	flunk "doctor D4 (out=<$out>)"
fi

# D5. other families
for pair in "fedora|ID=fedora\n|sudo dnf install pkg-fed" "arch|ID=arch\n|sudo pacman -S pkg-arch"; do
	IFS='|' read -r name osr want <<<"$pair"
	reset_healthy; pkgs_json; os_release "$osr"
	out=$(run 2>&1)
	if printf '%s' "$out" | grep -qF "$want"; then pass "doctor D5: $name -> $want"; else flunk "doctor D5 $name (out=<$out>)"; fi
done

# D6. unknown OS, and os-release missing -> binaries listed, no sudo, no crash
for osr in 'ID=plan9\n' ''; do
	reset_healthy; pkgs_json
	[ -n "$osr" ] && os_release "$osr"
	out=$(run 2>&1); rc=$?
	if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q 'rice-test-req-bin' \
		&& printf '%s' "$out" | grep -q 'not recognised' && ! printf '%s' "$out" | grep -q 'sudo '; then
		pass "doctor D6: unknown distro (${osr:-no os-release}) -> list only"
	else
		flunk "doctor D6 (osr=${osr:-none} rc=$rc out=<$out>)"
	fi
done

# D7. only an optional tool missing -> WARN, exit 0
reset_healthy
printf '{"packages":{"opt":{"desc":"nice thing","bin":"rice-test-opt-bin","fedora":"opt-fed","debian":"opt-deb","arch":"opt-arch"}}}' > "$SB/data.json"
os_release 'ID=fedora\n'
out=$(run 2>&1); rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q 'WARN.*opt'; then
	pass "doctor D7: optional missing -> WARN, exit 0"
else
	flunk "doctor D7 (rc=$rc out=<$out>)"
fi

# D8. family detection across derivatives (quoted / multi-value ID_LIKE)
while IFS='|' read -r label osr want; do
	reset_healthy; pkgs_json; os_release "$osr"
	# apt fixtures so the Debian-family rows have something to install
	for p in pkg-deb opt-deb; do
		printf ' %s | 0.56.1-1 | https://example.test/distro stable/main amd64 Packages\n' "$p" > "$SB/apt/madison-$p"
		printf '  Candidate: 0.56.1-1\n' > "$SB/apt/policy-$p"
	done
	out=$(run 2>&1)
	if printf '%s' "$out" | grep -qF "$want"; then pass "doctor D8: $label"; else flunk "doctor D8 $label (out=<$out>)"; fi
done <<'EOF'
Ubuntu|ID=ubuntu\nID_LIKE=debian\n|sudo apt install
Linux Mint|ID=linuxmint\nID_LIKE="ubuntu debian"\n|sudo apt install
Kali|ID=kali\nID_LIKE=debian\n|sudo apt install
Raspberry Pi OS|ID=raspbian\nID_LIKE=debian\n|sudo apt install
Manjaro|ID=manjaro\nID_LIKE=arch\n|sudo pacman -S
Rocky|ID="rocky"\nID_LIKE="rhel centos fedora"\n|sudo dnf install
EOF

# D9. every listed tool present -> ok summary, exit 0
reset_healthy
printf '#!/usr/bin/env bash\n' > "$sandbox/bin/rice-test-req-bin"; chmod +x "$sandbox/bin/rice-test-req-bin"
printf '{"packages":{"req":{"desc":"needed thing","bin":"rice-test-req-bin","required":true,"fedora":"x","debian":"x","arch":"x"}}}' > "$SB/data.json"
out=$(run 2>&1); rc=$?
rm -f "$sandbox/bin/rice-test-req-bin"
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q 'ok   all 1 checked dependencies present'; then
	pass "doctor D9: all present -> ok"
else
	flunk "doctor D9 (rc=$rc out=<$out>)"
fi

exit $fail
