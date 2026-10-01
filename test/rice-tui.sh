#!/usr/bin/env bash
# rice tui: finds the installer through `chezmoi source-path` and runs it; with no
# arguments it opens the TUI only on an interactive terminal (otherwise usage, as before).
set -u
test_dir=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$test_dir/.." && pwd)
fail=0
pass()  { printf '  ok   %s\n' "$1"; }
flunk() { printf '  FAIL %s\n' "$1"; fail=1; }

sandbox=$(mktemp -d)
trap 'rm -rf "${sandbox:?}"' EXIT
mkdir -p "$sandbox/bin" "$sandbox/src/installer"
cp "$repo/dot_local/bin/executable_rice" "$sandbox/bin/rice"
chmod +x "$sandbox/bin/rice"
: > "$sandbox/src/installer/__main__.py"
cat > "$sandbox/bin/chezmoi" <<FAKE
#!/usr/bin/env bash
[ "\$1" = source-path ] && echo "$sandbox/src"
FAKE
cat > "$sandbox/bin/python3" <<'FAKE'
#!/usr/bin/env bash
echo "python3 $* PYTHONPATH=$PYTHONPATH"
FAKE
chmod +x "$sandbox/bin/chezmoi" "$sandbox/bin/python3"
export PATH="$sandbox/bin:$PATH"

out=$(rice tui --plain 2>&1)
if [ "$out" = "python3 -m installer --plain PYTHONPATH=$sandbox/src" ]; then
	pass "rice tui: runs python3 -m installer with the source dir on PYTHONPATH, args passed through"
else
	flunk "rice tui (out=<$out>)"
fi

out=$(rice 2>&1 </dev/null); rc=$?
if [ $rc -eq 2 ] && printf '%s' "$out" | grep -q 'usage: rice'; then
	pass "rice with no args and no terminal: usage, exit 2 (unchanged)"
else
	flunk "rice no-arg without a terminal (rc=$rc out=<$out>)"
fi

rm "$sandbox/src/installer/__main__.py"
out=$(rice tui 2>&1); rc=$?
if [ $rc -eq 1 ] && printf '%s' "$out" | grep -q 'installer not found'; then
	pass "rice tui: clear error when the installer is missing"
else
	flunk "rice tui without installer (rc=$rc out=<$out>)"
fi

if rice help 2>&1 | grep -q '  tui '; then
	pass "rice help lists tui"
else
	flunk "rice help does not list tui"
fi
exit $fail
