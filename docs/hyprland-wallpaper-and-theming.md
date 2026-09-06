# Wallpaper and theming on Hyprland

Why the wallpaper, the window-border colour and the bar/terminal translucency
are wired the way they are — so a reinstall restores the intent, not just a pile
of files that happen to work.

Session that produced this: 2026-09-05. Host: `desktop` (Fedora 43), NVIDIA
GTX 1660S, dual monitor — `DP-1` (AOC, 1920x1080@144, primary) and `HDMI-A-1`
(HP V19b, 1366x768@60).

## TL;DR of what changed

| Area | File | Tracked here |
| --- | --- | :---: |
| Border colour from wallpaper (persistence side) | `hypr/.config/hypr/hyprland.lua` | ✓ |
| Drop hyprpaper from autostart | `hypr/.config/hypr/hyprland.lua` | ✓ |
| hyprpaper legacy → 0.8 syntax | `~/.config/hypr/hyprpaper.conf` | untracked by design |
| matugen on the session PATH | `environment.d/.config/environment.d/50-local-bin.conf` | ✓ (new package) |
| Terminal frost | `kitty/.config/kitty/kitty.conf` | ✓ (new package) |
| Per-monitor wallpaper bug fix | `~/.config/quickshell/grootshell/modules/background/Background.qml`, `shell.qml` | grootshell is not in this repo |
| Border-colour template + pipeline | `~/.config/quickshell/grootshell/templates/hyprland.lua.tpl`, `scripts/generate-theme.sh` | grootshell is not in this repo |
| Bar frost | `~/.config/quickshell/grootshell/components/Pill.qml`, `modules/bar/Workspaces.qml` | grootshell is not in this repo |

`~/.config/quickshell/grootshell/` holds a heavily-customised copy of the
grootshell Quickshell config. It is **not** a Stow package here and **not** its
own git repo on this host. The edits below live only on the filesystem; if that
shell is ever re-cloned they have to be re-applied. Vendoring it into this repo
is a separate decision.

## The original bug: no wallpaper on the primary monitor

`hyprctl layers` told the real story:

```
Monitor HDMI-A-1:  two  grootshell-background surfaces + hyprpaper
Monitor DP-1:       only hyprpaper
```

Two independent faults stacked into one symptom.

### Fault 1 — `Background.qml` shadowed `PanelWindow.screen`

`modules/background/Background.qml` had:

```qml
PanelWindow {
    id: root
    required property ShellScreen screen   // <- shadows PanelWindow's own `screen`
    ...
}
```

`PanelWindow` already has a `screen` property. Re-declaring it means the caller's
`Background { screen: scope.modelData }` binding set the **shadowing** property,
and the window's real `screen` was never assigned — so every `Background`
instance fell onto the default output. Both wallpaper surfaces landed on one
monitor and the other got none. Which monitor lost the wallpaper flipped on every
restart, because "default output" is a startup race.

The bar never had this problem: `shell.qml` sets `PanelWindow.screen` directly on
`barWindow`, no re-declaration.

**Fix** — rename the property and bind the real one:

```qml
PanelWindow {
    id: root
    required property ShellScreen modelData
    screen: root.modelData
    ...
}
```

and in `shell.qml`: `Background { modelData: scope.modelData }`.

After this, each monitor gets exactly one `grootshell-background` surface.

Quickshell here is `0.3.1` (Fedora COPR `errornointernet/quickshell`). Upstream
has moved on; if the shell is ever updated, re-check whether this rename is still
needed or whether the newer API makes it moot.

### Fault 2 — hyprpaper couldn't cover for it

`hyprpaper 0.8.4` (Fedora RPM) dropped the pre-0.8 config syntax entirely. The
word `preload` is not even in the binary any more, and `wallpaper = MON,path` is
ignored — hyprpaper created no wallpaper target for either monitor
(`Monitor DP-1 has no target: no wp will be created`).

`~/.config/hypr/hyprpaper.conf` is migrated to the 0.8 block form:

```
ipc = on
splash = false

wallpaper {
    monitor = DP-1
    path = /home/you/Pictures/wallpaper.jpg
}
wallpaper {
    monitor = HDMI-A-1
    path = /home/you/Pictures/wallpaper.jpg
}
```

It stays **untracked** (personal wallpaper path, same rule as `hyprlock.conf`)
and is only a fallback now — see below.

## Wallpaper is owned by the shell

`grootshell` (`modules/background/Background.qml`) already draws the wallpaper as
its own `Background`-layer surface per screen and drives the matugen palette from
it. With Fault 1 fixed, that works on both monitors, so **hyprpaper is dropped**:

- `hyprland.lua` autostart no longer runs `uwsm app -- hyprpaper`.
- The `SUPER+O` → `W` bind (was `hyprctl hyprpaper reload`, now dead under the
  Lua config parser) now calls `grootshell-ipc call wallpaper next`.

To go back to hyprpaper: re-enable the autostart line and comment out
`Background {}` in the shell's `shell.qml`.

## Window borders follow the wallpaper

The matugen pipeline (`scripts/generate-theme.sh` + `templates/`) already themed
the shell, GTK 3/4, WezTerm, Qt (qt6ct) and kitty. It had **no Hyprland
template**, so borders stayed the static catppuccin gradient.

### New template

`~/.config/quickshell/grootshell/templates/hyprland.lua.tpl`:

```lua
return {
  active_border = {
    "rgba({{colors.primary.default.hex_stripped}}ee)",
    "rgba({{colors.tertiary.default.hex_stripped}}ee)",
  },
  inactive_border = "rgba({{colors.outline_variant.default.hex_stripped}}aa)",
}
```

### Pipeline wiring (`scripts/generate-theme.sh`)

- new `[templates.hyprland]` block in the generated `matugen.toml`
  (`output_path = "$work/out/hyprland.lua"`);
- `install_theme()` copies it to `~/.config/hypr/colors-grootshell.lua`;
- `"$config/hypr"` added to the `mkdir -p` list;
- at the end, a **live apply** via `hyprctl eval` — the Lua config parser
  rejects `hyprctl keyword` ("can't work with non-legacy parsers"), so the
  border is set by running an `hl.config{ general = { col = ... } }` chunk that
  re-reads the file just written.

The template `*.tpl` files are already part of the script's cache fingerprint, so
adding one invalidates the cache without a manual purge.

### Persistence (`hypr/.config/hypr/hyprland.lua`) — tracked

A `do ... end` block after the main `hl.config{}` `pcall(dofile, ...)`s
`~/.config/hypr/colors-grootshell.lua` and applies `active_border` /
`inactive_border` from it. This is only the persistence half — it keeps the
wallpaper colour across `hyprctl reload` / relogin. The file is absent until the
first `theme regenerate`; until then the catppuccin values in the `general` block
stand.

`colors-grootshell.lua` is generated and **gitignored** (it resolves into
`hypr/.config/hypr/` through the Stow symlink).

## The theming pipeline was silently dead

`generate-theme.sh` needs `matugen`. It is installed at `~/.local/bin/matugen`
(v4.2.0), but `~/.local/bin` was only added to `PATH` by `~/.bashrc`, which
`systemd --user` / `uwsm` do not read. The shell is launched by
`uwsm app -- qs`, so it never saw matugen: every run died with
`matugen is not on PATH`, `theme.json` never regenerated, and the shell ran on
its compiled-in catppuccin fallback. Nothing followed the wallpaper.

**Fix** — `environment.d/.config/environment.d/50-local-bin.conf`:

```
PATH=%h/.local/bin:%h/bin:${PATH}
```

`systemd --user` reads `~/.config/environment.d/*.conf` at login and expands
`${PATH}`; `uwsm`-spawned apps inherit it. Takes effect on the **next login**.
For the current session it was pushed in with
`systemctl --user set-environment "PATH=..."` and the shell restarted.

## Bar and terminal frost (medium)

Blur was already configured and doing nothing:

- `hyprland.lua:171` has `hl.layer_rule` for `^grootshell(-bar)?$` with
  `blur = true` — but the bar's pills painted `Theme.frame` fully opaque, so
  there was nothing to blur through.
- `decoration:blur:enabled` is already globally `true`.

Changes:

- `components/Pill.qml` and `modules/bar/Workspaces.qml` — pill fill
  `Theme.frame` → `Qt.rgba(Theme.frame.r, Theme.frame.g, Theme.frame.b, 0.7)`.
  The gaps between pills stay fully transparent (below the rule's
  `ignore_alpha = 0.1`), so only the pills frost.
- `kitty/.config/kitty/kitty.conf` — `background_opacity 0.85` +
  `dynamic_background_opacity yes`; Hyprland's global blur does the rest, no
  window rule needed.

## Activation after a reinstall

1. `make desktop` (now also stows `kitty` and `environment.d`).
2. Ensure `matugen` is on `~/.local/bin` (`cargo install matugen` or the
   `sdegler/hyprland` COPR — needs >= 4.1 for `--prefer`).
3. Re-apply the grootshell edits from the table above (that shell is not in this
   repo).
4. Log out and back in, so `qs` starts under uwsm with the `environment.d` PATH.
5. `SUPER+O` then `T` once to generate the palette cleanly.
