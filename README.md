# dotfiles

Hyprland rice for Fedora, managed with [chezmoi](https://www.chezmoi.io/).
Meant to be cloned and actually used, not just looked at — pick your
`profile`/`host` at apply time and it applies cleanly, or restore your own
machine after a reinstall.

This repo only manages config files. It does not install packages —
Hyprland, kitty, yazi, etc. need to already be on the system. See
[docs/dependencies.md](docs/dependencies.md) for the full list, with
`dnf`/`apt`/`pacman` commands for each. `chezmoi` and `git` (below) are
the only two required just to apply this repo itself.

## Apply

```bash
sudo dnf install chezmoi git       # Fedora
sudo apt install chezmoi git       # Debian / Parrot
sudo pacman -S chezmoi git         # Arch

chezmoi init 44lain    # clones over HTTPS — no SSH key needed
```

You'll be asked two questions — each one explains itself when you see it,
but in short:

- **profile** — `guest` (the default) gets the shared rice only: themes,
  keybinds, look & feel. `personal` also pulls in a couple of scripts
  specific to my own machines.
- **host** — picks monitor layout, keyboard layout and GPU env from
  [`.chezmoidata/hosts.toml`](.chezmoidata/hosts.toml). `desktop` and
  `pentest` exist right now (my own two machines) — for anything else,
  either add a `[hosts.<name>]` block there by hand before applying, or
  just pick `desktop` for now: `rice` doesn't exist on the machine until
  the first apply creates it, so run `rice onboard` right after that —
  it autodetects monitors/keyboard/GPU and adds your host (see below).

That only clones and answers the prompts — nothing has touched `$HOME`
yet. Look before applying, especially if this isn't a throwaway machine:

```bash
chezmoi diff     # preview every file this would create or overwrite
chezmoi apply    # only once the diff looks right
```

`chezmoi apply` (not `chezmoi init --apply`) on purpose here: this first
apply is the one time in this whole flow that **doesn't** go through the
`rice apply` safety net below — `rice` itself doesn't exist on the
machine until this apply creates it. A plain `chezmoi diff` first is the
only guard available before that point.

Two loose ends specific to a first install, not automated by the above:

- **Debian/Parrot only:** their stock `~/.bashrc` doesn't source
  `~/.bashrc.d/*` the way Fedora's does — run
  `(cd "$(chezmoi source-path)" && make bashrc-hook)` once, or the prompt/
  aliases in `dot_bashrc.d/` never load.
- **`rice` not found right after applying:** `~/.local/bin` only lands on
  `PATH` once `dot_bashrc.d/10-path.sh` is sourced — open a new terminal
  (or `source ~/.bashrc`), or just run `~/.local/bin/rice <command>` by
  full path the first time.

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
| `rice onboard` | First-machine wizard: prompts for a git email if unset, then profile/host — autodetects monitors/keyboard/GPU for a new host and adds it (to the repo if `personal`, local-only if `guest`), then hands off to `rice apply`. |
| `rice doctor` | Not built yet — health check. |

Every `rice apply` backs up what it's about to change to
`~/.local/state/rice/backup/<timestamp>/` before touching anything, so
`rice rollback` always has something to restore. Nothing here is a real
transaction — both commands are best-effort, not a database.

## What's in it

| Path | Contents |
| ---- | -------- |
| `dot_bashrc.d/`, `dot_config/starship.toml` | shell + prompt |
| `dot_gitconfig` | git identity (name only — email is machine-local; `rice onboard` prompts for it, or set by hand: `git config -f ~/.config/git/local user.email you@example.com`) |
| `dot_config/hypr/` | Hyprland: `hyprland.lua` (keybinds, look & feel, window rules), `hypridle.conf`, `machine.lua.tmpl` (generated per-host monitors/kb layout/GPU env — see `.chezmoidata/hosts.toml`) |
| `dot_config/kitty/`, `dot_config/yazi/`, `dot_config/yt-x/` | terminal, file manager, terminal YouTube browser |
| `dot_config/environment.d/` | `systemd --user` PATH glue so uwsm-spawned apps see `~/.local/bin` |
| `bin/executable_cs2-mode.sh` | CS2 FPS tuning — `profile=personal` only |
| `dot_local/bin/` | the `rice` command family |

Not in this repo, on purpose: KDE fallback config, Cursor editor settings,
and a Konsole profile used to live here — dropped, they're personal backup
material, not part of the rice anyone would actually want. `hyprlock.conf`,
`hyprpaper.conf` and the wallpaper-derived `colors-grootshell.lua` are also
left out of version control (personal wallpaper path, not yet templated).

See [docs/dependencies.md](docs/dependencies.md) for every package this
rice touches, per distro; [docs/keyboard.md](docs/keyboard.md) for the KDE
shortcut remap this still assumes as a fallback (60% keyboard);
[docs/hyprland-wallpaper-and-theming.md](docs/hyprland-wallpaper-and-theming.md)
for how the wallpaper, border colour and bar/terminal frost fit together;
[docs/yt-x.md](docs/yt-x.md) for the terminal YouTube setup (deps and the
Zen cookie symlink are not automated); and
[docs/track-E.md](docs/track-E.md), the full design doc + cookbook for the
chezmoi migration this repo went through, including a step-by-step for
adding a monitor or a new host.

## Layout

```
dotfiles/
├── .chezmoi.toml.tmpl     profile/host prompts (chezmoi init)
├── .chezmoidata/hosts.toml   per-host monitors, kb_layout, GPU env
├── dot_bashrc.d/          10-path, 20-aliases, 30-pnpm, 40-starship
├── dot_config/
│   ├── starship.toml
│   ├── environment.d/50-local-bin.conf
│   ├── hypr/              hyprland.lua, hypridle.conf, machine.lua.tmpl
│   │                      readonly__legacy_ini_backup/ (pre-lua, rollback)
│   ├── kitty/kitty.conf
│   ├── yazi/{yazi,keymap}.toml
│   └── yt-x/config
├── dot_gitconfig
├── dot_local/bin/         rice, rice-apply, rice-rollback, rice-uninstall
├── bin/executable_cs2-mode.sh
├── test/                  rice.sh, wave-1.sh
└── docs/                  dependencies.md, keyboard.md,
                           hyprland-wallpaper-and-theming.md, yt-x.md,
                           track-E.md, cursor-extensions.txt
```

## Dev commands (this repo, not the applied config)

```bash
make check              # shellcheck + gitleaks
make bashrc-hook        # Debian/Parrot only — hooks ~/.bashrc.d into ~/.bashrc
make cursor-extensions  # installs the Cursor extensions in docs/cursor-extensions.txt
```
