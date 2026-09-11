#!/usr/bin/env bash
# rice / rice-apply / rice-rollback behaviour. Uses a fake chezmoi and a
# fake $HOME on PATH — never touches the real environment.
set -u

repo="/home/user/Documentos/Code/dotfiles"
src="$repo/dot_local/bin"
fail=0
pass()  { printf '  ok   %s\n' "$1"; }
flunk() { printf '  FAIL %s\n' "$1"; fail=1; }

# --- sandbox: fake HOME + fake chezmoi on PATH ---------------------------
sandbox=$(mktemp -d)
trap 'rm -rf "$sandbox"' EXIT
mkdir -p "$sandbox/home" "$sandbox/bin"
cp "$src/executable_rice"          "$sandbox/bin/rice"
cp "$src/executable_rice-apply"    "$sandbox/bin/rice-apply"
cp "$src/executable_rice-rollback" "$sandbox/bin/rice-rollback"
chmod +x "$sandbox/bin"/*

# Fake chezmoi: behaviour driven by files under $sandbox.
cat > "$sandbox/bin/chezmoi" <<'FAKE'
#!/usr/bin/env bash
case "$1" in
  status)      cat "$SB/status" 2>/dev/null || true ;;
  diff)        echo "FAKE DIFF" ;;
  apply)       cp -a "$SB/status" "$SB/applied" 2>/dev/null || true ;;
  source-path) echo "$SB/src" ;;
  *)           exit 0 ;;
esac
FAKE
chmod +x "$sandbox/bin/chezmoi"
mkdir -p "$sandbox/src"
git -C "$sandbox/src" init -q
git -C "$sandbox/src" commit -q --allow-empty -m seed

export SB="$sandbox"
export HOME="$sandbox/home"
export XDG_STATE_HOME="$sandbox/home/.local/state"
export PATH="$sandbox/bin:$PATH"

run() { "$sandbox/bin/rice" "$@"; }
bdir="$XDG_STATE_HOME/rice/backup"

# expect <want-rc> <stdout+stderr regex> <label> [rice args...]
expect() {
	local want_rc=$1 re=$2 label=$3; shift 3
	local out got
	out=$(run "$@" 2>&1); got=$?
	if [ "$got" -eq "$want_rc" ] && printf '%s' "$out" | grep -q "$re"; then
		pass "$label"
	else
		flunk "$label (rc=$got want=$want_rc out=<$out>)"
	fi
}

# --- dispatcher --------------------------------------------------------------
expect 2 "usage:"          "bare rice -> usage, exit 2"
expect 0 "usage:"          "rice --help -> usage, exit 0"          --help
expect 2 "unknown command" "unknown command -> exit 2"            bogus
expect 0 "not implemented" "rice doctor -> stub, exit 0"          doctor
expect 0 "^FAKE DIFF$"     "rice diff -> chezmoi diff passthrough" diff
expect 1 "not built yet"   "rice onboard -> not-built, exit 1"    onboard

# --- rice-apply ----------------------------------------------------------
# nothing pending
: > "$sandbox/status"
out=$(run apply 2>&1); rc=$?
if [ $rc -eq 0 ] && [ "$out" = "nothing to apply" ] && [ ! -d "$bdir" ]; then
	pass "apply: nothing pending -> exit 0, no backup"
else
	flunk "apply: nothing pending (rc=$rc out=<$out>)"
fi

# a modify: file exists in $HOME, gets backed up
mkdir -p "$HOME/.config"
printf 'ORIGINAL\n' > "$HOME/.config/foo.toml"
printf 'MM .config/foo.toml\n' > "$sandbox/status"
out=$(run apply -y 2>&1); rc=$?
ts=$(find "$bdir" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | tail -1)
if [ $rc -eq 0 ] \
	&& [ "$(cat "$bdir/$ts/.config/foo.toml")" = "ORIGINAL" ] \
	&& grep -qx '.config/foo.toml' "$bdir/$ts/manifest" \
	&& grep -q '^# source-commit: ' "$bdir/$ts/manifest" \
	&& printf '%s' "$out" | grep -q "rollback: rice rollback $ts"; then
	pass "apply: modify -> file backed up, manifest written"
else
	flunk "apply: modify (rc=$rc ts=$ts out=<$out>)"
fi

# an add: no file in $HOME, recorded in .created only
printf ' A .config/new.toml\n' > "$sandbox/status"
out=$(run apply -y 2>&1); rc=$?
ts2=$(find "$bdir" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | tail -1)
if [ $rc -eq 0 ] && [ "$ts2" != "$ts" ] \
	&& grep -qx '.config/new.toml' "$bdir/$ts2/.created" \
	&& [ ! -e "$bdir/$ts2/.config/new.toml" ]; then
	pass "apply: add -> recorded in .created, nothing backed up"
else
	flunk "apply: add (rc=$rc ts2=$ts2)"
fi

# malformed status -> fail closed
printf 'this is not a status line\n' > "$sandbox/status"
before=$(find "$bdir" -mindepth 1 -maxdepth 1 -type d | wc -l)
out=$(run apply -y 2>&1); rc=$?
after=$(find "$bdir" -mindepth 1 -maxdepth 1 -type d | wc -l)
if [ $rc -eq 1 ] && printf '%s' "$out" | grep -qi "cannot parse" && [ "$before" = "$after" ]; then
	pass "apply: malformed status -> exit 1, no new backup"
else
	flunk "apply: malformed status (rc=$rc out=<$out>)"
fi

# prune to 10
rm -rf "$bdir"; mkdir -p "$bdir"
for n in $(seq -w 1 12); do mkdir -p "$bdir/20200101T0000$n"; done
printf 'MM .config/foo.toml\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1
kept=$(find "$bdir" -mindepth 1 -maxdepth 1 -type d | wc -l)
if [ "$kept" -eq 10 ]; then
	pass "apply: prunes to 10 backups"
else
	flunk "apply: prune (kept $kept)"
fi

# --- rice-rollback round trip ------------------------------------------
rm -rf "$bdir"; mkdir -p "$HOME/.config"
printf 'ORIGINAL\n' > "$HOME/.config/foo.toml"
printf 'MM .config/foo.toml\nA  .config/new.toml\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1

# simulate what `chezmoi apply` would have done to $HOME
printf 'CHANGED\n' > "$HOME/.config/foo.toml"
printf 'brand new\n' > "$HOME/.config/new.toml"

out=$(run rollback -y 2>&1); rc=$?
if [ $rc -eq 0 ] \
	&& [ "$(cat "$HOME/.config/foo.toml")" = "ORIGINAL" ] \
	&& [ ! -e "$HOME/.config/new.toml" ]; then
	pass "rollback: newest backup restores modify + removes create"
else
	flunk "rollback: round trip (rc=$rc out=<$out>)"
fi

expect 1 "no such backup" "rollback: unknown timestamp -> exit 1" rollback 20200101T000000

rm -rf "$bdir"
expect 1 "no backups" "rollback: no backups -> exit 1" rollback -y

exit $fail
