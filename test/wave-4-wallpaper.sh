#!/usr/bin/env bash
# Wave-4 wallpaper templating check (docs/track-E.md status table): hyprlock
# and hyprpaper are chezmoi-managed, render fine without wallpaper_path (it is
# optional), and hyprpaper's monitor blocks come from .chezmoidata/hosts.toml. Uses a temp
# chezmoi config so it never touches the real ~/.config/chezmoi/chezmoi.toml.
set -u

repo="$(cd "$(dirname "$0")/.." && pwd)"
fail=0
ok()  { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fail=1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

render() { # render <tmpl-relpath> <wallpaper_path>
	cat > "$tmp/chezmoi.toml" <<-EOF
	sourceDir = "$repo"
	[data]
	    profile = "personal"
	    host = "desktop"
	    wallpaper_path = "$2"
	EOF
	chezmoi execute-template -f "$repo/$1" --config "$tmp/chezmoi.toml" 2>&1
}

# --- managed -----------------------------------------------------------
render dot_config/hypr/hyprlock.conf.tmpl "" >/dev/null   # writes $tmp/chezmoi.toml
managed=$(chezmoi managed --source "$repo" --config "$tmp/chezmoi.toml")
if printf '%s\n' "$managed" | grep -qx '.config/hypr/hyprlock.conf' \
	&& printf '%s\n' "$managed" | grep -qx '.config/hypr/hyprpaper.conf'; then
	ok "chezmoi manages hyprlock.conf and hyprpaper.conf"
else
	bad "chezmoi does not manage both hyprlock.conf and hyprpaper.conf"
fi

# --- wallpaper_path is optional -----------------------------------------
out=$(render dot_config/hypr/hyprlock.conf.tmpl ""); rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q 'color = ' \
	&& ! printf '%s' "$out" | grep -q 'path ='; then
	ok "hyprlock.conf.tmpl renders a solid background when wallpaper_path is unset"
else
	bad "hyprlock.conf.tmpl did not render cleanly on empty wallpaper_path: $out"
fi

out=$(render dot_config/hypr/hyprpaper.conf.tmpl ""); rc=$?
if [ "$rc" -eq 0 ] && ! printf '%s' "$out" | grep -q 'wallpaper {'; then
	ok "hyprpaper.conf.tmpl renders no wallpaper blocks when wallpaper_path is unset"
else
	bad "hyprpaper.conf.tmpl did not render cleanly on empty wallpaper_path: $out"
fi

# --- renders the set path -----------------------------------------------
out=$(render dot_config/hypr/hyprlock.conf.tmpl "/tmp/test-wall.jpg"); rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qF "/tmp/test-wall.jpg"; then
	ok "hyprlock.conf.tmpl renders the configured wallpaper_path"
else
	bad "hyprlock.conf.tmpl did not render wallpaper_path: $out"
fi

# --- hyprpaper monitors come from hosts.toml ----------------------------
out=$(render dot_config/hypr/hyprpaper.conf.tmpl "/tmp/test-wall.jpg")
if printf '%s' "$out" | grep -q 'monitor = DP-1' \
	&& printf '%s' "$out" | grep -q 'monitor = HDMI-A-1'; then
	ok "hyprpaper.conf.tmpl generates a wallpaper block per host monitor"
else
	bad "hyprpaper.conf.tmpl did not generate per-monitor blocks: $out"
fi

exit $fail
