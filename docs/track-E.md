# track E — repo → chezmoi + onboarding

Design spec for the migration off GNU Stow to [chezmoi](https://www.chezmoi.io/).
Covers backlog items **E1–E6** (`docs/ROADMAP.md`). Implementation ships in
waves, each wave gets its own plan; this file is the architecture.

Status: **design** · written 2026-09-10 · supersedes the E-track table stub in
`ROADMAP.md`.

---

## why

GNU Stow gives dumb symlinks and one flat set of packages. It cannot template
per machine, cannot carry secrets, cannot bootstrap packages or services, and
cannot cleanly separate "the rice anyone can take" from "my monitor layout".
chezmoi does all four. The E0 spike (`f100aec`) proved the mechanics in a
throwaway lab: per-host data from one file, a personal layer genuinely withheld
from a guest, `chezmoi diff` preview before apply, `run_once_` bootstrap
branching on distro.

The theme pipeline (matugen, `theme regenerate`) becomes a set of plugins on
top of this — **track A**, out of scope here.

## goals

1. `chezmoi apply` reproduces `$HOME` **byte-identical** to what Stow delivers today.
2. Same repo drives `desktop` (Fedora/Hyprland) and `pentest` (Parrot/KDE→Hyprland).
3. A guest dev installs the portable layer and **nothing** on their machine
   breaks — monitors, GPU env, personal config all untouched.
4. Fresh machine → one command → full desktop back.
5. Every config a person wants to hand-edit (keybinds, rules, look & feel) stays
   a plain file in its native syntax. Templating is scoped to what genuinely
   differs between machines.

## decisions

Locked during design (2026-09-10):

| # | Decision |
| - | -------- |
| D1 | One spec for the whole track (E1–E6). Implementation in waves. |
| D2 | Incremental migration: chezmoi and Stow coexist, package by package. |
| D3 | `server` host is **dropped**. Track E targets `desktop` and `pentest` only. |
| D4 | Secrets: ship the `age` mechanism + one example. Migrate no real secret now (YAGNI). |
| D5 | Track E builds the template *mechanism* only. Converting configs into token `.tmpl` files is track A. |
| D6 | Per-host divergence is **data-driven** (`.chezmoidata/hosts.toml` → generated `machine.lua`), accepting the indirection for a single edit point (option A of the design discussion). |
| D7 | Safe-apply guard is a wrapper command (`rice apply`). A bare `chezmoi apply` bypasses it, by design; docs steer to `rice apply`. |
| D8 | Track E creates a minimal `rice` dispatcher (`apply`, `diff`, `onboard`, `rollback`, `doctor` stub). Track C1 extends it. |
| D9 | Onboarding is a dedicated `rice-onboard` TUI script (`gum`, with a plain-`read` fallback). |
| D10 | E6 formalises the repo's **own** existing conventions. No structure imported from sibling repos. |

---

## 1 · source layout

**Where it lives.** The repo stays at `~/Documentos/Code/dotfiles`.
`~/.config/chezmoi/chezmoi.toml` sets `sourceDir` to that path — chezmoi does
**not** use its default `~/.local/share/chezmoi`. Development happens in the same
place as today.

**Layout translation.** The 12 Stow packages collapse into one tree that mirrors
`$HOME`, using chezmoi's source naming:

| Stow today | chezmoi source |
| ---------- | -------------- |
| `hypr/.config/hypr/hyprland.lua` | `dot_config/hypr/hyprland.lua` |
| `shell/.bashrc.d/10-path.sh` | `dot_bashrc.d/10-path.sh` *(sourced, not executed — no `executable_`)* |
| `bin/.local/bin/accela` | `dot_local/bin/executable_accela` |
| `bin/bin/cs2-mode.sh` | `bin/executable_cs2-mode.sh` *(target `~/bin/`)* |
| `git/.gitconfig` | `dot_gitconfig` |
| `konsole/.local/share/konsole/Sweet.colorscheme` | `dot_local/share/konsole/Sweet.colorscheme` |

Attribute prefixes: `executable_`, `private_`, `readonly_`, `run_onchange_`;
suffix `.tmpl`. The "package" grouping disappears as a concept — it becomes
plain directory structure under `dot_config/`.

**Two ignore files, different jobs:**

- **`.gitignore`** — unchanged philosophy: deny-by-default, "public from commit
  zero". The `!/hypr/...` allow-rules are rewritten for chezmoi source names
  (`!/dot_config/hypr/**`, `!/dot_local/bin/**`, …). The trailing hard
  re-ignore block for keys / tokens / `.env` / `*.kdbx` stays verbatim.
- **`.chezmoiignore`** — new. Stops chezmoi treating repo meta as targets.
  Lists `README.md`, `LICENSE`, `CONTRIBUTING.md`, `CLAUDE.md`, `docs/**`,
  `.github/**`, `test/**`. Also holds the templated layer-3 gate (§2) and every
  matugen-generated file (§5, track A boundary).

**`Makefile`.** Deleted **at the end of the migration** (wave 4 / E6), not up
front — the incremental waves still call `make unstow` / `make <host>` while
Stow and chezmoi coexist. Once the last package is migrated the Stow targets
have no chezmoi equivalent worth keeping; README then points at `rice` directly.

**`_legacy_ini_backup/`** (the pre-Lua Hyprland INI) migrates as-is under
`readonly_`, still the Hyprland rollback point.

---

## 2 · three layers and per-host data

### profile & host prompts

`.chezmoi.toml.tmpl` prompts twice at `chezmoi init` and writes to
`~/.config/chezmoi/chezmoi.toml` (machine-local, never in the repo):

- `profile` → `personal` | `guest`
- `host` → `desktop` | `pentest` | *(new name, via the wizard in §5)*

### layer 1 — portable rice

Everything with no host or profile gate: tokens/theme scaffolding, bar,
terminal, launcher, generic binds, shell, prompt, editor config. Anyone who
installs gets it. This is the bulk of `dot_config/`.

### layer 2 — machine profile (data-driven)

One file in the repo, `.chezmoidata/hosts.toml`:

```toml
[hosts.desktop]
  gpu       = "nvidia"
  kb_layout = "us,br"
  scale     = 1
  monitors  = [
    "DP-1,     1920x1080@144, 0x0,      1",
    "HDMI-A-1, 1366x768@60,   1920x312, 1",
  ]

[hosts.pentest]
  gpu       = "intel"
  kb_layout = "us,br"
  scale     = 1
  monitors  = [", preferred, auto, 1"]
```

A new monitor or a new machine means editing **this file only** (P2).

**Hyprland host extraction.** `hyprland.lua` today hardcodes monitors, NVIDIA
env, and `kb_layout`. Rather than templating the whole `.lua` (Go template
syntax inside Lua is unreadable), the machine-specific part moves to a
**generated file — the same pattern `colors-grootshell.lua` already uses**:

- new `dot_config/hypr/machine.lua.tmpl` renders
  `return { monitors = {…}, gpu_env = {…}, kb_layout = "…" }` from
  `.hosts[.host]`.
- `hyprland.lua` gains `local m = dofile(".../machine.lua")` near the top and
  reads that table for its monitor / env / input-layout lines. With no host
  data present it falls back to a built-in default (exactly as it already does
  for colours).
- `hyprpaper.conf` and `hyprlock.conf` (untracked today because of a personal
  wallpaper path) become `.tmpl`, path fed from a `wallpaper_dir` field
  (per-profile or per-host — decided in the plan).

Keybinds, window rules, look & feel, animations, and input (beyond the layout
string) **stay as plain Lua in `hyprland.lua`**. No template, no generation.

### layer 3 — personal

Gated by a templated block in `.chezmoiignore`:

```
{{ if ne .profile "personal" }}
.config/rice/projects.toml
.local/bin/accela
{{ end }}
```

With `profile = guest` those paths never appear in `chezmoi managed`,
`chezmoi diff`, or the guest's `$HOME` (proven in E0). Layer-3 contents:
`projects.toml` (project switcher), personal scripts in `bin`, aliases with a
personal path, and the `encrypted_` files from §4.

---

## 3 · the `rice` command

**Where it lives.** `dot_local/bin/executable_rice` → `~/.local/bin/rice`.
Bash, no dependency beyond `chezmoi` + coreutils.

**Dispatcher.** A thin argument router, no logic of its own:

| Subcommand | Does | Item |
| ---------- | ---- | ---- |
| `rice apply` | safe-apply guard (below) | E1a |
| `rice diff` | `chezmoi diff` passthrough | E1a |
| `rice onboard` | calls `rice-onboard` (§5) | E5 |
| `rice rollback [<ts>]` | restore from the newest backup, or the given timestamp | E1a |
| `rice doctor` | stub: prints `not implemented (track B)`, exits 0 | B1 |

Track C1 later hangs `theme`, `wallpaper`, toggles, scratchpads off the same
dispatcher.

### `rice apply` — flow (P5)

1. `chezmoi diff`. Empty → print `nothing to apply`, exit 0.
2. For every path `apply` would create / overwrite / remove (from
   `chezmoi status` / `chezmoi diff`): `cp --parents` the current state into
   `~/.local/state/rice/backup/<timestamp>/`. A path that does not exist yet is
   recorded in `<timestamp>/.created` so rollback deletes it instead of
   restoring.
3. Write `<timestamp>/manifest` — the path list plus the source git commit.
4. Prompt `y/N`. `N` → abort; the (inert) backup stays.
5. `chezmoi apply`.
6. Print `rollback: rice rollback <timestamp>`.

### `rice rollback`

Reads the manifest, `cp`s saved files back, deletes anything listed in
`.created`. Best-effort, documented as "returns you to the pre-apply state" —
not a transactional system.

### retention

`rice apply` prunes `~/.local/state/rice/backup/` to the last 10 entries.
`~/.local/state/` is the XDG spot for this and is never in the repo.

A bare `chezmoi apply` still bypasses the guard (D7). `README.md` and this file
state plainly: use `rice apply`.

---

## 4 · bootstrap and secrets

### bootstrap scripts (E3)

In `.chezmoiscripts/`, run at the end of every `chezmoi apply`:

- `run_onchange_before_10-packages.sh.tmpl` — installs packages. `run_onchange_`
  hashes the rendered content, so it re-runs only when the list changes and is
  otherwise silent. The `.tmpl` embeds the list, so adding a package changes
  the hash and triggers a re-run.
- `run_onchange_after_20-services.sh.tmpl` — `systemctl --user enable --now`
  for the user units (hypridle, hyprpaper / grootshell, …).

### package-manager abstraction (E3a)

`.chezmoidata/packages.toml`:

```toml
base    = ["git", "starship", "fzf", "zoxide", "age", "gum"]
desktop = ["hyprland", "kitty", "mako", "waybar", "yazi", "btop"]

[map.btop]
  apt = "btop"
[map.hyprland]
  apt = "hyprland"   # placeholder — Parrot likely needs a backport / build
```

The script picks `dnf` vs `apt` from `{{ .chezmoi.osRelease.id }}` (`fedora` →
dnf; `debian` / `parrot` / `kali` → apt), resolves divergent names through
`[map]`, installs `base` always and `desktop` unless `profile = guest`.
Idempotent — installs only what is missing.

### sudo (P3)

`apply` never runs `sudo` silently. The package script **detects** what is
missing and **prints the `sudo dnf install …` / `sudo apt install …` line for
you to run**. `systemctl --user` needs no root and runs directly. Documented in
the cookbook (§6).

### secrets (E4) — age

`.chezmoi.toml.tmpl` sets `encryption = "age"` plus a public recipient. The
private key lives at `~/.config/chezmoi/key.txt` (`chmod 600`, never in the
repo; backed up by hand / in a password manager). One example only:
`encrypted_private_dot_config/rice/example-secret.age`, gated to
`profile == personal`. Documented flow: `chezmoi add --encrypt <file>`,
`chezmoi edit <file>`. A guest or a host without the key simply does not get the
file — no error.

---

## 5 · onboarding wizard (E5)

**Piece.** `dot_local/bin/executable_rice-onboard`, invoked by `rice onboard`.
Bash + `gum` for the TUI (menu, input, confirm). Fallback: no `gum` → plain
`read` / `select`. Degrades, does not break.

**Flow:**

1. **Deps** — check `chezmoi`, `git`, `age`. Missing → print the
   `sudo dnf/apt install …` line (same rule as §4, never a silent install).
2. **Init** — no `~/.config/chezmoi/chezmoi.toml` → `chezmoi init <repo>`.
3. **Profile** — `gum choose personal guest`.
4. **Host** — list hosts already in `.chezmoidata/hosts.toml` + a "new" option.
   New host, detect and pre-fill:
   - monitors: `hyprctl monitors -j` → build the lines, `gum confirm` / edit
   - `kb_layout`: `localectl status`
   - `gpu`: `lspci | grep -E 'VGA|3D'` → `nvidia` / `intel` / `amd`
   - `scale`: prompt, default `1`
5. **Where the host data goes:**
   - `profile = personal` → write the `[hosts.<name>]` block **into the repo's
     `.chezmoidata/hosts.toml`** and print *"commit this to restore the machine
     later"*. This is goal 4 in practice.
   - `profile = guest` → write to `~/.config/chezmoi/chezmoi.toml` as
     `[data.hosts.<name>]`, **local**, never touching the repo. The guest's
     machine stays intact.
6. **Apply** — call `rice apply` (§3: diff + backup + confirm).

**Scope.** Initial machine setup only. Theme / wallpaper / toggle switching is
track C1 on the same `rice`.

---

## 6 · migration, docs, testing, boundaries

### incremental migration (D2)

Per package, each one commit: `chezmoi add` → confirm `chezmoi diff` **empty**
(target identical to current) → `make unstow PKG=<x>` → `rice apply` (replaces
the symlink with a real file, content identical) → `stow -D` cleanup → commit.

| Wave | Packages | Risk / reason |
| ---- | -------- | ------------- |
| 1 | `shell` `starship` `git` `environment.d` | trivial, no host, no template |
| 2 | `kitty` `yazi` `yt-x` `bin` | plain files; `bin` exercises `executable_` |
| 3 | `hypr` `kde` | **the hard wave** — `machine.lua.tmpl`, `.chezmoidata/hosts.toml`, templated `monitors` / `hyprpaper` / `hyprlock` |
| 4 | `cursor` `konsole` | closes out; validates `_legacy_ini_backup` as `readonly_` |

Files in waves 1–2 are layer 1 by default. The layer *concept* — the `profile`
prompt, the templated `.chezmoiignore` gate — and bootstrap land with wave 3,
where the first host data appears. `age` + example: wave 4. Stow and chezmoi coexist
between waves; any package reverts to Stow by reverting its commit +
`git checkout <old path>` + `make <host>`.

**Whole-migration rollback:** each wave is an isolated commit;
`_legacy_ini_backup/` stays the Hyprland return point; `git revert` +
`make desktop` restores Stow.

### status

| Wave | Packages | State |
| ---- | -------- | ----- |
| 1 | `shell` `starship` `git` `environment.d` | **done** (`track-E-wave-1.md`) — `dot_bashrc.d/`, `dot_config/`, `dot_gitconfig`; verifier `test/wave-1.sh` |
| 2 | `kitty` `yazi` `yt-x` `bin` | todo |
| 3 | `hypr` `kde` | todo |
| 4 | `cursor` `konsole` | todo |

Wave 1 notes: on the `desktop` host these four packages were already
plain files (not Stow symlinks), so there was no `make unstow` step —
`chezmoi diff` was verified empty, then `chezmoi apply`. `rice` does not
exist yet (its own plan), so wave 1 used `chezmoi diff` + `chezmoi apply`
directly. Each not-yet-migrated Stow dir has a `/name` line in
`.chezmoiignore`; a wave removes its line when it converts the package.

**`git` note:** `dot_gitconfig` carries `user.name`, the LFS filter, and
`[include] path = ~/.config/git/local`. The real `user.email` lives only in
that machine-local file (in `.chezmoiignore`, never committed). `git config
--get user.email` follows the include; `git config --global --get` does
**not** (it skips includes) — use the plain form to verify. On a new
machine, create it with
`git config -f ~/.config/git/local user.email "<you@example.com>"` — until
then commits have no email set. Wave 3's `rice onboard` will prompt for it.

### docs (E6) — formalise the repo's own conventions (D10)

- **`docs/track-E.md`** (this file) grows a **step-by-step cookbook**: change a
  monitor, add a host, add a package, add a secret, revert an apply, roll a
  package back to Stow. Plus where each layer lives and how to test a change (P4).
- **`README.md`** rewritten: chezmoi quickstart instead of Stow; a "restore on a
  new machine" section (`rice onboard`).
- **`CONTRIBUTING.md`** — new. Documents the existing `.gitignore`
  deny-by-default rule, the `docs/<topic>.md` pattern, and the `type(scope):`
  commit style already in `git log`. Nothing imported from other repos.
- **`CLAUDE.md`** — the minimal format Claude Code expects; repo facts only.
- **`.github/workflows/check.yml`** — minimal fix so it does not break (drop the
  `stow --simulate` / `gitleaks` steps that no longer apply). Real CI
  (shellcheck, stylua, JSON-schema, `chezmoi execute-template` dry-run) is
  track B2.

### testing (E0 lab pattern — fake `$HOME`, nothing touches `~` or the real repo)

- `test/` in the repo: `chezmoi apply --dry-run` / `diff` against a fake
  `$HOME`; assert content per profile (`personal` sees layer 3, `guest` does not).
- `rice apply`: fake `chezmoi` + fake `$HOME`; assert the backup is created and
  `rice rollback` restores.
- `rice-onboard`: `hyprctl` / `localectl` / `lspci` mocked on `PATH`; assert the
  resulting TOML.
- Scripts: `shellcheck`. Templates: `chezmoi execute-template` for each host.

### component boundaries — each piece testable alone

| Piece | Does | Depends on |
| ----- | ---- | ---------- |
| `rice` (dispatcher) | routes the argument | — |
| `rice apply` (lib) | diff + backup + apply + prune | `chezmoi`, coreutils |
| `rice rollback` | restore from the manifest | backup dir |
| `rice-onboard` | detect + prompt + write TOML | `chezmoi`, `gum` (opt) |
| `.chezmoidata/*.toml` | pure data (hosts, packages) | — |
| `.chezmoiscripts/run_onchange_*` | bootstrap, one file per concern (packages, services) | `packages.toml`, `osRelease` |
| `machine.lua.tmpl` + templates | render only, read data, no logic | `.chezmoidata` |

---

## out of scope — belongs to track A

Converting configs into token `.tmpl` files, the token contract,
`theme use <provider>`. Track E only guarantees that every matugen-generated
file is in `.chezmoiignore` and that the template mechanism exists.

## done when

1. Clean Fedora VM + `rice onboard` → full `desktop` back, no manual step.
2. The Parrot notebook runs the same layer 1 via the same repo.
3. A guest install (`profile = guest`) touches nothing outside its scope —
   monitors, GPU env, personal config all untouched.
4. `rice apply` on either host: `chezmoi diff` empty against the pre-migration
   `$HOME` for every migrated package.

## open risks

- **Hyprland on Parrot** — `hyprland` may not be packaged for Parrot; the
  `[map.hyprland] apt` entry is a placeholder. Resolve in the wave-3 plan
  (backport, COPR-equivalent, or build).
- **`hyprland.lua` `dofile` path** — the generated `machine.lua` path must
  resolve the same whether run by Hyprland or by a test harness. Pin an
  absolute `~/.config/hypr/machine.lua` in the `dofile` call.
- **`rice apply` path enumeration** — `chezmoi status` output format must be
  parsed defensively; a format change should fail closed (abort, keep backup),
  never apply without a backup.
