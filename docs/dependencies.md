# Dependencies

Everything this rice assumes is already on the system, by distro. `chezmoi`
and `git` are the only things applying this repo itself needs — this list is
for the *result* of applying it to actually work.

Support: **Fedora** with Hyprland 0.56+ is what this was built on and is the
only verified column. **Arch** is planned (the package names below are listed
but untested — adding it officially means testing them on a real install).
Debian/Ubuntu is not supported (no Hyprland in stable); that column is a
best-effort guess. If a name is wrong, it's a docs bug, not a hidden
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
| xdg-user-dirs (`xdg-user-dir`: screenshot and yt-x download folders) | `xdg-user-dirs` | `xdg-user-dirs` | `xdg-user-dirs` |
| xdg-utils (`xdg-open`, `xdg-settings`: default file manager / browser) | `xdg-utils` | `xdg-utils` | `xdg-utils` |
| xrandr (only if `primary_monitor` is set for your host) | `xrandr` | `x11-xserver-utils` | `xorg-xrandr` |

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

## Browser (`SUPER+B`) and file manager (`SUPER+E`)

Both are per-host settings in `.chezmoidata/hosts.toml` (`browser`,
`file_manager`). Left unset they fall back to your system's default browser
and `xdg-open $HOME` (so any file manager registered for directories). The
maintainer's own host sets `browser = "zen"` — [Zen Browser](https://zen-browser.app/),
which no distro packages officially (AppImage, the Flatpak `app.zen_browser.zen`,
or the AUR `zen-browser-bin`). You don't need it.

## Power menu (`SUPER+O`, then `E`)

`~/.local/bin/powermenu` (shipped in this repo) is a five-entry rofi menu
(lock / logout / suspend / reboot / poweroff) — needs `rofi`, already listed
above.

## yt-x (terminal YouTube browser) — optional

Only needed if you actually use `yt-x` (see
[docs/yt-x.md](yt-x.md)). Fedora: `sudo dnf install mpv yt-dlp vlc fzf jq`
(rofi already covered above); Debian/Arch: the same package names under
`apt`/`pacman` should work. `yt-x` itself is a single script, not
packaged anywhere — installed by hand per docs/yt-x.md.

## CS2 tuning (`bin/executable_cs2-mode.sh`, `profile=personal` only)

Assumes Steam + Counter-Strike 2 already installed; the script itself has
no extra package dependency beyond that.

## `rice onboard` and secrets — optional

Neither is required to apply this repo — `rice onboard` falls back to
plain `read` prompts without `gum`, and `age` is only needed for the
`profile=personal` secrets example (§4 of `docs/track-E.md`). Both are
checked by `rice onboard` itself, which prints the install line rather
than failing silently if either is missing.

| What | Fedora (`dnf`) | Debian/Ubuntu (`apt`) | Arch (`pacman`) |
| ---- | --------------- | ---------------------- | ---------------- |
| gum (nicer `rice onboard` prompts) | `gum` | not in stable repos — the [charm apt repo](https://github.com/charmbracelet/gum#installation) | `gum` |
| age (secrets, `profile=personal` only) | `age` | `age` | `age` |

## Dev tooling for this repo (not applied to your `$HOME`)

`make test` needs `chezmoi` (already required) and, optionally, `luajit`
(Fedora: `sudo dnf install luajit`) to syntax-check the rendered Lua.

`make check` needs `shellcheck` and `gitleaks` — Fedora: `sudo dnf install
shellcheck` (`gitleaks` isn't in Fedora's repos, grab a release binary
from [gitleaks' releases page](https://github.com/gitleaks/gitleaks/releases)).
Debian/Arch: `shellcheck` is packaged (`apt`/`pacman`); `gitleaks` is on
the AUR, otherwise the same release-binary approach as Fedora.
