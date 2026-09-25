# Dependencies

Everything this rice assumes is already on the system, by distro. `chezmoi`
and `git` are the only things applying this repo itself needs — this list is
for the *result* of applying it to actually work.

Support: **Fedora** and **Debian-family** distros (Debian, Ubuntu, Linux Mint,
Kali, Parrot, Pop!_OS, …) with Hyprland **0.55 or newer**. **Arch** is planned:
its package names are listed but untested. `rice doctor` reads the same data
as the tables below and prints the exact install command for *your* distro,
so you usually do not need to read this file at all.

Debian-family notes:

- **"backports"** is an official second repository with newer versions of some
  packages. Stable releases (Debian 13, Parrot 7) keep an old Hyprland in the
  main repository and the usable one in backports. apt does not use backports
  on its own; you ask for it with `-t <suite>`. `rice doctor` finds the right
  suite from apt itself and prints the full command — you never type a
  distro codename. Stock Debian 13 needs backports enabled first (the
  Hyprland row below says how); Parrot already has it.
- Some releases have **no** usable Hyprland at all (Debian 12, Ubuntu 24.04
  LTS). `rice doctor` says so. Options: a newer release, or build Hyprland from
  source following its upstream instructions; everything else here works the
  same afterwards.
- Which distros are actually checked: package names are verified against
  Debian 13 (with backports), Parrot 7 and Fedora 43 on every
  `make distro-check`; for Arch the names resolve in its repositories but no
  install has been run. A stranger's first apply is exercised on Debian 13,
  Ubuntu 24.04 and Fedora 43. Other derivatives resolve to the same family and
  are best-effort. A full desktop session on a Debian-family distro has not
  been confirmed yet.

## Compositor & session

| What | Fedora (`dnf`) | Debian family (`apt`) | Arch (`pacman`) |
| ---- | -------------- | --------------------- | --------------- |
| idle daemon | `hypridle` | `hypridle` | `hypridle` |
| compositor | `hyprland` — stock Fedora has no Hyprland stack: first run 'sudo dnf copr enable sdegler/hyprland' (also provides hypridle, hyprlock, hyprpaper, hyprpolkitagent, uwsm, cliphist) | `hyprland` — on Debian stable the usable Hyprland is only in the release's backports repository: add the line `deb http://deb.debian.org/debian <release>-backports main` (see https://backports.debian.org/Instructions/), run `sudo apt update`, then `sudo apt install -t <release>-backports hyprland`; Parrot and some other derivatives already have backports enabled, so the printed command works as-is there | `hyprland` |
| lock screen | `hyprlock` | `hyprlock` | `hyprlock` |
| wallpaper fallback (grootshell draws the wallpaper day to day) | `hyprpaper` | `hyprpaper` | `hyprpaper` |
| polkit agent | `hyprpolkitagent` | `hyprpolkitagent` | `hyprpolkitagent` — AUR |
| session manager that wraps every autostart app | `uwsm` | `uwsm` | `uwsm` |

## Bar / theming (grootshell — not in this repo)

`hyprland.lua` autostarts a Quickshell config called `grootshell`, which is
**not part of this repo** (see
[docs/hyprland-wallpaper-and-theming.md](hyprland-wallpaper-and-theming.md)
for why). Without it there's no bar, no notifications, no wallpaper —
Hyprland itself still starts fine.

| What | Fedora (`dnf`) | Debian family (`apt`) | Arch (`pacman`) |
| ---- | -------------- | --------------------- | --------------- |
| wallpaper -> colour palette | cargo install matugen (needs Rust/cargo; Arch: AUR matugen) | cargo install matugen (needs Rust/cargo; Arch: AUR matugen) | cargo install matugen (needs Rust/cargo; Arch: AUR matugen) |
| Quickshell (runs grootshell: bar, notifications, wallpaper) | COPR: sudo dnf copr enable errornointernet/quickshell && sudo dnf install quickshell | `quickshell` | AUR: quickshell |

## Terminal & tools

| What | Fedora (`dnf`) | Debian family (`apt`) | Arch (`pacman`) |
| ---- | -------------- | --------------------- | --------------- |
| file manager (SUPER+E on the maintainer's host; set file_manager in hosts.toml) | `dolphin` | `dolphin` | `dolphin` |
| terminal | `kitty` | `kitty` | `kitty` |
| launcher, power menu, clipboard picker | `rofi` | `rofi` | `rofi` |
| shell prompt | `starship` — not in stock Fedora: needs the Terra repo (https://terra.fyralabs.com/) | `starship` | `starship` |
| terminal file manager | `yazi` — not in stock Fedora: needs the Terra repo (https://terra.fyralabs.com/) | see https://yazi-rs.github.io/docs/installation | `yazi` |

Yazi's `z`/`Z` keymap needs two of its own plugins on top of the package
itself: `ya pack -a yazi-rs/plugins:zoxide yazi-rs/plugins:fzf` — which in
turn need `zoxide` and `fzf` (see the clipboard/screenshot table below,
`fzf` is already there for clipboard).

## Clipboard & screenshots

| What | Fedora (`dnf`) | Debian family (`apt`) | Arch (`pacman`) |
| ---- | -------------- | --------------------- | --------------- |
| clipboard history | `cliphist` | `cliphist` | `cliphist` — AUR |
| fuzzy finder (clipboard fallback, yazi Z) | `fzf` | `fzf` | `fzf` |
| screenshots | `grim` | `grim` | `grim` |
| JSON tool used by rice scripts | `jq` | `jq` | `jq` |
| notify-send | `libnotify` | `libnotify-bin` | `libnotify` |
| screen region picker | `slurp` | `slurp` | `slurp` |
| wl-copy / wl-paste | `wl-clipboard` | `wl-clipboard` | `wl-clipboard` |
| xdg-user-dir: screenshot and yt-x download folders | `xdg-user-dirs` | `xdg-user-dirs` | `xdg-user-dirs` |
| xdg-open / xdg-settings: default browser and file manager | `xdg-utils` | `xdg-utils` | `xdg-utils` |
| only if primary_monitor is set for your host | `xrandr` | `x11-xserver-utils` | `xorg-xrandr` |
| smart cd (yazi z) | `zoxide` | `zoxide` | `zoxide` |

## Media / audio

| What | Fedora (`dnf`) | Debian family (`apt`) | Arch (`pacman`) |
| ---- | -------------- | --------------------- | --------------- |
| media keys | `playerctl` | `playerctl` | `playerctl` |
| wpctl (volume keys); usually pulled in with a PipeWire desktop | `wireplumber` | `wireplumber` | `wireplumber` |

## System tray / hardware

| What | Fedora (`dnf`) | Debian family (`apt`) | Arch (`pacman`) |
| ---- | -------------- | --------------------- | --------------- |
| Bluetooth manager | `blueman` | `blueman` | `blueman` |
| KDE Connect (only if your host autostarts it) | `kdeconnectd` | `kdeconnect` | `kdeconnect` |
| NetworkManager tray applet | `network-manager-applet` | `network-manager-gnome` | `network-manager-applet` |

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

| What | Fedora (`dnf`) | Debian family (`apt`) | Arch (`pacman`) |
| ---- | -------------- | --------------------- | --------------- |
| secrets (profile=personal only) | `age` | `age` | `age` |
| nicer prompts in `rice onboard` (plain prompts without it) | `gum` | charm apt repo: https://github.com/charmbracelet/gum#installation | `gum` |

## Dev tooling for this repo (not applied to your `$HOME`)

`make test` needs `chezmoi` (already required) and, optionally, `luajit`
(Fedora: `sudo dnf install luajit`) to syntax-check the rendered Lua.

`make check` needs `shellcheck` and `gitleaks` — Fedora: `sudo dnf install
shellcheck` (`gitleaks` isn't in Fedora's repos, grab a release binary
from [gitleaks' releases page](https://github.com/gitleaks/gitleaks/releases)).
Debian/Arch: `shellcheck` is packaged (`apt`/`pacman`); `gitleaks` is on
the AUR, otherwise the same release-binary approach as Fedora.
