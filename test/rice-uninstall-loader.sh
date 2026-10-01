#!/usr/bin/env bash
# rice-uninstall removes the ~/.bashrc loader that rice-onboard appended (marked
# block + state file), asks first, and never touches an unmarked ~/.bashrc.
set -u
test_dir=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$test_dir/.." && pwd)
fail=0
pass()  { printf '  ok   %s\n' "$1"; }
flunk() { printf '  FAIL %s\n' "$1"; fail=1; }

sandbox=$(mktemp -d)
trap 'rm -rf "${sandbox:?}"' EXIT
export HOME="$sandbox/home" XDG_STATE_HOME="$sandbox/home/.local/state"
mkdir -p "$HOME" "$XDG_STATE_HOME/rice"
uninstall="$repo/dot_local/bin/executable_rice-uninstall"

block() {
	printf '# stock bashrc\n\n# >>> rice bashrc.d loader >>>\n# Load ~/.bashrc.d fragments (managed by dotfiles)\nif [ -d ~/.bashrc.d ]; then :; fi\n# <<< rice bashrc.d loader <<<\nalias keep=1\n' > "$HOME/.bashrc"
	: > "$XDG_STATE_HOME/rice/bashrc-loader"
}

block
out=$(printf 'y\n' | bash "$uninstall" 2>&1)
if ! grep -q 'rice bashrc.d loader' "$HOME/.bashrc" && grep -q '^alias keep=1$' "$HOME/.bashrc" \
	&& grep -q '^# stock bashrc$' "$HOME/.bashrc" && [ ! -e "$XDG_STATE_HOME/rice/bashrc-loader" ]; then
	pass "uninstall: answered y -> marked loader removed, the rest of ~/.bashrc kept"
else
	flunk "uninstall loader removal (out=<$out>)"
fi

block
printf 'n\n' | bash "$uninstall" >/dev/null 2>&1
if grep -q '>>> rice bashrc.d loader >>>' "$HOME/.bashrc"; then
	pass "uninstall: answered n -> loader kept"
else
	flunk "uninstall: removed the loader after n"
fi

block
bash "$uninstall" --yes >/dev/null 2>&1
if ! grep -q 'rice bashrc.d loader' "$HOME/.bashrc"; then
	pass "uninstall: --yes removes the loader without asking"
else
	flunk "uninstall --yes did not remove the loader"
fi

printf '# my bashrc\nif [ -d ~/.bashrc.d ]; then :; fi\n' > "$HOME/.bashrc"
rm -f "$XDG_STATE_HOME/rice/bashrc-loader"
before=$(cat "$HOME/.bashrc")
bash "$uninstall" --yes >/dev/null 2>&1
if [ "$(cat "$HOME/.bashrc")" = "$before" ]; then
	pass "uninstall: an unmarked/user-written loader is never touched"
else
	flunk "uninstall touched a loader it did not add"
fi
exit $fail
