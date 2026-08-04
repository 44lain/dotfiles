# shellcheck shell=bash
# Starship prompt.
#
# Last fragment on purpose: starship must initialise after PATH is final,
# otherwise a starship installed under ~/.local/bin is not found yet.
# Skipped on non-interactive shells and when starship is absent.

case $- in
    *i*) ;;
    *) return 0 ;;
esac

command -v starship >/dev/null 2>&1 || return 0
eval "$(starship init bash)"
