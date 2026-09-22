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
cp "$src/executable_rice"           "$sandbox/bin/rice"
cp "$src/executable_rice-apply"     "$sandbox/bin/rice-apply"
cp "$src/executable_rice-rollback"  "$sandbox/bin/rice-rollback"
cp "$src/executable_rice-uninstall" "$sandbox/bin/rice-uninstall"
chmod +x "$sandbox/bin"/*

# Fake chezmoi: behaviour driven by files under $sandbox.
cat > "$sandbox/bin/chezmoi" <<'FAKE'
#!/usr/bin/env bash
case "$1" in
  status)
    [ ! -f "$SB/status-fail" ] || exit 1
    cat "$SB/status" 2>/dev/null || true ;;
  diff)        echo "FAKE DIFF" ;;
  apply)
    [ ! -f "$SB/apply-fail" ] || exit 1
    cp -a "$SB/status" "$SB/applied" 2>/dev/null || true ;;
  source-path) echo "$SB/src" ;;
  *)           exit 0 ;;
esac
FAKE
chmod +x "$sandbox/bin/chezmoi"

cat > "$sandbox/bin/rice-doctor" <<'FAKE'
#!/usr/bin/env bash
echo "FAKE DOCTOR"
FAKE
chmod +x "$sandbox/bin/rice-doctor"

mkdir -p "$sandbox/src"
git -C "$sandbox/src" init -q
git -C "$sandbox/src" commit -q --allow-empty -m seed

export SB="$sandbox"
export HOME="$sandbox/home"
export XDG_STATE_HOME="$sandbox/home/.local/state"
export PATH="$sandbox/bin:$PATH"

run() { "$sandbox/bin/rice" "$@"; }
bdir="$XDG_STATE_HOME/rice/backup"
bldir="$XDG_STATE_HOME/rice/baseline"

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
expect 0 "uninstall"       "rice --help lists uninstall"           --help
expect 2 "unknown command" "unknown command -> exit 2"            bogus
expect 0 "^FAKE DOCTOR$"   "rice doctor -> delegates to rice-doctor" doctor
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

# a run-only status: chezmoi's `R` code (script will be run) must not be
# treated as unknown/aborting, and must still proceed to apply
printf ' R .chezmoiscripts/run_once_10-example.sh\n' > "$sandbox/status"
out=$(run apply -y 2>&1); rc=$?
if [ $rc -eq 0 ] \
	&& printf '%s' "$out" | grep -q "will run" \
	&& printf '%s' "$out" | grep -q "NOT reversible by rollback" \
	&& ! printf '%s' "$out" | grep -qi "unknown status code"; then
	pass "apply: R status (script) -> previewed, not unknown, proceeds"
else
	flunk "apply: R status (rc=$rc out=<$out>)"
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

# decline the confirmation prompt -> abort, no apply invoked
rm -rf "$bdir"; rm -f "$SB/applied"
printf 'MM .config/foo.toml\n' > "$sandbox/status"
out=$(printf 'n\n' | "$sandbox/bin/rice" apply 2>&1); rc=$?
if [ $rc -eq 1 ] && printf '%s' "$out" | grep -q "aborted" && [ ! -e "$SB/applied" ]; then
	pass "apply: decline prompt -> exit 1 aborted, chezmoi apply never invoked"
else
	flunk "apply: decline prompt (rc=$rc out=<$out>)"
fi

# non-zero `chezmoi status` -> fail closed, no backup dir touched
rm -rf "$bdir"
touch "$SB/status-fail"
out=$(run apply -y 2>&1); rc=$?
rm -f "$SB/status-fail"
if [ $rc -eq 1 ] && printf '%s' "$out" | grep -qi "'chezmoi status' failed" && [ ! -d "$bdir" ]; then
	pass "apply: chezmoi status fails -> exit 1, not applying"
else
	flunk "apply: chezmoi status fails (rc=$rc out=<$out>)"
fi

# non-zero `chezmoi apply` -> exit 1, names the rollback timestamp
rm -rf "$bdir"; rm -f "$SB/applied"
printf 'MM .config/foo.toml\n' > "$sandbox/status"
touch "$SB/apply-fail"
out=$(run apply -y 2>&1); rc=$?
ts3=$(find "$bdir" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | tail -1)
rm -f "$SB/apply-fail"
if [ $rc -eq 1 ] && printf '%s' "$out" | grep -q "rice rollback $ts3" && [ ! -e "$SB/applied" ]; then
	pass "apply: chezmoi apply fails -> exit 1, names rice rollback <ts>"
else
	flunk "apply: chezmoi apply fails (rc=$rc ts3=$ts3 out=<$out>)"
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

# --- rice-apply: baseline capture (docs/track-E.md §3, `rice uninstall`) ---
rm -rf "$bdir" "$bldir" "$HOME/.config"
mkdir -p "$HOME/.config"
printf 'PRE-EXISTING\n' > "$HOME/.config/foo.toml"
printf 'MM .config/foo.toml\n A .config/new.toml\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1
if [ "$(cat "$bldir/files/.config/foo.toml" 2>/dev/null)" = "PRE-EXISTING" ] \
	&& grep -qP '^E\t\.config/foo\.toml$' "$bldir/manifest" \
	&& grep -qP '^C\t\.config/new\.toml$' "$bldir/manifest" \
	&& [ ! -e "$bldir/files/.config/new.toml" ]; then
	pass "apply: baseline records pre-existing (E) and created (C) paths"
else
	flunk "apply: baseline capture (manifest=<$(cat "$bldir/manifest" 2>/dev/null)>)"
fi

# a second apply on a path already in the baseline must not touch its
# recorded pre-rice content, even though the file has since changed
printf 'CHANGED-BY-RICE\n' > "$HOME/.config/foo.toml"
printf 'MM .config/foo.toml\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1
if [ "$(cat "$bldir/files/.config/foo.toml")" = "PRE-EXISTING" ] \
	&& [ "$(grep -c '\.config/foo\.toml$' "$bldir/manifest")" -eq 1 ]; then
	pass "apply: baseline does not re-capture an already-recorded path"
else
	flunk "apply: baseline re-capture (content=<$(cat "$bldir/files/.config/foo.toml")>)"
fi

# a genuinely new path (later commit adds a package) extends the baseline
printf 'MM .config/foo.toml\n A .config/brand-new-pkg.toml\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1
if grep -qP '^C\t\.config/brand-new-pkg\.toml$' "$bldir/manifest"; then
	pass "apply: baseline grows for a path never seen before"
else
	flunk "apply: baseline growth"
fi

# a path that is a *substring* of an already-recorded one must still get
# its own baseline entry — a plain (unanchored) grep would wrongly treat
# ".config/app" as already-recorded because of an existing
# ".config/app-extra" line and silently never capture it
mkdir -p "$HOME/.config"
printf 'MM .config/foo.toml\n A .config/app-extra\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1
printf 'MM .config/foo.toml\n A .config/app\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1
if grep -qP '^C\t\.config/app$' "$bldir/manifest"; then
	pass "apply: baseline entry for one path is not shadowed by a superstring sibling"
else
	flunk "apply: baseline substring collision (manifest=<$(cat "$bldir/manifest")>)"
fi

# --- rice-uninstall ------------------------------------------------------
rm -rf "$bdir" "$bldir" "$HOME/.config"
expect 0 "nothing to uninstall" "uninstall: no baseline -> exit 0, no-op" uninstall

mkdir -p "$HOME/.config"
printf 'PRE-RICE\n' > "$HOME/.config/foo.toml"
printf 'MM .config/foo.toml\n A .config/new.toml\n A .bashrc.d\n A .bashrc.d/10-path.sh\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1
# simulate what chezmoi apply did to $HOME since
printf 'RICED\n' > "$HOME/.config/foo.toml"
printf 'created by rice\n' > "$HOME/.config/new.toml"
mkdir -p "$HOME/.bashrc.d"
printf 'echo hi\n' > "$HOME/.bashrc.d/10-path.sh"

out=$(run uninstall -y 2>&1); rc=$?
if [ $rc -eq 0 ] \
	&& [ "$(cat "$HOME/.config/foo.toml")" = "PRE-RICE" ] \
	&& [ ! -e "$HOME/.config/new.toml" ] \
	&& [ ! -e "$HOME/.bashrc.d" ] \
	&& [ ! -d "$bldir" ]; then
	pass "uninstall: restores pre-rice content, deletes created paths, clears baseline"
else
	flunk "uninstall: full round trip (rc=$rc out=<$out>)"
fi

# decline the confirmation prompt -> abort, nothing changed, baseline kept
rm -rf "$bdir" "$bldir" "$HOME/.config"
mkdir -p "$HOME/.config"
printf 'PRE-RICE\n' > "$HOME/.config/foo.toml"
printf 'MM .config/foo.toml\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1
printf 'RICED\n' > "$HOME/.config/foo.toml"
out=$(printf 'n\n' | "$sandbox/bin/rice" uninstall 2>&1); rc=$?
if [ $rc -eq 1 ] && printf '%s' "$out" | grep -q "aborted" \
	&& [ "$(cat "$HOME/.config/foo.toml")" = "RICED" ] \
	&& [ -d "$bldir" ]; then
	pass "uninstall: decline prompt -> exit 1 aborted, nothing changed"
else
	flunk "uninstall: decline prompt (rc=$rc out=<$out>)"
fi

# after a real uninstall, a fresh apply must start capturing a new baseline
rm -rf "$bdir" "$bldir" "$HOME/.config"
mkdir -p "$HOME/.config"
printf 'V1\n' > "$HOME/.config/foo.toml"
printf 'MM .config/foo.toml\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1
run uninstall -y >/dev/null 2>&1
printf 'V2\n' > "$HOME/.config/foo.toml"
printf 'MM .config/foo.toml\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1
if [ "$(cat "$bldir/files/.config/foo.toml" 2>/dev/null)" = "V2" ]; then
	pass "uninstall: baseline restarts fresh after a full uninstall"
else
	flunk "uninstall: baseline restart (content=<$(cat "$bldir/files/.config/foo.toml" 2>/dev/null)>)"
fi

# --- rice-rollback round trip ------------------------------------------
rm -rf "$bdir"; mkdir -p "$HOME/.config"
printf 'ORIGINAL\n' > "$HOME/.config/foo.toml"
printf 'MM .config/foo.toml\n A .config/new.toml\n' > "$sandbox/status"
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

# backup dir exists but has no manifest -> exit 1, clear message
rm -rf "$bdir"; mkdir -p "$bdir/20200101T000000"
expect 1 "no manifest" "rollback: backup dir with no manifest -> exit 1" rollback 20200101T000000

# --- rice-rollback: directories in .created (Critical #1) ---------------
# chezmoi status emits directory entries too (parent before child); a plain
# `rm -f` on a directory fails and, under set -e, aborts the whole rollback
# before anything is deleted.
rm -rf "$bdir" "$HOME/.bashrc.d"
printf ' A .bashrc.d\n A .bashrc.d/10-path.sh\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1
# simulate what `chezmoi apply` would have created in $HOME
mkdir -p "$HOME/.bashrc.d"
printf 'echo hi\n' > "$HOME/.bashrc.d/10-path.sh"
out=$(run rollback -y 2>&1); rc=$?
if [ $rc -eq 0 ] && [ ! -e "$HOME/.bashrc.d" ]; then
	pass "rollback: directory in .created -> both dir and child removed"
else
	flunk "rollback: directory in .created (rc=$rc out=<$out>)"
fi

# --- rice-rollback: directory manifest entry (Critical #2) ---------------
# `cp -a` into an existing directory nests the backup inside it instead of
# restoring in place; `cp -aT` must be used so the destination is unambiguous.
rm -rf "$bdir" "$HOME/.bashrc.d"
mkdir -p "$HOME/.bashrc.d"
printf 'ORIGINAL-10\n' > "$HOME/.bashrc.d/10-path.sh"
printf 'MM .bashrc.d\n' > "$sandbox/status"
run apply -y >/dev/null 2>&1
# simulate what `chezmoi apply` would have done to the directory's contents
printf 'CHANGED-10\n' > "$HOME/.bashrc.d/10-path.sh"
printf 'NEW-FILE\n' > "$HOME/.bashrc.d/99-new.sh"
out=$(run rollback -y 2>&1); rc=$?
if [ $rc -eq 0 ] \
	&& [ "$(cat "$HOME/.bashrc.d/10-path.sh" 2>/dev/null)" = "ORIGINAL-10" ] \
	&& [ ! -e "$HOME/.bashrc.d/.bashrc.d" ]; then
	pass "rollback: directory manifest entry restores in place, no self-nesting"
else
	flunk "rollback: directory manifest entry (rc=$rc out=<$out>)"
fi

rm -rf "$bdir"
expect 1 "no backups" "rollback: no backups -> exit 1" rollback -y

exit $fail
