# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private reporting:
**Security → Report a vulnerability** on this repository.

Include what you found, how to reproduce it, and the distro/version. Expect a first
reply within about a week; this is a one-person project.

## What counts

- `install.sh` and the installer (it runs as the user and calls `sudo` only after showing
  the exact command and asking).
- Anything that could write a secret into the repo, or execute downloaded code without
  verification (pinned downloads in `.chezmoidata/packages.toml` carry a sha256; `make pins-check` verifies them).
- Anything in `rice apply` / `rollback` / `uninstall` that touches files outside the managed set.

## Out of scope

Hyprland, chezmoi, grootshell and distro packages themselves: report those upstream.

## Supported versions

Only the latest tagged release and `main`.
