# Multi-distro support (Debian family + Arch) — design

Date: 2026-09-24 · Status: draft, awaiting review

## Intent

The rice is supported on Fedora only. The maintainer will test it next on a
notebook running **Parrot OS 7** (Debian 13 base, KDE Plasma installed
alongside), and wants the project usable on **Debian and derivatives** and on
**Arch**.

Success looks like:

1. Someone on Fedora, Debian/Parrot or Arch can find out **exactly which
   packages they are missing, and the command to install them**, without
   reading a doc.
2. The package names in that answer are **verified to exist** on each distro,
   not guessed.
3. The config runs on the oldest Hyprland the Debian family can actually get
   (0.55), or fails with a clear message when it cannot.
4. Nothing already working on Fedora changes.
5. **Non-negotiable (maintainer, 2026-09-24): it must work for other people, not
   only on the maintainer's machine.** A stranger on any Debian-family distro
   (Debian, Ubuntu, Mint, Kali, Parrot, Pop!_OS, Raspberry Pi OS, ...) gets from
   `chezmoi init` to a working rice by following the README alone. Nothing in
   code or docs may hard-code the maintainer's host, a distro codename
   (`trixie`, `echo`) or a repo name.

What the maintainer said, versus what is assumed:

| Said | Assumed (correct me) |
| ---- | -------------------- |
| Adapt for Debian/derivatives and Arch | "Derivatives" means Parrot, Kali, Ubuntu, Mint by `ID_LIKE`; only Debian/Parrot are a real target now |
| `rice doctor` should print the install command | Read-only; never runs `sudo` |
| Minimum Hyprland 0.55, validated on the notebook | Where 0.55 cannot work, we go back to requiring 0.56 rather than branching the config |
| Scope is `dotfiles` only | `linux-bootstrap` (private) is a later round |

## Findings that shape the design

- The **code is already almost distro-neutral**. Distro-specific text lives in
  `docs/dependencies.md`, the README, `rice-onboard`'s install hints and the
  `Makefile` bashrc hook. Two hard-coded paths exist:
  `/usr/bin/kdeconnectd` (in the maintainer's own host entry only) and
  `CONFIG_EDITOR="/usr/bin/nano"` in the yt-x template.
- Debian: Hyprland is **0.56.2 in sid/forky** and **0.55.2 in trixie-backports**;
  Quickshell 0.3.0 is in trixie-backports and sid; hyprlock is in trixie-backports.
- Parrot 7.3 (`ID=parrot`, `ID_LIKE=debian`, `VERSION_CODENAME=echo`) is Debian
  13 based and uses **its own repos** (`echo`, `echo-backports`). **Verified on
  the notebook (`apt-cache policy`):** `echo-backports` (priority 599) carries
  hyprland 0.55.2, quickshell 0.3.0, uwsm 0.26.7 and hyprpolkitagent 0.1.3;
  `echo` (priority 600) carries cliphist 0.5.0 and hyprland **0.52.2**. Because
  backports has the lower priority, a plain `apt install hyprland` installs the
  too-old 0.52.2; the install must use `-t echo-backports`. No repo mixing is
  needed on Parrot.
- `matugen` is not packaged for Debian/Parrot (needs `cargo`).
- `hyprland.lua` was written and tested on **0.56.2**. Whether every API it
  calls exists in 0.55 is **unknown**.

## Design

### 1. Package data — one source of truth

`.chezmoidata/packages.toml` lists every dependency once:

```toml
[packages.hyprland]
desc     = "compositor"
bin      = "Hyprland"        # looked up on PATH
required = true
fedora   = "hyprland"
debian   = "hyprland"
arch     = "hyprland"
note_debian = "needs backports: sudo apt install -t <codename>-backports hyprland (0.55+)"

[packages.matugen]
desc     = "wallpaper -> colour palette"
bin      = "matugen"
required = true
manual   = "cargo install matugen (Fedora/Debian); AUR matugen (Arch)"
```

- A family value is a package name; `""` means "not packaged, see `manual`".
- Entries without a package name for any family carry only `manual`.
- Adding a dependency is one block in one file.

### 2. Distro detection and `rice doctor`

- Family from `/etc/os-release`: `ID`, then `ID_LIKE`.
  `fedora|rhel` → fedora; `debian|ubuntu|parrot|kali` → debian;
  `arch` → arch; anything else → unknown.
- `rice-doctor` gains a `== dependencies ==` section. It reads
  `chezmoi data --format=json` (already how it reads `wallpaper_path`), checks
  each `bin` with `command -v`, and for the missing ones prints one command:
  `sudo dnf install …`, `sudo apt install …`, or `sudo pacman -S …`, followed
  by the `note_<family>` and `manual` lines that apply.
- **The apt suite comes from apt's own data, never from a codename table.** For a
  missing package on the debian family, doctor asks the local apt cache
  (`apt-cache madison`, `apt-cache policy`: read-only, no network, no root) for
  the newest version any configured source offers. If that is not the default
  candidate (Debian/Parrot backports, where the default is 0.52), it prints
  `sudo apt install -t <suite> <pkg>` using the suite apt itself reported.
  If the newest version is below the entry's `min_version`, or apt knows no
  such package, doctor says so plainly (with "run `sudo apt update` first") and
  points at `docs/dependencies.md` instead of printing a command that fails.
  This is what makes Debian, Ubuntu, Mint, Kali, Parrot and Pop!_OS behave
  correctly without listing them.
- Read-only. No `sudo`, no network. `RICE_OS_RELEASE` overrides the
  `os-release` path (test hook).

### 3. Hyprland version gate

- `rice-doctor` reads `Hyprland --version`; below **0.55** → `FAIL` with a
  message pointing at `docs/dependencies.md`. This is a real scenario on
  Parrot/Debian: an `apt install hyprland` without `-t` yields 0.52.2.
- Implementation task: compare every `hl.*` call in `hyprland.lua` against the
  0.55 Lua API documentation. Anything 0.56-only is adapted **without**
  version branches (choose the form both versions accept). If that is not
  possible for something essential, stop and raise it — the fallback is
  "require 0.56".
- The comment in `hyprland.lua` that says window rules exist "only in Lua on
  0.56" is checked for accuracy against 0.55 as part of this.

### 4. Onboarding and code adjustments

- `rice-onboard` install hints come from the same package data instead of the
  hard-coded `dnf`/`apt` lines.
- **`~/.bashrc.d` hook.** Debian/Parrot do not source it. `rice onboard`
  detects that `~/.bashrc` lacks the loop and asks `y/N` before appending it
  (idempotent, same text the Makefile target writes today). `make bashrc-hook`
  stays as the manual form.
- The notebook is a new `[hosts.<name>]`; `rice onboard` already detects
  monitors, keyboard and GPU.
- README: per-distro command to install `chezmoi` and `git`; note that the
  login session to pick in SDDM is the uwsm-managed Hyprland entry.
- `CONFIG_EDITOR` in the yt-x template stops hard-coding `/usr/bin/nano`.
- `docs/dependencies.md` is **generated** from `packages.toml`
  (`docs/dependencies.md.tmpl` rendered with `chezmoi execute-template`,
  `make docs`); a test fails when the committed file is out of date. Prose that
  is not a table (support statement, backports caveat) stays in the template.

### 5. Verification

Runs locally with Docker and in CI; these are the parts that can be checked
without the notebook.

- **Package names exist.** For each family, in a container: `debian:trixie`
  with backports enabled, `archlinux`, `fedora:43`, and `parrotsec/core` if
  that image is available — resolve every package name in `packages.toml`
  (`apt-cache policy` / `pacman -Si` / `dnf repoquery`). A name that does not
  resolve fails the check. AUR packages are skipped and listed as such.
- **Matrix.** Hard-fail images: `debian:trixie` (+ backports), `parrotsec/core`,
  `fedora:43`, `archlinux`. Report-only images (informational, they may
  legitimately lack Hyprland): `ubuntu:24.04`, `kalilinux/kali-rolling`.
  An image that cannot be pulled is skipped, not failed.
- **Stranger walk-through in containers** (`debian:trixie`, `ubuntu:24.04`,
  `fedora:43`): install chezmoi the documented way, apply as `profile=guest`,
  run `rice doctor`. Every template must render, and doctor must print the
  correct install command for that family.
- **Distro detection** and the **install-command output** are unit-tested with
  fake `os-release` files, in the existing fake-environment style of
  `test/rice-doctor.sh`.
- **Existing suite** (`make test`, `make check`) keeps passing unchanged.
- **Not verifiable here, left to the maintainer on the notebook:** Hyprland
  0.55 actually running this config, Quickshell/grootshell, uwsm session
  start, the GPU. The spec's success criterion 3 is confirmed only there.

## Error handling

- Unknown distro: doctor degrades to a list of missing binaries.
- Missing `jq`/`chezmoi` when doctor runs: existing behaviour (skip with a
  message), extended to the new section.
- `packages.toml` entry with a family key missing: treated as "not packaged",
  falls through to `manual`, never a template error.

## Out of scope

- `linux-bootstrap` provisioning scripts for Debian/Parrot/Arch.
- A `rice deps` command that installs packages, and any silent `sudo`.
- Per-Hyprland-version config branches.
- Ubuntu/Mint/Kali as **supported** targets — they resolve to the `debian`
  family and are "best effort, untested".
- Fixing Parrot repo policy: this design documents the trixie-backports route
  for plain Debian and marks Parrot as "verify on your install".

## Open questions and risks

1. **0.55 compatibility is unknown** until the API audit and the notebook run.
   Risk: something essential is 0.56-only.
2. ~~Parrot's Hyprland source unverified~~ **Resolved 2026-09-24:** Parrot
   `echo-backports` carries 0.55.2 (see Findings). Residual: apt prefers 0.52.2
   unless `-t` is used.
3. `matugen` has no Debian package; users need `cargo`.
4. The `parrotsec/core` image may not resolve the same package set as a full
   Parrot install; a pass there is evidence, not proof.

## Testing the result

Success criteria, checked in this order: (1) the package-existence check is
green for Fedora, Debian and Arch; (2) doctor unit tests pass for all three
families and an unknown one; (3) `make check` and `make test` still pass on
Fedora; (4) the maintainer runs `chezmoi init` → `rice onboard` → `rice doctor`
on the Parrot notebook and reports what fails.
