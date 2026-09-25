# dotfiles

Hyprland rice for Fedora and Debian-family distros, managed with [chezmoi](https://www.chezmoi.io/).
Meant to be cloned and actually used, not just looked at — pick your
`profile`/`host` at apply time and it applies cleanly, or restore your own
machine after a reinstall.

## Who can use this

| | |
| --- | --- |
| **Supported** | **Fedora** (built and tested on Fedora 43) and **Debian-family distros** (Debian, Ubuntu, Linux Mint, Kali, Parrot, Pop!_OS, …) that can install **Hyprland 0.55 or newer** — the config is `hyprland.lua`, and Lua config needs a recent Hyprland. `rice doctor` tells you whether yours can and prints the install command. |
| **Planned** | **Arch.** Nothing here is Arch-specific; the package names are already listed in [docs/dependencies.md](docs/dependencies.md) but have **not been tested**. Adding it means testing that list on a real install and dropping the "untested" warning. |
| **Not supported** | Setups without Hyprland, and releases that cannot get Hyprland 0.55+ from their repos (e.g. Debian 12, Ubuntu 24.04 LTS) unless you build Hyprland yourself. |

Fedora with Hyprland is the verified target. The Debian family is verified in
containers only (package names and a first apply, `make distro-check`); a full
desktop run is confirmed on: *(not yet — to be filled in after a real-hardware
test)*. Stock Debian 13 needs its backports repository enabled to get a usable
Hyprland; `rice doctor` prints the steps.

This repo only manages config files. It does **not** install packages —
Hyprland, kitty, yazi and the rest must already be on the system, see
[docs/dependencies.md](docs/dependencies.md). `chezmoi` and `git` are the
only two things needed just to apply this repo itself.

### The bar, notifications and wallpaper

Those come from **grootshell**, a [Quickshell](https://quickshell.outfoxxed.me/)
desktop shell that is not part of this repo. It is an upstream project
([BenjaminPrice/grootshell](https://github.com/BenjaminPrice/grootshell),
GPL-3.0); the version used with this rice is kept as a fork at
[44lain/grootshell](https://github.com/44lain/grootshell). Without it Hyprland
still starts, but there is no bar, no notification daemon and no wallpaper.

```bash
# Fedora; other distros: see docs/dependencies.md
sudo dnf copr enable errornointernet/quickshell && sudo dnf install quickshell
cargo install matugen        # wallpaper -> colour palette; needs Rust/cargo (on Debian family too)
git clone https://github.com/44lain/grootshell ~/.config/quickshell/grootshell
```

## Apply

```bash
# Fedora
sudo dnf install chezmoi git
# Debian / Ubuntu / Mint / Kali / Parrot / Pop!_OS …
sudo apt install git curl && sh -c "$(curl -fsLS get.chezmoi.io)" -- -b ~/.local/bin
# Arch
sudo pacman -S chezmoi git

chezmoi init 44lain    # clones over HTTPS — no SSH key needed
```

You'll be asked two questions — each one explains itself when you see it,
but in short:

- **profile** — `guest` (the default) gets the shared rice only: themes,
  keybinds, look & feel. `personal` also pulls in a couple of scripts
  specific to the maintainer's own machines.
- **host** — picks monitor layout, keyboard layout, GPU env and app choices
  from [`.chezmoidata/hosts.toml`](.chezmoidata/hosts.toml). `desktop` and
  `pentest` exist right now (the maintainer's own machines) — for anything
  else, either add a `[hosts.<name>]` block there by hand before applying, or
  pick `desktop` for now and run `rice onboard` right after the first apply:
  it autodetects monitors/keyboard/GPU and adds your host (see below).

That only clones and answers the prompts — nothing has touched `$HOME`
yet. Look before applying, especially if this isn't a throwaway machine:

```bash
chezmoi diff     # preview every file this would create or overwrite
chezmoi apply    # only once the diff looks right
```

`chezmoi apply` (not `chezmoi init --apply`) on purpose: this first apply is
the one time in this flow that **doesn't** go through the `rice apply`
safety net below — `rice` itself doesn't exist on the machine until this
apply creates it. A plain `chezmoi diff` first is the only guard available
before that point.

Then finish setting up — this is what makes the machine yours:

```bash
rice onboard     # git name + email, optional wallpaper, host detection
```

`rice` is on `PATH` once `dot_bashrc.d/10-path.sh` is sourced, so open a new
terminal first (or `source ~/.bashrc`, or run `~/.local/bin/rice onboard`).
On Debian-family distros the stock `~/.bashrc` does not load `~/.bashrc.d`;
`rice onboard` offers to add the loader (or run `make bashrc-hook` yourself).

Then, on any distro: run `rice doctor` and paste the `sudo … install` line it
prints for the missing packages, and at your display manager (SDDM, GDM, …)
pick the Hyprland session entry that goes through **uwsm** if it lists one.

Your git name and email are **machine-local** (`~/.config/git/local`, never
committed) — until `rice onboard` sets them, `git commit` will refuse to run.
A wallpaper is optional: without one the lock screen is a plain dark
background and hyprpaper draws nothing (grootshell draws the wallpaper day
to day).

## Day to day: the `rice` command

Once applied, `~/.local/bin/rice` is the entry point for everything after
the first install — never run a bare `chezmoi apply` on this repo, it
skips the safety net below.

| Command | What it does |
| ------- | ------------ |
| `rice diff` | Preview what would change. Read-only. |
| `rice apply` | Preview, back up whatever it's about to touch, ask `y/N`, then apply. |
| `rice rollback [<timestamp>]` | Undo the **last** `rice apply` only. |
| `rice uninstall` | Undo **every** `rice apply` ever run here — back to before this repo touched anything. Leaves `chezmoi` itself installed. |
| `rice onboard` | First-machine wizard: git name/email if unset, optional wallpaper, then profile/host — autodetects monitors/keyboard/GPU for a new host and adds it (to the repo if `personal`, local-only if `guest`), then hands off to `rice apply`. |
| `rice doctor` | Health check: configs parse, services running, fonts present, theme files coherent, dependencies (with the install command for your distro), Hyprland version. `FAIL` exits 1; `WARN` doesn't. |

Every `rice apply` backs up what it's about to change to
`~/.local/state/rice/backup/<timestamp>/` before touching anything, so
`rice rollback` always has something to restore. Nothing here is a real
transaction — both commands are best-effort, not a database.

## Customizing

Things you'd plausibly want to change live in one place each:

| To change | Edit |
| --------- | ---- |
| monitors, keyboard layout, GPU env | `[hosts.<name>]` in `.chezmoidata/hosts.toml` |
| terminal / file manager / browser (`SUPER+Return`/`E`/`B`), X11 primary monitor, tray apps started at login | the optional keys in the same `[hosts.<name>]` block (documented at the top of the file; each has a neutral default) |
| keybinds, look & feel, window rules | `dot_config/hypr/hyprland.lua` |
| wallpaper for the lock screen | `wallpaper_path` in `~/.config/chezmoi/chezmoi.toml` `[data]` (machine-local) |
| git name / email | `~/.config/git/local` (machine-local) |

Then `rice apply`. See [docs/track-E.md](docs/track-E.md) for a step-by-step
on adding a monitor or a new host.

## What's in it

| Path | Contents |
| ---- | -------- |
| `dot_bashrc.d/`, `dot_config/starship.toml` | shell + prompt |
| `dot_gitconfig` | git LFS + an include of the machine-local `~/.config/git/local` (name and email live there, not here) |
| `dot_config/hypr/` | Hyprland: `hyprland.lua` (keybinds, look & feel, window rules), `hypridle.conf`, `hyprlock.conf.tmpl`, `hyprpaper.conf.tmpl`, `machine.lua.tmpl` (generated per-host monitors/kb layout/GPU env/apps — see `.chezmoidata/hosts.toml`) |
| `dot_config/kitty/`, `dot_config/yazi/`, `dot_config/yt-x/` | terminal, file manager, terminal YouTube browser |
| `dot_config/environment.d/` | `systemd --user` PATH glue so uwsm-spawned apps see `~/.local/bin` |
| `bin/executable_cs2-mode.sh` | CS2 FPS tuning — `profile=personal` only |
| `dot_local/bin/` | the `rice` command family, plus `powermenu` (rofi power menu, `SUPER+O` then `E`) |

Not managed here, on purpose: `colors-grootshell.lua` / `colors-grootshell.conf`
are generated from the wallpaper at runtime (matugen), so chezmoi leaves them
alone. KDE fallback config, Cursor editor settings and a Konsole profile used to
live in this repo and were dropped — personal backup material, not part of the
rice.

See [docs/dependencies.md](docs/dependencies.md) for every package this
rice touches; [docs/keyboard.md](docs/keyboard.md) for the KDE shortcut remap
for a 60% keyboard;
[docs/hyprland-wallpaper-and-theming.md](docs/hyprland-wallpaper-and-theming.md)
for how the wallpaper, border colour and bar/terminal frost fit together;
[docs/yt-x.md](docs/yt-x.md) for the terminal YouTube setup; and
[docs/track-E.md](docs/track-E.md), the design doc for the chezmoi migration
this repo went through.

## Layout

```
dotfiles/
├── .chezmoi.toml.tmpl     profile/host prompts (chezmoi init)
├── .chezmoidata/hosts.toml   per-host monitors, kb_layout, GPU env, apps
├── dot_bashrc.d/          10-path, 20-aliases, 30-pnpm, 40-starship
├── dot_config/
│   ├── starship.toml
│   ├── environment.d/50-local-bin.conf
│   ├── hypr/              hyprland.lua, hypridle.conf, hyprlock/hyprpaper
│   │                      .conf.tmpl, machine.lua.tmpl
│   ├── kitty/kitty.conf
│   ├── yazi/{yazi,keymap}.toml
│   └── yt-x/config.tmpl
├── dot_gitconfig
├── dot_local/bin/         rice, rice-{apply,rollback,uninstall,onboard,doctor},
│                          powermenu
├── bin/executable_cs2-mode.sh
├── test/                  rice*.sh, machine.sh, wave-4-wallpaper.sh
└── docs/                  dependencies, keyboard, theming, yt-x, ROADMAP, track-E
```

## Dev commands (this repo, not the applied config)

```bash
make check              # shellcheck + gitleaks
make test               # test/*.sh — needs chezmoi; luajit optional
make bashrc-hook        # `rice onboard` offers this; manual form (hooks ~/.bashrc.d into ~/.bashrc)
make docs               # regenerate docs/dependencies.md from .chezmoidata/packages.toml
make distro-check       # package names + guest install in containers (docker, network)
make cursor-extensions  # installs the Cursor extensions in docs/cursor-extensions.txt
```
