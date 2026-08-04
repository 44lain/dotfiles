# shellcheck shell=bash
# pnpm.
#
# Self-guarding instead of host-templated: on a machine without pnpm this
# is a no-op, so the same fragment can be stowed on every host. This is
# why the repo does not need chezmoi-style templates — see README.

PNPM_HOME="$HOME/.local/share/pnpm"
[ -d "$PNPM_HOME" ] || return 0

export PNPM_HOME
case ":$PATH:" in
    *":$PNPM_HOME/bin:"*) ;;
    *) export PATH="$PNPM_HOME/bin:$PATH" ;;
esac
