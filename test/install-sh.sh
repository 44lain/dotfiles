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
home="$sandbox/home"; mkdir -p "$home/.local/share/chezmoi/.git" "$sandbox/bin"
printf 'ID=fedora\n' > "$sandbox/os-release"
log="$sandbox/calls.log"; : > "$log"

fake() {  # fake <name> <exit-code> [stdout]
	printf '#!/bin/sh\necho "%s $*" >> "%s"\n%s\nexit %s\n' "$1" "$log" "${3:+echo \"$3\"}" "$2" > "$sandbox/bin/$1"
	chmod +x "$sandbox/bin/$1"
}
fake git 0; fake curl 0; fake chezmoi 0; fake python3 0; fake sudo 0
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
exit $fail
