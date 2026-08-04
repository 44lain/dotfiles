# Keyboard and shortcuts

Why the KDE shortcuts in this repo diverge from the defaults, so that a future
reinstall restores intent and not just an `.ini` file.

## The constraint

The daily driver is a 60% board — USB `258a:0049`, a Sino Wealth controller.
It is **not QMK or VIA**, so there is no firmware layer and no `keymap.c` to
version. Everything below lives in `kde/.config/kglobalshortcutsrc` and nowhere
else. That file is the only backup of this layout.

A 60% has no F-row, no arrow cluster, no navigation block and no numpad. Every
default that reaches for `F1`–`F12`, `PgUp`, `PgDown`, `Home`, `End` or
`Print` is only reachable through a `Fn` layer, which defeats the point of a
shortcut. The remaps move those onto the alpha block.

## Virtual desktops

Four desktops, named `work`, `games`, `musga`, `misc`.

| Action | KDE default | Here | Why |
| --- | --- | --- | --- |
| Switch to desktop 1–3 | `Meta+F1`…`F3` | `Alt+1`…`3` | F-row needs `Fn` |
| Switch to desktop 4 | `Meta+F4` | `Ctrl+F4`, `Alt+4` | see open question below |
| Move window to desktop 1–4 | *(unbound)* | `Alt+!` `Alt+@` `Alt+#` `Alt+$` | i.e. `Alt+Shift+1..4`, pairs with the switch binding |

## Window management

| Action | KDE default | Here | Why |
| --- | --- | --- | --- |
| Maximize | `Meta+PgUp` | `Alt+Shift+W` | no `PgUp` on a 60% |
| Minimize | `Meta+PgDown` | `Alt+Shift+E` *(default kept as secondary)* | no `PgDown` |
| Close | `Alt+F4` | `Alt+Shift+Q` *(default kept as secondary)* | `F4` needs `Fn` |
| Fullscreen | *(unbound)* | `Ctrl+Alt+W` | |
| Present windows | `Meta+F9`/`F10`/`F7` | `Ctrl+F9`/`F10`/`F7` | dropped the `Meta+F*` variant, kept `Ctrl+F*` |
| Clear mouse marks | `Meta+Shift+F11`/`F12` | `Ctrl+Alt+Z` / `Ctrl+Alt+X` | |

Where a default did not require `Fn`, it was kept as a secondary binding rather
than overwritten — muscle memory from other machines still works.

## Tiling (Krohnkite)

Krohnkite is a tiling script for KWin, installed under
`~/.local/share/kwin/scripts/krohnkite`. Its 19 bindings use vim motions:

| | |
| --- | --- |
| Focus | `Meta+H` `Meta+J` `Meta+K` `Meta+L` |
| Move window | `Meta+Shift+` + `H/J/K/L` |
| Resize | `Meta+Ctrl+` + `H/J/K/L` |
| Layouts | `Meta+M` monocle · `Ctrl+Alt+F` floating · `Meta+\\` next · `Meta+Backspace` previous |
| Other | `Meta+F` float all · `Meta+I` increase · `Meta+Ctrl+Return` set master |

**Currently disabled** — `kwinrc` has `krohnkiteEnabled=false`. The bindings are
kept on purpose: they are inert while the script is off, and re-enabling the
script restores a working tiling setup with no re-learning. The gap settings in
`[Script-krohnkite]` are preserved for the same reason.

`linux-bootstrap` must install the script, otherwise these bindings point at
nothing on a fresh machine.

## Deliberately disabled

129 default actions are set to `none`. The two groups worth knowing about:

- **Session actions** — `Shut Down`, `Reboot`, `LogOut` and their
  "Without Confirmation" variants. A misfire on these is unrecoverable.
- **Desktops 5–20**, plus opacity stepping and `Setup Window Shortcut`. Only
  four desktops exist; the rest were noise in the shortcut list.

## Known asymmetry — left as is

`Switch to Desktop 4` has `Ctrl+F4` primary and `Alt+4` secondary, while
desktops 1–3 have `Alt+N` primary. Reviewed and kept: `Alt+4` still works, so
the inconsistency costs nothing in practice, and rewriting a binding that is
already in muscle memory costs more than it fixes.

Not a candidate for "cleanup" on a future pass. `Alt+F4` is not available as an
alternative either — it belongs to `Window Close`.
