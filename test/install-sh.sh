#!/usr/bin/env bash
# install.sh: shows what is missing and asks first, never installs a newer Python,
# reattaches the terminal, and opens the TUI. Everything is faked on PATH.
set -u
test_dir=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$test_dir/.." && pwd)
fail=0
pass()  { printf '  ok   %s\n' "$1"; }
flunk() { printf '  FAIL %s\n' "$1"; fail=1; }

sandbox=$(mktemp -d)
trap 'rm -rf "${sandbox:?}"' EXIT
home="$sandbox/home"; mkdir -p "$home/.local/share/chezmoi/.git" "$home/.local/share/chezmoi/installer" "$sandbox/bin"
: > "$home/.local/share/chezmoi/installer/__main__.py"
# shellcheck disable=SC2016 # the generated fake script must expand $1/$3 itself, later
printf '#!/bin/sh\necho "${FAKE_UID:-1000}"\n' > "$sandbox/bin/id"; chmod +x "$sandbox/bin/id"
printf 'ID=fedora\n' > "$sandbox/os-release"
log="$sandbox/calls.log"; : > "$log"

fake() {  # fake <name> <exit-code> [stdout]
	printf '#!/bin/sh\necho "%s $*" >> "%s"\n%s\nexit %s\n' "$1" "$log" "${3:+echo \"$3\"}" "$2" > "$sandbox/bin/$1"
	chmod +x "$sandbox/bin/$1"
}
fake git 0; fake curl 0; fake jq 0; fake chezmoi 0; fake python3 0; fake sudo 0
export HOME="$home" RICE_OS_RELEASE="$sandbox/os-release"
# R5: the script runs with PATH=$sandbox/bin ONLY, so a real git/curl/python3 is never found
base_path="$sandbox/bin"

run() {  # run <answers> ... ; stdin is a pipe, the terminal is the RICE_TTY file
	printf '%s' "$1" > "$sandbox/tty"
	RICE_TTY="$sandbox/tty" PATH="$base_path" /bin/sh "$repo/install.sh" "${@:2}" 2>&1 < /dev/null
}

# 1. everything present: no prompt, hands over to the TUI with the arguments
: > "$log"
out=$(run "" --plain); rc=$?
if [ $rc -eq 0 ] && grep -q '^python3 -m installer --plain' "$log" && ! grep -q '^sudo' "$log"; then
	pass "install.sh: all present -> straight to the TUI, args passed, nothing installed"
else
	flunk "install.sh all present (rc=$rc out=<$out>)"
fi

# 2. git missing: lists it, answer n -> aborts without installing
rm "$sandbox/bin/git"; : > "$log"
out=$(run "n
"); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q 'git' && ! grep -q '^sudo' "$log" && ! grep -q '^python3 -m installer' "$log"; then
	pass "install.sh: missing git, answered n -> asked first, installed nothing"
else
	flunk "install.sh decline (rc=$rc out=<$out>)"
fi

# 3. git missing: answer y -> installs it through the distro package manager
: > "$log"
fake git 0   # becomes present after the (fake) install is called; sudo records the call
cat > "$sandbox/bin/sudo" <<FAKE
#!/bin/sh
echo "sudo \$*" >> "$log"
printf '#!/bin/sh\nexit 0\n' > "$sandbox/bin/git"; /bin/chmod +x "$sandbox/bin/git"
exit 0
FAKE
chmod +x "$sandbox/bin/sudo"; rm "$sandbox/bin/git"
out=$(run "y
"); rc=$?
if [ $rc -eq 0 ] && grep -q '^sudo dnf install -y .*git' "$log"; then
	pass "install.sh: answered y -> sudo dnf install -y git (family from os-release)"
else
	flunk "install.sh install (rc=$rc out=<$out> log=<$(cat "$log")>)"
fi

# 4. Python older than 3.11: says so and stops; never installs Python
fake python3 1; : > "$log"
out=$(run ""); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -qi '3.11' && ! grep -q 'install' "$log"; then
	pass "install.sh: old Python -> clear message, nothing installed"
else
	flunk "install.sh old python (rc=$rc out=<$out>)"
fi

# 5. no terminal available: refuses instead of hanging
fake python3 0
out=$(RICE_TTY="$sandbox/does-not-exist" PATH="$base_path" /bin/sh "$repo/install.sh" 2>&1 </dev/null); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -qi 'terminal'; then
	pass "install.sh: no terminal -> clear error"
else
	flunk "install.sh no terminal (rc=$rc out=<$out>)"
fi
# 6. /dev/tty readable but unopenable (no controlling terminal): clear error up front
fake python3 0; fake git 0
if [ -x /usr/bin/setsid ]; then
	out=$(setsid -w /usr/bin/env -i HOME="$home" PATH="$base_path" RICE_TTY=/dev/tty RICE_OS_RELEASE="$sandbox/os-release" /bin/sh "$repo/install.sh" 2>&1 </dev/null); rc=$?
	if [ $rc -ne 0 ] && printf '%s' "$out" | grep -qi 'no terminal' && ! printf '%s' "$out" | grep -qiE 'Endere|No such device'; then
		pass "install.sh: /dev/tty present but no controlling terminal -> clear error"
	else
		flunk "install.sh no controlling terminal (rc=$rc out=<$out>)"
	fi
else
	printf '  skip install.sh no-controlling-terminal test: setsid not installed\n'
fi

# 7. python3 installed by the script itself but too old: stops with the 3.11 message, no TUI
rm "$sandbox/bin/python3"; : > "$log"
cat > "$sandbox/bin/sudo" <<FAKE
#!/bin/sh
echo "sudo \$*" >> "$log"
printf '#!/bin/sh\nexit 1\n' > "$sandbox/bin/python3"; /bin/chmod +x "$sandbox/bin/python3"
exit 0
FAKE
out=$(run "y
"); rc=$?
if [ $rc -eq 1 ] && printf '%s' "$out" | grep -q '3.11' && ! grep -q '^python3 -m installer' "$log" && grep -q '^sudo dnf install -y .*python3' "$log"; then
	pass "install.sh: python3 installed by us is too old -> 3.11 message, TUI never started"
else
	flunk "install.sh re-check after install (rc=$rc out=<$out> log=<$(cat "$log")>)"
fi
fake python3 0; fake sudo 0

# 8. source dir: non-empty without .git -> clear error; empty -> cloned into
nogit="$sandbox/nogit"; mkdir -p "$nogit"; : > "$nogit/stray"; : > "$log"
out=$(CHEZMOI_SOURCE_DIR="$nogit" run ""); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q "$nogit" && ! grep -q '^git clone' "$log"; then
	pass "install.sh: non-empty source dir without .git -> clear error naming it"
else
	flunk "install.sh non-empty source dir (rc=$rc out=<$out>)"
fi
emptydir="$sandbox/emptydir"; mkdir -p "$emptydir"; : > "$log"
# shellcheck disable=SC2016 # the generated fake script must expand $1/$3 itself, later
printf '#!/bin/sh\necho "git $*" >> "%s"\ncase $1 in clone) /bin/mkdir -p "$3/installer"; : > "$3/installer/__main__.py" ;; esac\nexit 0\n' "$log" > "$sandbox/bin/git"
out=$(CHEZMOI_SOURCE_DIR="$emptydir" run ""); rc=$?
fake git 0
if [ $rc -eq 0 ] && grep -q '^git clone' "$log"; then
	pass "install.sh: empty source dir -> cloned into"
else
	flunk "install.sh empty source dir (rc=$rc out=<$out>)"
fi

# 9. chezmoi prompt explains in plain words that it runs a downloaded script
rm "$sandbox/bin/chezmoi"
out=$(run "n
"); rc=$?
if printf '%s' "$out" | grep -q 'get.chezmoi.io' && printf '%s' "$out" | grep -qi 'downloads and runs a script'; then
	pass "install.sh: chezmoi prompt says it downloads and runs a script"
else
	flunk "install.sh chezmoi wording (rc=$rc out=<$out>)"
fi

# 10. a chezmoi living in ~/.local/bin (installed by an earlier run) is found: no prompt
mkdir -p "$home/.local/bin"; : > "$log"
rm -f "$sandbox/bin/chezmoi"
printf '#!/bin/sh\nexit 0\n' > "$home/.local/bin/chezmoi"; chmod +x "$home/.local/bin/chezmoi"
out=$(run "" --plain); rc=$?
if [ $rc -eq 0 ] && ! printf '%s' "$out" | grep -q 'Install these now' && grep -q '^python3 -m installer' "$log"; then
	pass "install.sh: chezmoi in ~/.local/bin is found on a re-run (no install prompt)"
else
	flunk "install.sh ~/.local/bin on PATH (rc=$rc out=<$out>)"
fi
rm -f "$home/.local/bin/chezmoi"

# 12. root without sudo: no sudo prefix is printed or used
fake chezmoi 0; rm -f "$sandbox/bin/sudo" "$sandbox/bin/git"; fake dnf 0; : > "$log"
out=$(FAKE_UID=0 run "y
"); rc=$?
if [ $rc -eq 0 ] && grep -q '^dnf install -y .*git' "$log" && ! printf '%s' "$out" | grep -q 'sudo'; then
	pass "install.sh: root -> no sudo prefix (works without sudo installed)"
else
	flunk "install.sh root without sudo (rc=$rc out=<$out> log=<$(cat "$log")>)"
fi
# 13. not root and no sudo: clear message, nothing installed
: > "$log"
out=$(FAKE_UID=1000 run "y
"); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -qi 'sudo' && ! grep -q '^dnf' "$log"; then
	pass "install.sh: not root and no sudo -> clear message"
else
	flunk "install.sh no sudo (rc=$rc out=<$out>)"
fi
fake sudo 0; fake git 0

# 14. the source dir is another repo: one-line warning; no installer package: clear error
other="$sandbox/other"; mkdir -p "$other/.git"; : > "$log"
fake git 0 "https://example.com/someone/other-project.git"
out=$(CHEZMOI_SOURCE_DIR="$other" run ""); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q 'not the dotfiles repo' && printf '%s' "$out" | grep -q 'installer/__main__.py' && ! printf '%s' "$out" | grep -q 'No module named'; then
	pass "install.sh: foreign repo -> warning plus clear error, no 'No module named'"
else
	flunk "install.sh foreign repo (rc=$rc out=<$out>)"
fi
fake git 0

# 15. debian family: apt-get update runs BEFORE install, and the listing shown before the prompt has both
printf 'ID=ubuntu\nID_LIKE=debian\n' > "$sandbox/os-release-deb"
rm -f "$sandbox/bin/git"; : > "$log"
cat > "$sandbox/bin/sudo" <<FAKE
#!/bin/sh
echo "sudo \$*" >> "$log"
exit 0
FAKE
out=$(RICE_OS_RELEASE="$sandbox/os-release-deb" run "y
"); rc=$?
upd_line=$(grep -n '^sudo apt-get update' "$log" | head -n1 | cut -d: -f1)
ins_line=$(grep -n '^sudo apt-get install -y .*git' "$log" | head -n1 | cut -d: -f1)
listing=$(printf '%s' "$out" | sed '/Install these now/q')
if [ -n "$upd_line" ] && [ -n "$ins_line" ] && [ "$upd_line" -lt "$ins_line" ] \
	&& printf '%s' "$listing" | grep -q 'sudo apt-get update' \
	&& printf '%s' "$listing" | grep -q 'sudo apt-get install -y git'; then
	pass "install.sh: debian -> apt-get update runs (and is listed) before apt-get install"
else
	flunk "install.sh apt-get update (rc=$rc out=<$out> log=<$(cat "$log")>)"
fi
# non-debian families never run an update
: > "$log"; rm -f "$sandbox/bin/git"
out=$(run "y
"); rc=$?
if ! grep -q 'update' "$log" && ! printf '%s' "$out" | grep -q 'update'; then
	pass "install.sh: fedora -> no package-list refresh"
else
	flunk "install.sh fedora must not update (log=<$(cat "$log")>)"
fi
fake sudo 0; fake git 0

# 16. jq is part of the minimum set on every family when missing
for fam_id in fedora ubuntu arch; do
	printf 'ID=%s\n' "$fam_id" > "$sandbox/os-release-$fam_id"
	rm -f "$sandbox/bin/jq"; : > "$log"
	out=$(RICE_OS_RELEASE="$sandbox/os-release-$fam_id" run "n
"); rc=$?
	if printf '%s' "$out" | grep -qE '(install -y|--noconfirm) .*\bjq\b' && ! printf '%s' "$out" | grep -qE 'git|curl'; then
		pass "install.sh: $fam_id -> jq missing is listed for install"
	else
		flunk "install.sh jq on $fam_id (rc=$rc out=<$out>)"
	fi
done
fake jq 0
# with everything present nothing is installed (case 1 covers it, jq included)
: > "$log"
out=$(run "" --plain); rc=$?
if [ $rc -eq 0 ] && ! grep -q '^sudo' "$log" && ! printf '%s' "$out" | grep -q 'Install these now'; then
	pass "install.sh: everything present (jq too) -> nothing installed"
else
	flunk "install.sh all present with jq (rc=$rc out=<$out>)"
fi

# 17. arch: one form only, pacman -Syu --needed (never -S alone, never -Sy); python3 -> python
printf 'ID=endeavouros\nID_LIKE=arch\n' > "$sandbox/os-release-eos"
rm -f "$sandbox/bin/git"; : > "$log"
out=$(RICE_OS_RELEASE="$sandbox/os-release-eos" run "n
"); rc=$?
if printf '%s' "$out" | grep -q 'sudo pacman -Syu --needed --noconfirm git' && ! printf '%s' "$out" | grep -qE 'pacman -S(y)? '; then
	pass "install.sh: arch derivative -> pacman -Syu --needed"
else
	flunk "install.sh arch form (rc=$rc out=<$out>)"
fi
fake git 0

# 18. artix (ID_LIKE=arch but no systemd) is refused before anything is asked
printf 'ID=artix\nID_LIKE=arch\n' > "$sandbox/os-release-artix"
: > "$log"
out=$(RICE_OS_RELEASE="$sandbox/os-release-artix" run "y
"); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q 'Artix is not supported' && ! grep -q '^sudo' "$log" && ! grep -q '^python3 -m installer' "$log"; then
	pass "install.sh: artix -> refused with a clear line, nothing run"
else
	flunk "install.sh artix (rc=$rc out=<$out>)"
fi

# 11. the hard re-ignore of secret-looking names beats the installer allowlist
touch "$repo/installer/token_x.py"
if git -C "$repo" check-ignore -q installer/token_x.py && ! git -C "$repo" check-ignore -q installer/model.py; then
	pass ".gitignore: installer/token_x.py stays ignored, installer/model.py is tracked"
else
	flunk ".gitignore: allowlist must sit above the hard re-ignore block"
fi
rm -f "$repo/installer/token_x.py"
exit $fail
