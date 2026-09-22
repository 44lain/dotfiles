#!/usr/bin/env bash
# Wave-4 wallpaper templating check (docs/track-E.md status table): hyprlock
# and hyprpaper are chezmoi-managed, fail loudly without wallpaper_path, and
# hyprpaper's monitor blocks come from .chezmoidata/hosts.toml. Uses a temp
# chezmoi config so it never touches the real ~/.config/chezmoi/chezmoi.toml.
set -u

repo="/home/user/Documentos/Code/dotfiles"
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
managed=$(chezmoi managed)
if printf '%s\n' "$managed" | grep -qx '.config/hypr/hyprlock.conf' \
	&& printf '%s\n' "$managed" | grep -qx '.config/hypr/hyprpaper.conf'; then
	ok "chezmoi manages hyprlock.conf and hyprpaper.conf"
else
	bad "chezmoi does not manage both hyprlock.conf and hyprpaper.conf"
fi

# --- fails loudly without wallpaper_path --------------------------------
out=$(render dot_config/hypr/hyprlock.conf.tmpl ""); rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -qi wallpaper_path; then
	ok "hyprlock.conf.tmpl fails with a wallpaper_path-mentioning error when unset"
else
	bad "hyprlock.conf.tmpl did not fail clearly on empty wallpaper_path: $out"
fi

out=$(render dot_config/hypr/hyprpaper.conf.tmpl ""); rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -qi wallpaper_path; then
	ok "hyprpaper.conf.tmpl fails with a wallpaper_path-mentioning error when unset"
else
	bad "hyprpaper.conf.tmpl did not fail clearly on empty wallpaper_path: $out"
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
