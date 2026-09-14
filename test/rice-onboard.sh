#!/usr/bin/env bash
# rice-onboard behaviour (docs/track-E.md §5). Fakes chezmoi, hyprctl,
# localectl, lspci on PATH; deliberately no fake `gum`, so every run
# exercises the plain-`read` fallback. Never touches the real environment.
set -u

# Use the directory this script is in (worktree), falling back to main repo if needed
test_dir=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$test_dir/.." && pwd)
src="$repo/dot_local/bin"
fail=0
pass()  { printf '  ok   %s\n' "$1"; }
flunk() { printf '  FAIL %s\n' "$1"; fail=1; }

sandbox=$(mktemp -d)
trap 'rm -rf "${sandbox:?}"' EXIT
mkdir -p "$sandbox/home" "$sandbox/bin" "$sandbox/src/.chezmoidata"
cp "$src/executable_rice"         "$sandbox/bin/rice"
cp "$src/executable_rice-apply"   "$sandbox/bin/rice-apply"
cp "$src/executable_rice-onboard" "$sandbox/bin/rice-onboard"
chmod +x "$sandbox/bin"/*

cat > "$sandbox/src/.chezmoidata/hosts.toml" <<'EOF'
[hosts.desktop]
kb_layout = "us,br"
scale     = 1
monitors  = [
  { output = "DP-1", mode = "1920x1080@144", position = "0x0", scale = 1 },
]
gpu_env = { LIBVA_DRIVER_NAME = "nvidia" }
EOF

cat > "$sandbox/bin/chezmoi" <<'FAKE'
#!/usr/bin/env bash
case "$1" in
  status)      cat "$SB/status" 2>/dev/null || true ;;
  apply)       cp -a "$SB/status" "$SB/applied" 2>/dev/null || true ;;
  source-path) echo "$SB/src" ;;
  data)        cat "$SB/data.json" 2>/dev/null || echo '{"hosts":{}}' ;;
  init)
    touch "$SB/chezmoi-init-called"
    mkdir -p "$HOME/.config/chezmoi"
    printf '[data]\n    profile = "guest"\n    host    = "desktop"\n\n[git]\n    autoCommit = false\n' \
      > "$HOME/.config/chezmoi/chezmoi.toml" ;;
  *)           exit 0 ;;
esac
FAKE
chmod +x "$sandbox/bin/chezmoi"

cat > "$sandbox/bin/hyprctl" <<'FAKE'
#!/usr/bin/env bash
if [ "$1 $2" = "monitors -j" ]; then cat "$SB/hyprctl-monitors.json" 2>/dev/null || echo '[]'; fi
FAKE
cat > "$sandbox/bin/localectl" <<'FAKE'
#!/usr/bin/env bash
cat "$SB/localectl-status" 2>/dev/null
FAKE
cat > "$sandbox/bin/lspci" <<'FAKE'
#!/usr/bin/env bash
cat "$SB/lspci-output" 2>/dev/null
FAKE
chmod +x "$sandbox/bin/hyprctl" "$sandbox/bin/localectl" "$sandbox/bin/lspci"

export SB="$sandbox"
export XDG_STATE_HOME="$sandbox/home/.local/state"
export PATH="$sandbox/bin:$PATH"
run() { HOME="$sandbox/home" "$sandbox/bin/rice" "$@"; }

# --- 1. missing chezmoi + git -> exit 1, names both, before any prompt ---
emptybin=$(mktemp -d)
ln -s "$(command -v bash)" "$emptybin/bash"
out=$(PATH="$emptybin" HOME="$sandbox/home" "$sandbox/bin/rice-onboard" 2>&1); rc=$?
rm -rf "${emptybin:?}"
if [ $rc -eq 1 ] && printf '%s' "$out" | grep -q chezmoi && printf '%s' "$out" | grep -q git; then
	pass "onboard: missing chezmoi+git -> exit 1, names both"
else
	flunk "onboard: missing deps (rc=$rc out=<$out>)"
fi

# --- 2. happy path: personal, new host, full detection ------------------
rm -rf "${sandbox:?}/home"; mkdir -p "$sandbox/home"
: > "$sandbox/status"   # rice apply at the end: nothing pending
printf '{"hosts":{"desktop":{},"pentest":{}}}' > "$SB/data.json"
printf '   X11 Layout: us,br\n' > "$SB/localectl-status"
printf '01:00.0 VGA compatible controller: NVIDIA Corporation TU116 [GeForce GTX 1660 SUPER]\n' > "$SB/lspci-output"
cat > "$SB/hyprctl-monitors.json" <<'EOF'
[ {"name":"DP-1","width":1920,"height":1080,"refreshRate":143.981,"x":0,"y":0,"scale":1.0} ]
EOF
answers=$'91384441+44lain@users.noreply.github.com\npersonal\nnew\nlaptop\n\n\ny\n'
out=$(printf '%s' "$answers" | run onboard 2>&1); rc=$?
cfg="$sandbox/home/.config/chezmoi/chezmoi.toml"
hosts_file="$sandbox/src/.chezmoidata/hosts.toml"
if [ $rc -eq 0 ] \
	&& [ -f "$SB/chezmoi-init-called" ] \
	&& printf '%s' "$out" | grep -qi "age" \
	&& [ "$(git config -f "$sandbox/home/.config/git/local" --get user.email)" = "91384441+44lain@users.noreply.github.com" ] \
	&& grep -q '^\[hosts\.laptop\]$' "$hosts_file" \
	&& grep -q '^kb_layout = "us,br"$' "$hosts_file" \
	&& grep -qE '^\s*\{ output = "DP-1", mode = "1920x1080@143",' "$hosts_file" \
	&& grep -q '^    profile = "personal"$' "$cfg" \
	&& grep -q '^    host    = "laptop"$' "$cfg"; then
	pass "onboard: personal+new host -> init, email, hosts.toml, config all correct"
else
	flunk "onboard: happy path (rc=$rc out=<$out>)"
fi

# --- 3. guest + new host -> local chezmoi.toml only, repo untouched -----
rm -rf "${sandbox:?}/home"; mkdir -p "$sandbox/home"
before_hosts=$(cat "$hosts_file")
answers=$'nobody@example.com\nguest\nnew\nguestbox\n\n\nn\n'
out=$(printf '%s' "$answers" | run onboard 2>&1); rc=$?
cfg="$sandbox/home/.config/chezmoi/chezmoi.toml"
if [ $rc -eq 0 ] \
	&& grep -q '^\[data\.hosts\.guestbox\]$' "$cfg" \
	&& grep -q '^    profile = "guest"$' "$cfg" \
	&& grep -q '^    host    = "guestbox"$' "$cfg" \
	&& [ "$(cat "$hosts_file")" = "$before_hosts" ]; then
	pass "onboard: guest+new host -> local config only, repo hosts.toml untouched"
else
	flunk "onboard: guest+new host (rc=$rc out=<$out>)"
fi

# --- 4. existing host picked -> no detection, config updated only -------
rm -rf "${sandbox:?}/home"; mkdir -p "$sandbox/home"
before_hosts=$(cat "$hosts_file")
answers=$'x@example.com\npersonal\npentest\n'
out=$(printf '%s' "$answers" | run onboard 2>&1); rc=$?
cfg="$sandbox/home/.config/chezmoi/chezmoi.toml"
if [ $rc -eq 0 ] \
	&& grep -q '^    host    = "pentest"$' "$cfg" \
	&& [ "$(cat "$hosts_file")" = "$before_hosts" ]; then
	pass "onboard: existing host -> no new block, no detection prompts consumed"
else
	flunk "onboard: existing host (rc=$rc out=<$out>)"
fi

exit $fail
