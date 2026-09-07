# dotfiles

Dotfiles for `desktop` (Fedora/KDE), `pentest` (Parrot/KDE) and `server`
(Debian, headless), managed with [GNU Stow](https://www.gnu.org/software/stow/).

## Apply

```bash
sudo dnf install stow gitleaks ShellCheck   # Fedora
sudo apt install stow shellcheck            # Debian / Parrot

git clone git@github.com:44lain/dotfiles.git ~/dotfiles
cd ~/dotfiles

make bashrc-hook   # Debian/Parrot only — hooks ~/.bashrc.d into ~/.bashrc
make desktop        # or: make pentest / make server
make cursor-extensions   # optional, desktop/pentest
```

`make dry-run PKG=<name>` previews without touching anything.
`make unstow PKG=<name>` removes a package's symlinks.

## How Stow is used here

Each top-level directory is a Stow package whose internal path mirrors
`$HOME`. `make desktop` runs `stow` for the packages that host uses, creating
symlinks in `$HOME` back into this repo — e.g. `konsole/.config/konsolerc` in
the repo becomes the real `~/.config/konsolerc`. Stow refuses to overwrite an
existing real file, so nothing is silently replaced.

## Packages

| Package    | Contents                                    | desktop | pentest | server |
| ---------- | -------------------------------------------- | :-----: | :-----: | :----: |
| `shell`    | `~/.bashrc.d/` fragments                     |    ✓    |    ✓    |   ✓    |
| `starship` | prompt                                        |    ✓    |    ✓    |   ✓    |
| `git`      | `.gitconfig`                                  |    ✓    |    ✓    |   ✓    |
| `konsole`  | profile + colorschemes                        |    ✓    |    ✓    |        |
| `cursor`   | `settings.json`, `keybindings.json`           |    ✓    |    ✓    |        |
| `kde`      | `kdeglobals`, `kwinrc`, `kglobalshortcutsrc`  |    ✓    |    ✓    |        |
| `bin`      | personal scripts                              |    ✓    |         |        |
| `hypr`     | Hyprland lua config, hypridle                 |    ✓    |         |        |
| `kitty`    | terminal baseline (matugen palette at runtime)|    ✓    |         |        |
| `environment.d` | `systemd --user` PATH glue for uwsm      |    ✓    |         |        |
| `yt-x`     | terminal YouTube browser config               |    ✓    |         |        |

See [docs/keyboard.md](docs/keyboard.md) for the KDE shortcut remap (60%
keyboard) and
[docs/hyprland-wallpaper-and-theming.md](docs/hyprland-wallpaper-and-theming.md)
for how the wallpaper, border colour and bar/terminal frost fit together, and
[docs/yt-x.md](docs/yt-x.md) for the terminal YouTube setup (deps and the Zen
cookie symlink are not automated).

## Layout

```
dotfiles/
├── shell/     .bashrc.d/{10-path,20-aliases,30-pnpm,40-starship}.sh
├── starship/  .config/starship.toml
├── konsole/   .config/konsolerc
│              .local/share/konsole/{*.colorscheme,*.profile}
├── cursor/    .config/Cursor/User/{settings,keybindings}.json
├── kde/       .config/{kdeglobals,kwinrc,kglobalshortcutsrc}
├── git/       .gitconfig
├── bin/       bin/cs2-mode.sh
│              .local/bin/accela
├── hypr/      .config/hypr/{hyprland.lua,hypridle.conf}
│              .config/hypr/_legacy_ini_backup/  (pre-lua INI, rollback)
├── kitty/     .config/kitty/kitty.conf
├── environment.d/ .config/environment.d/50-local-bin.conf
├── yt-x/      .config/yt-x/config
└── docs/      keyboard.md, hyprland-wallpaper-and-theming.md, yt-x.md, cursor-extensions.txt
```
