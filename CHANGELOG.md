# Changelog

Notable changes, newest first. Versions follow [Semantic Versioning](https://semver.org/)
loosely: while the major version is 0, the interface (`rice` commands, `hosts.toml`
keys, installer flags) can still change between minors.

## [0.1.0] - 2026-10-08

First tagged state. Everything below was built before tagging; this entry is the
baseline to pin to (`git checkout v0.1.0`).

### Added
- **Arch family** (Arch, EndeavourOS, CachyOS, Garuda; Manjaro if its repos carry
  Hyprland 0.55+). Installs with `pacman -Syu --needed`; Artix is refused
  (needs systemd). Verified in containers only.
- **Guided installer** (`install.sh`, `rice tui`): scans what is missing, shows the exact
  commands, installs after confirmation, configures and verifies. English and Português.
- **End-to-end test harness** (`make e2e-check`): the installer driven through a pty in
  containers, cells in parallel, one verdict line per cell.
- **Debian family** support (Debian 13 with backports, Ubuntu, Mint, Kali, Parrot, Pop!_OS)
  with Hyprland 0.55+ detection, and `make distro-check` (package names, guest install,
  `hyprland.lua` validation in containers).
- **`rice` command family**: `apply` (diff, backup, confirm), `rollback`, `uninstall`,
  `onboard` (git identity, wallpaper, host autodetection), `doctor`.
- **Profiles and hosts**: `guest` / `personal` profile, per-host monitors, keyboard
  layout, GPU env and apps from `.chezmoidata/hosts.toml`.
- CI: shellcheck, gitleaks, template/unit tests on every push; the slow distro matrix on
  relevant paths, weekly and on demand.

### Changed
- Repository migrated from GNU Stow to chezmoi (see `docs/track-E.md`).
- Git history rewritten once before going public (secrets audit).

### Known gaps
- No full desktop run confirmed on real Arch or Debian-family hardware.
- No screenshots yet.
- Theme engine (track A), perf pass and stylua/schema CI are still on the
  [roadmap](docs/ROADMAP.md).

[0.1.0]: https://github.com/44lain/dotfiles/releases/tag/v0.1.0
