# shellcheck shell=bash
# PATH additions.
#
# Fedora's stock ~/.bashrc already prepends these, but Debian and Parrot
# do not. Guarded so running it twice never duplicates an entry.

for dir in "$HOME/.local/bin" "$HOME/bin"; do
    [ -d "$dir" ] || continue
    case ":$PATH:" in
        *":$dir:"*) ;;
        *) PATH="$dir:$PATH" ;;
    esac
done
unset dir
export PATH
