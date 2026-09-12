# Dependencies

Everything this rice assumes is already on the system, by distro. `chezmoi`
and `git` are the only things `chezmoi init --apply` itself needs — this
list is for the *result* of applying it to actually work.

Honesty check: this was built and is only really verified on **Fedora**
(the `desktop` host). Debian/Ubuntu and Arch columns are best-effort —
package names that should be right based on each distro's usual naming,
not something tested here. If one's wrong, it's a docs bug, not a hidden
requirement — open an issue or just fix it and send a PR.

## Compositor & session

| What | Fedora (`dnf`) | Debian/Ubuntu (`apt`) | Arch (`pacman`) |
| ---- | --------------- | ---------------------- | ---------------- |
| Hyprland | `hyprland` | not in stable repos as of writing — check `testing`/`sid`, or build from source | `hyprland` |
| hypridle | `hypridle` | same caveat as Hyprland | `hypridle` |
| hyprlock | `hyprlock` | same caveat | `hyprlock` |
| hyprpaper *(fallback only — grootshell draws the wallpaper day to day)* | `hyprpaper` | same caveat | `hyprpaper` |
| uwsm (session manager, wraps every autostart app) | `uwsm` | same caveat | `uwsm` |
| Hyprland's polkit agent | `hyprpolkitagent` | same caveat | `hyprpolkitagent` (AUR) |

## Bar / theming (grootshell — not in this repo)

`hyprland.lua` autostarts a Quickshell config called `grootshell`, which is
**not part of this repo** (see
[docs/hyprland-wallpaper-and-theming.md](hyprland-wallpaper-and-theming.md)
for why). Without it there's no bar, no notifications, no wallpaper —
Hyprland itself still starts fine.

| What | Fedora (`dnf`) | Debian/Ubuntu (`apt`) | Arch (`pacman`) |
| ---- | --------------- | ---------------------- | ---------------- |
| Quickshell | COPR: `sudo dnf copr enable errornointernet/quickshell && sudo dnf install quickshell` | build from source (no known packaging) | `quickshell` (AUR) |
| matugen (wallpaper → colour palette) | not packaged — `cargo install matugen` (needs Rust/`cargo`) | same, `cargo install matugen` | `matugen` (AUR) |

## Terminal & tools

| What | Fedora (`dnf`) | Debian/Ubuntu (`apt`) | Arch (`pacman`) |
| ---- | --------------- | ---------------------- | ---------------- |
| kitty | `kitty` | `kitty` | `kitty` |
| yazi | `yazi` | not in stable repos — see [yazi's own install docs](https://yazi-rs.github.io/docs/installation) | `yazi` |
| starship | `starship` | `starship` (or the installer at starship.rs) | `starship` |
| dolphin (file manager, `SUPER+E`) | `dolphin` | `dolphin` | `dolphin` |
| rofi (launcher fallback for clipboard) | `rofi` | `rofi` | `rofi` |

Yazi's `z`/`Z` keymap needs two of its own plugins on top of the package
itself: `ya pack -a yazi-rs/plugins:zoxide yazi-rs/plugins:fzf` — which in
turn need `zoxide` and `fzf` (see the clipboard/screenshot table below,
`fzf` is already there for clipboard).

## Clipboard & screenshots

| What | Fedora (`dnf`) | Debian/Ubuntu (`apt`) | Arch (`pacman`) |
| ---- | --------------- | ---------------------- | ---------------- |
| cliphist | `cliphist` | not in stable repos — static binary from [upstream releases](https://github.com/sentriz/cliphist) | `cliphist` (AUR) |
| wl-clipboard (`wl-copy`/`wl-paste`) | `wl-clipboard` | `wl-clipboard` | `wl-clipboard` |
| grim + slurp (screenshots) | `grim slurp` | `grim slurp` | `grim slurp` |
| jq | `jq` | `jq` | `jq` |
| libnotify (`notify-send`) | `libnotify` | `libnotify-bin` | `libnotify` |
| rofi + fzf (clipboard picker fallback, also yazi's `Z`) | `rofi fzf` | `rofi fzf` | `rofi fzf` |
| zoxide (yazi's `z`) | `zoxide` | `zoxide` | `zoxide` |

## Media / audio

| What | Fedora (`dnf`) | Debian/Ubuntu (`apt`) | Arch (`pacman`) |
| ---- | --------------- | ---------------------- | ---------------- |
| playerctl | `playerctl` | `playerctl` | `playerctl` |
| WirePlumber (`wpctl`) | usually already pulled in with a PipeWire desktop; else `wireplumber` | `wireplumber` | `wireplumber` |

## System tray / hardware

| What | Fedora (`dnf`) | Debian/Ubuntu (`apt`) | Arch (`pacman`) |
| ---- | --------------- | ---------------------- | ---------------- |
| NetworkManager applet (`nm-applet`) | `network-manager-applet` | `network-manager-gnome` | `network-manager-applet` |
| Blueman | `blueman` | `blueman` | `blueman` |
| KDE Connect | `kdeconnectd` | `kdeconnect` | `kdeconnect` |

## Window-rule targets (only if you actually use them — Hyprland doesn't need these to run)

`hyprland.lua`'s window rules float/centre a few specific apps. None of
these are required — they're just what a rule matches *if* it's running:
`pavucontrol`, `blueman-manager` (comes with Blueman above),
`nm-connection-editor` (comes with the NetworkManager applet package
above), a polkit-kde auth agent (`org.kde.polkit-kde-authentication-agent-1`
— pulled in by most KDE/Plasma installs), `spectacle` (KDE's screenshot
tool — kept as a rule from before the grim/slurp switch, not actually
used to take screenshots under Hyprland), and `xdg-desktop-portal-gtk`
(GTK file-picker portal, needed for browser file dialogs under Wayland).

## Browser (`SUPER+B`)

`hyprland.lua` execs `zen` — [Zen Browser](https://zen-browser.app/). Not
in any distro's official repos on any of the three; install the AppImage,
the Flatpak (`app.zen_browser.zen`), or the AUR package
(`zen-browser-bin`).

## yt-x (terminal YouTube browser) — optional

Only needed if you actually use `yt-x` (see
[docs/yt-x.md](yt-x.md)). Fedora: `sudo dnf install mpv yt-dlp vlc fzf jq`
(rofi already covered above); Debian/Arch: the same package names under
`apt`/`pacman` should work. `yt-x` itself is a single script, not
packaged anywhere — installed by hand per docs/yt-x.md.

## CS2 tuning (`bin/executable_cs2-mode.sh`, `profile=personal` only)

Assumes Steam + Counter-Strike 2 already installed; the script itself has
no extra package dependency beyond that.

## Dev tooling for this repo (not applied to your `$HOME`)

`make check` needs `shellcheck` and `gitleaks` — Fedora: `sudo dnf install
shellcheck` (`gitleaks` isn't in Fedora's repos, grab a release binary
from [gitleaks' releases page](https://github.com/gitleaks/gitleaks/releases)).
Debian/Arch: `shellcheck` is packaged (`apt`/`pacman`); `gitleaks` is on
the AUR, otherwise the same release-binary approach as Fedora.
