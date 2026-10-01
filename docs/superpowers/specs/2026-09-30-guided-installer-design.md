# Guided installer (TUI) — design

Date: 2026-09-30 · Status: draft, awaiting review

## Intent

A stranger on a fresh machine runs one command and ends with the whole rice
working, without reading documentation. Today `rice doctor` only **prints** what
is missing, and the first install on Parrot OS 7 needed an AI assistant to
finish. This adds a guided, terminal-based installer that **detects every
missing dependency, installs them in one confirmed plan, configures the user's
preferences, and verifies the result** — all from one interface.

Success looks like:

1. From a machine with nothing but a shell, one command leads to a working rice.
2. The user sees exactly what will run before it runs, and **nothing installs
   without an explicit confirmation**.
3. Every user action gets visible feedback; every error says what to do next.
4. The existing commands (`rice apply`, `diff`, `rollback`, `uninstall`,
   `onboard`, `doctor`) keep working exactly as they do now.
5. Everything stays hand-editable and understandable by its maintainer
   (colours, texts, package recipes), with no framework to learn.

What the maintainer said, versus what is assumed:

| Said | Assumed (correct me) |
| ---- | -------------------- |
| Full scope: detect → install everything at once → configure the user's setup (wallpaper folder, Grootshell, session hint) | "Configure" stops at the files listed in §3; it does not tune the user's desktop |
| Existing commands stay as they are; the TUI is a new layer | `rice` with no arguments opens the TUI only on an interactive terminal |
| Interface in the style of the Hermes setup screen (boxed frame, arrow keys) — visual reference only | No Hermes code or dependency; the reference is the layout and key hints |
| Python, standard library only (`curses` + ANSI) | Needs Python ≥ 3.11 (`tomllib`); no installer for a newer Python |
| Pinned download URLs with `sha256` | They go stale loudly (clear error), like the ProtonVPN pin in `linux-bootstrap` |
| Texts in English **and** pt-BR | Language from `$LANG`, switchable; English fallback per missing key |
| Two entry paths: one-liner and manual | Both documented in the README |

## Findings that shape the design

From a first install on Parrot OS 7 (Debian 13 base) and a follow-up debugging
session on the same machine:

1. `rice` was "not found" in the shell right after `chezmoi apply` (`~/.local/bin`
   not yet on `PATH`).
2. The host prompt lists the maintainer's hosts; a guest picked one instead of
   `new`, which skipped monitor/keyboard/GPU detection.
3. `wallpaper_path` accepted a **folder**; `rice doctor` failed on it later.
   There are three distinct settings (§3) and nothing explained the difference.
   One typed path also lost its leading `/`.
4. `rice doctor` prints three or four `apt` lines with different `-t` suites;
   there is no single "install everything" step.
5. `matugen` is not packaged for Debian; `cargo install matugen` failed because
   the distro Rust (1.85) is older than the crate requires (1.88). A pinned
   release binary with a checksum worked.
6. Tools outside apt (`gum`, `yazi`) only had a note; Neovim ≥ 0.11.2 (for
   LazyVim) is not checked at all.
7. The three required fonts reported `FAIL` with no install step; the result was
   icon names rendered as text. Installing them per user, without root, works
   (download → `~/.local/share/fonts/` → `fc-cache`).
8. Grootshell was a manual `git clone` plus a hand-written config file.
9. `qs` and `hypridle` reported `FAIL` while the user was still in another
   session (they only run inside Hyprland).
10. Two `shell.json` files exist: the one that counts is
    `~/.config/grootshell/shell.json`; a root-owned untracked copy inside the
    clone was edited first.
11. An `apt install` failed on a backports version conflict
    (`libxkbcommon-dev` pinned to an older `libxkbcommon0`). A simulation before
    asking for confirmation would have shown it.
12. Slow login into the Hyprland session was reported and **not diagnosed** —
    out of scope here.

## Design

### 1. Structure and data

New files (none are deployed by chezmoi; all listed in `.chezmoiignore`):

- `install.sh` (repo root) — the entry point (§5).
- `installer/` — a Python package, standard library only:
  - `model.py` — reads `packages.toml`, detects the distro family, scans,
    builds the plan.
  - `recipes.py` — executes recipes.
  - `validate.py` — wallpaper, paths, `shell.json`, git identity.
  - `ui.py` — `curses` widgets, plus the colour/frame constants block.
  - `screens.py` — the eight screens (§2, §3).
  - `messages/en.py`, `messages/pt_br.py` — texts keyed by id.
- `rice` gains `rice tui`. With no arguments it opens the TUI **only when stdin
  and stdout are terminals**; otherwise it prints usage as today. Every other
  subcommand is unchanged.

`.chezmoidata/packages.toml` stays the single source of truth. Each entry gets
an optional `recipe` block, used when the distro does not package the item
(`debian = ""` etc.). Decision order per item: **distro package → recipe →
`manual` text**.

Recipe kinds — a small closed set, one function each in `recipes.py`:

| Kind | Used for | Fields |
| ---- | -------- | ------ |
| `release-binary` | matugen | `url`, `sha256`, `member`, `dest` |
| `apt-repo` | gum, yazi | `key_url`, `key_sha256`, source line, package |
| `dnf-copr` | Hyprland/Quickshell stack on Fedora | COPR name |
| `fonts` | Material Symbols Rounded, Rubik, CaskaydiaCove | list of `url` + `sha256`; installed to `~/.local/share/fonts/` then `fc-cache` |
| `git-clone` | Grootshell fork | `url`, `branch`, `dest` |

Every recipe can **describe itself** as text and **run itself**. The plan screen
shows the description, so the user sees the exact commands and sources.
Download URLs are **pinned to a version with `sha256`**: a stale pin fails with
a clear message instead of installing unverified bytes. A recipe declares the
architecture it supports (initially `x86_64`); on another architecture the item
falls back to its `manual` text.

### 2. Scan, plan, install

**Scan.** Each `packages.toml` item gets one of: `ok`, `missing`, `too old`
(against `min_version`), or `no source` (the distro lacks it and there is no
recipe; only the `manual` text applies). On the Debian family the scan asks
apt's local cache (`apt-cache madison`, `policy`) for the right `-t <suite>`,
exactly as `rice doctor` does. A test checks that the Python scan and
`rice-doctor` agree on the same data.

**Plan.** Required items are pre-selected, optional ones are not; one key toggles
all. Execution order: repositories (`apt-repo`, `dnf-copr`) → distro packages
grouped into the fewest commands per suite → recipes (binary, fonts, clone). The
screen shows each command and its origin.

**Simulation before confirming.** Distro-repo packages go through a dry run
(`apt-get -s install`; `dnf` with `--assumeno`; the pacman equivalent is
confirmed at implementation time, and if none exists the simulation is skipped
with a notice). A conflict such as the backports one is shown on the plan screen
before anything is installed. Items that depend on a third-party repository can
only be checked after that repository is added, so they are verified at install
time.

**Install.** Steps run in order; the last output lines are shown in a pane and
the full log goes to `~/.local/state/rice/install-<date>.log`. `sudo` is
authenticated once at the start (the terminal is released from the TUI for that
moment) and asked again if the credential expires. When a step fails the user
sees the error excerpt and chooses *retry*, *skip* or *abort*; independent steps
continue. A final summary lists installed, skipped and failed items.

Guarantees:

- Running again re-scans, so only what is still missing enters the plan.
- Package installs are **not** reverted by the rice; the plan screen says so.
  Applied configuration stays reversible with `rice rollback`.

### 3. Preferences and validation

Three different settings were conflated on the first install. The preferences
screen separates and explains them:

| Setting | Stored in | Used by |
| ------- | --------- | ------- |
| Wallpaper **folder** | `~/.config/grootshell/shell.json` → `wallpaper.directory` | Grootshell's wallpaper picker |
| Lock-screen **image** (optional) | `~/.config/chezmoi/chezmoi.toml` → `wallpaper_path` | `hyprlock`, `hyprpaper` |
| Git name and e-mail | `~/.config/git/local` | this machine only |

Validation gives feedback before anything is written:

- **Folder:** must be an absolute path (`~` is expanded; a path missing its
  leading `/` is rejected with the reason), must exist and be a directory. The
  screen shows how many images it found ("933 images found"). If it finds none
  and a parent folder holds images, it suggests the parent.
- **Lock-screen image:** must be an image file. Given a folder, the screen
  explains the difference and offers to pick an image inside it, or to skip.
- **E-mail:** format check only; the name must not be empty.

Writing `shell.json`: read the existing file and change **only**
`wallpaper.directory`, preserving every other key. If the existing file is
invalid JSON it is **not** overwritten; the error is shown and the user decides.
The `shell.json` inside the Grootshell clone is never touched. The file is the
user's preference, so `rice uninstall` leaves it alone.

**Profile and host (screen 2).** Outside Hyprland `hyprctl` does not exist, so
monitor detection falls back to `preferred/auto` (which works); keyboard comes
from `localectl`, GPU from `lspci`. The default for `guest` is a **new** host;
the maintainer's hosts are hidden behind an explanation.

**`rice-onboard` gets optional flags** (`--profile`, `--host`, `--git-name`,
`--git-email`, and the wallpaper values) so the TUI collects answers and calls
it, rather than re-implementing the file writes and the detection. With no flags
its behaviour is unchanged. `chezmoi init` asks profile and host itself; the
flow passes those answers (for example with `--promptString`) so the user is not
asked twice. The exact mechanism is validated during implementation.

### 4. Interface

Look (after the reference screen): a frame with a title and the current step
(`rice setup · 3/8`) and a footer with the key hints
`↑↓ navigate · ENTER/SPACE select · ESC cancel · ← back`.

Six components in `ui.py`: single-choice menu, checkbox list, text field with a
default and live validation message, table (the scan), progress pane with the
last log lines, confirmation box.

**Feedback rule.** Every action gets a visible response: validation appears under
the field; every step shows pending / running (spinner) / ok / warning / failed;
every error says what happened **and what to do next**; leaving with ESC
mid-flow states what was already done and what was not.

**Robustness.**

- Screens talk to an abstract UI with two implementations: `CursesUI` and
  `PlainUI` (`print`/`input`). Without an interactive terminal, or with
  `TERM=dumb`, the same questions run in `PlainUI`.
- Minimum 80×24; a smaller window shows a notice, and resize is handled.
- UTF-8 frame characters, ASCII fallback when the locale is not UTF-8; `NO_COLOR`
  is respected.
- Colours, frame characters and the minimum size live in one constants block at
  the top of `ui.py`.

**Languages.** Texts live in `messages/en.py` and `messages/pt_br.py`. Language
comes from `$LANG`, can be switched on the first screen or with `--lang`, and
falls back to English for a missing key. A test asserts the two files have the
same keys. Messages printed by the existing bash commands stay in English.

**Screens.**

1. Welcome and detection (distro, Hyprland version, current session, what is
   already installed).
2. Profile and host.
3. Preferences (§3).
4. Scan.
5. Plan, with simulation result and mandatory confirmation.
6. Install.
7. Configure: `rice apply` with preview, Grootshell clone and `shell.json`,
   fonts, the `~/.bashrc` loader.
8. Verify: `rice doctor`, with session-aware results (no false `FAIL` for `qs`
   and `hypridle` outside Hyprland), then "next steps" and **how to go back**.

### 5. Entry point and installation from zero

Two documented paths: the one-liner
(`curl -fsSL https://raw.githubusercontent.com/44lain/dotfiles/main/install.sh | sh`) and
the manual one (`git clone`, then `./install.sh`) for anyone who wants to read
the script first.

`install.sh` (POSIX `sh`, short and commented):

1. Detects the distro family.
2. Checks `python3` ≥ 3.11, `git`, `curl`, `chezmoi`.
3. **Shows what is missing and asks for confirmation**, then installs only that
   minimum with the distro package manager (`chezmoi` uses the README's current
   method).
4. Clones the repo into chezmoi's source directory.
5. Reattaches the terminal (`exec </dev/tty`, because under `curl | sh` stdin is
   the script itself) and opens the TUI.

If Python is older than 3.11 it says so plainly and stops; it never installs a
newer Python. Running it again resumes: it does not reinstall or update the repo,
it reopens the TUI, which re-scans. After the first `rice apply`, `rice tui` finds
the installer through `chezmoi source-path`.

### 6. Leaving the rice (going back to another desktop)

Installing the rice adds a session entry to the login manager; it does not change
the user's other sessions. The repo enables and masks no services, and the
Hyprland configuration is read only inside a Hyprland session, so the user can
log out and pick their previous desktop. What persists everywhere:

- The shell: a loader appended to `~/.bashrc`, the Starship prompt (only if
  Starship is installed), and `~/.local/bin` on `PATH`.
- Existing user configs the rice manages (`~/.gitconfig`, kitty, yazi, starship)
  are replaced by the rice's, after `rice apply`'s preview and backup;
  `rice rollback` / `rice uninstall` restore them.
- Installed packages, third-party apt repositories added by `apt-repo` recipes,
  fonts, the Grootshell clone and the matugen binary stay on the system.

Changes this makes:

- Screen 8 shows a **"how to go back"** block (log out, choose the previous
  session in the login manager's session selector) and lists what stays
  installed and what `rice uninstall` does and does not undo.
- `rice onboard` records the `~/.bashrc` loader it appends so `rice uninstall`
  can remove it, after asking. Today that line is not reverted.
- On Ubuntu-family systems the scan marks Hyprland as `no source` unless the
  release ships 0.55+, and shows the `manual` text; the installer never adds
  Debian repositories there.

### 7. Testing and verification

All Python tests use the standard-library `unittest` (no `pytest`) and run in
`make test` and CI.

- **`model.py`:** scan and plan over a test `packages.toml`, a fake `os-release`
  (the existing `RICE_OS_RELEASE` hook) and a fake `apt-cache` on `PATH`; plus the
  parity test against `rice-doctor`.
- **`validate.py`:** table-driven — path without leading `/`, missing folder,
  folder with no images (parent suggested), `shell.json` merge preserving other
  keys, invalid `shell.json` not overwritten.
- **`recipes.py`:** each recipe's description against expected text; execution
  against a local `file://` URL and `sha256`; a checksum mismatch aborts and
  leaves nothing behind; running twice is safe.
- **Screens:** a `FakeUI` with scripted answers. `CursesUI` gets a `pty` smoke
  test (draws, exits on ESC).
- **Messages:** `en` and `pt_br` have identical keys.
- **`rice-onboard` flags:** bash tests that the flags produce the same files as
  the interactive path, and that no flags changes nothing.
- **Containers**, same pattern as `test/distro`: the full flow in `fedora:43` and
  `debian:trixie` with `PlainUI` fed answers on `stdin`. Arch gets scan and plan
  only and stays documented as "install not verified".
- **Real-machine acceptance:** the flow is run for real on the Parrot notebook
  with a fresh user and clean `$HOME`, and `rice doctor` must end without `FAIL`
  (fakes alone missed real bugs in earlier `rice` work).
- **Staleness:** the weekly CI job also checks the pinned URLs (response and
  `sha256`); the versioned Material Symbols URL is the most fragile.

## Out of scope

- A non-interactive mode such as `--yes`.
- Installing a newer Python.
- Removing packages, repositories or fonts (`rice uninstall` still does not).
- TUI screens for `rollback` and `uninstall`; they remain commands.
- The slow Hyprland login, Deskflow and KDE Connect.
- Anything from Hermes.
- Automatic updating of pinned versions.
- Inventory of the pentest and server hosts.

## Open items for the implementation plan

- Exact mechanism to pass profile/host answers to `chezmoi init` without a
  second prompt (§3).
- Whether a dry run exists for pacman (§2).
- Confirm in containers that Fedora, Debian 13/Parrot and Arch ship Python ≥ 3.11
  (§5).
- Pin and checksum the real URLs for matugen, the three fonts, and the gum and
  yazi apt repositories (§1).
