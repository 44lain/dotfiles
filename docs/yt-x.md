# yt-x

[yt-x](https://github.com/Benexl/yt-x) — browse and play YouTube (and other
yt-dlp sites) from the terminal, playback in mpv. Package: `yt-x`
(`yt-x/.config/yt-x/config`), desktop only.

Session that produced this: 2026-09-07. Host: `desktop` (Fedora 43), now on
Hyprland, kitty terminal, Zen Browser.

## What Stow does and doesn't do

`make desktop` symlinks `~/.config/yt-x/config` into this repo. On a host that
already has a real `~/.config/yt-x/config` (like `desktop` at the time this was
added), stow reports a conflict — adopt it once:

```bash
stow --adopt yt-x && git -C ~/Documentos/Code/dotfiles checkout -- yt-x
```

Stow does **not**:

- install the `yt-x` script or its dependencies
- create the Zen Browser profile symlink (see below)

## Install (not automated here)

```bash
sudo dnf install -y mpv yt-dlp vlc fzf jq        # rofi already present
curl -fL https://github.com/Benexl/yt-x/releases/latest/download/yt-x \
  -o ~/.local/bin/yt-x && chmod +x ~/.local/bin/yt-x
```

`~/.local/bin` is already on PATH via the `environment.d` package. Optional:
`chafa` (image preview fallback for non-kitty terminals).

Bash/zsh completions are not implemented upstream (fish only) — nothing to
install for this host.

## Config choices baked in

| Key | Value | Why |
| --- | --- | --- |
| `CONFIG_IMAGE_RENDERER` | `icat` | kitty native (`kitten icat`); best thumbnail quality |
| `CONFIG_ENABLE_PREVIEW*` | `true` | title/channel/views/date + thumbnail in the fzf pane |
| `CONFIG_DISOWN_PLAYER` | `true` | mpv detaches, terminal stays free |
| `CONFIG_DOWNLOAD_DIR` | `$HOME/Vídeos/yt-x` | matches `XDG_VIDEOS_DIR` (pt_BR, accented) |
| `CONFIG_DOWNLOADS_ENUMERATE` | `true` | numeric prefix on downloaded files |
| `CONFIG_FZF_OPTS` | Tokyo Night + extra `--bind` | `ctrl-/` is flaky under kitty's keyboard protocol, so `alt-p` and `f2` also toggle the preview |

## Zen Browser cookies (the subscriptions feed / age-restricted / members)

yt-dlp has no `zen` value for `--cookies-from-browser`. Zen is a Firefox fork,
so its `cookies.sqlite` is readable by the Firefox parser — but the Flatpak
profile path contains spaces and parentheses
(`.../povbvcqv.Default (release)/`), and yt-x expands `CONFIG_BROWSER`
unquoted. Fix: a space-free symlink.

```bash
ln -sfn "$(printf '%s' "$HOME"/.var/app/app.zen_browser.zen/.zen/*.Default*)" \
        "$HOME/.local/share/yt-x-zen-profile"
```

(adjust the glob if the profile dir name differs — check
`~/.var/app/app.zen_browser.zen/.zen/`). `CONFIG_BROWSER` then points at
`firefox:$HOME/.local/share/yt-x-zen-profile`.

You must be **logged into YouTube in Zen** for this to do anything — yt-x only
reads existing cookies, it does not log in. Verify:

```bash
yt-dlp --cookies-from-browser "firefox:$HOME/.local/share/yt-x-zen-profile" \
  --flat-playlist --playlist-items 1-5 \
  -O "%(uploader)s | %(title)s" "https://www.youtube.com/feed/subscriptions"
```

Set `CONFIG_BROWSER=""` to disable cookie access entirely (public videos only).
