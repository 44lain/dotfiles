# Contributing

Issues and pull requests are welcome. This is a personal rice made public, so a change
that fits the maintainer's principles has the best chance of landing quickly.

## Principles

The full list is in [docs/ROADMAP.md](docs/ROADMAP.md#principles). The ones that decide most reviews:

- **Legible over clever.** Small, commented configs; no framework only one person understands.
- **One place per change.** A new package, host or theme surface means editing one file.
- **Secure by default.** No secrets in the repo; `apply` never runs `sudo`; a guest install
  never touches anything outside its scope.
- **Reversible.** Anything that writes to `$HOME` goes through the backup/diff path of `rice apply`.

## Setup

```bash
git clone https://github.com/lainciano/dotfiles && cd dotfiles
make check    # shellcheck + gitleaks (both must be installed)
make test     # test/*.sh (needs chezmoi, jq; luajit optional)
```

Before opening a PR, `make check` and `make test` must pass. They run in CI on every push.

If you touch packages, `install.sh`, `installer/`, `rice-doctor`, `rice-onboard` or
`hyprland.lua`, also run `make distro-check` (Docker and network required). For installer
flow changes, `make e2e-check` (slow); `E2E_ARGS="-d arch -v"` narrows it to one distro.

## Where things live

| To change | Edit |
| --- | --- |
| package names per distro | `.chezmoidata/packages.toml`, then `make docs` |
| a host (monitors, keyboard, GPU, apps) | `[hosts.<name>]` in `.chezmoidata/hosts.toml` |
| installer screens and messages | `installer/` (tests in `installer/tests/`) |
| the `rice` commands | `dot_local/bin/executable_rice*` |

Do not run a bare `chezmoi apply` on your clone to test; use `rice apply` so a backup exists.

## Commits and PRs

- Conventional style: `feat(scope):`, `fix(scope):`, `docs:`, `test:`, `ci:`, `chore:`.
- One topic per PR, with the reason in the description. No unrelated formatting churn.
- Add an entry to [CHANGELOG.md](CHANGELOG.md) under `Unreleased` for user-visible changes.
- Say what you actually ran and on which distro. "Verified in a container" and "verified on
  hardware" are different claims; please keep them apart.

## Adding a distro

Package names go in `packages.toml`, detection in the installer, and a row in
`test/distro/` plus an E2E cell. A distro is listed as supported only after those pass.
