#!/bin/sh
# install.sh — entry point of the guided installer.
#   curl -fsSL https://raw.githubusercontent.com/lainciano/dotfiles/main/install.sh | sh
# or, to read it first:
#   git clone https://github.com/lainciano/dotfiles ~/.local/share/chezmoi && ~/.local/share/chezmoi/install.sh
#
# It checks the minimum the installer itself needs (python3 >= 3.11, git, curl,
# jq, chezmoi), shows what is missing and ASKS before installing it, makes sure the
# repo is in chezmoi's source directory, then opens the TUI.
set -eu

REPO_URL=${RICE_REPO_URL:-https://github.com/lainciano/dotfiles.git}
SRC=${CHEZMOI_SOURCE_DIR:-$HOME/.local/share/chezmoi}
TTY=${RICE_TTY:-/dev/tty}
OSR=${RICE_OS_RELEASE:-/etc/os-release}

# tools installed in ~/.local/bin by an earlier run (chezmoi) must be found now
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$HOME/.local/bin:$PATH"; export PATH ;; esac

say() { printf '%s\n' "$*"; }
die() { printf 'install.sh: %s\n' "$*" >&2; exit 1; }

family() {
	[ -r "$OSR" ] || { echo unknown; return; }
	# shellcheck disable=SC1090 # os-release path is a test hook; its content is plain KEY=value
	( . "$OSR"
	  [ "${ID:-}" = artix ] && { echo artix; exit 0; }
	  for w in ${ID:-} ${ID_LIKE:-}; do
		case $w in
			fedora|rhel) echo fedora; exit 0 ;;
			debian|ubuntu) echo debian; exit 0 ;;
			arch) echo arch; exit 0 ;;
		esac
	  done
	  echo unknown )
}

have() { command -v "$1" >/dev/null 2>&1; }

# the terminal: under `curl | sh` stdin is this script, so ask the user through the tty
( : < "$TTY" ) 2>/dev/null || die "no terminal available to talk to you (run it from a terminal)"

# --- python: present AND new enough (never installed/upgraded to a newer one) -----
check_python() {
	python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
		|| die "python3 is older than 3.11 (the installer needs 3.11 or newer). Install a newer Python from your distribution and run this again."
	python3 -c 'import curses, tomllib' 2>/dev/null \
		|| die "this python3 lacks the 'curses' or 'tomllib' module; install your distribution's full python3 package and run this again."
}
if have python3; then check_python; fi

fam=$(family)
[ "$fam" = artix ] && die "Artix is not supported: the session needs systemd (uwsm and systemd user units)."
missing=""
have python3 || missing="$missing python3"
have git     || missing="$missing git"
have curl    || missing="$missing curl"
have jq      || missing="$missing jq"   # rice-onboard hard-requires it
need_chezmoi=0
have chezmoi || need_chezmoi=1

pm=""
upd=""   # package-list refresh, debian family only (stock images ship empty lists)
if [ -n "$missing" ]; then
	# root needs no sudo (and may not have it); anyone else needs it
	asroot=""
	if [ "$(id -u)" -ne 0 ]; then
		have sudo || die "sudo is not installed, so I cannot install$missing for you; install it yourself (as root) and run this again."
		asroot="sudo "
	fi
	case $fam in
		fedora) pm="${asroot}dnf install -y" ;;
		debian) upd="${asroot}apt-get update"
			pm="${asroot}apt-get install -y" ;;
		arch)   pm="${asroot}pacman -Syu --needed --noconfirm"   # -Syu: a stale database 404s; -Sy alone is a partial upgrade
			case $missing in *" python3"*) missing="${missing%% python3*} python${missing#*python3}" ;; esac ;;
		*) die "distro not recognised; install$missing yourself and run this again." ;;
	esac
fi

if [ -n "$missing" ] || [ "$need_chezmoi" -eq 1 ]; then
	say "To open the guided installer I first need:"
	if [ -n "$missing" ]; then
		say "  - system packages, with:"
		[ -z "$upd" ] || say "      $upd"
		say "      $pm$missing"
	fi
	[ "$need_chezmoi" -eq 0 ] || say "  - chezmoi: this downloads and runs a script from get.chezmoi.io, with:  sh -c \"\$(curl -fsLS get.chezmoi.io)\" -- -b ~/.local/bin"
	printf 'Install these now? [y/N] '
	read -r reply < "$TTY" || reply=""
	case $reply in y|Y|yes|YES|s|S|sim) ;; *) die "nothing installed; install them yourself and run this again." ;; esac
	if [ -n "$missing" ]; then
		# shellcheck disable=SC2086 # $upd is a space-separated command: splitting is intended
		[ -z "$upd" ] || $upd
		# shellcheck disable=SC2086 # $pm and $missing are space-separated word lists: splitting is intended
		$pm $missing
	fi
	if [ "$need_chezmoi" -eq 1 ]; then
		sh -c "$(curl -fsLS get.chezmoi.io)" -- -b "$HOME/.local/bin"
		PATH="$HOME/.local/bin:$PATH"
		export PATH
	fi
	# python3 may have just been installed by the package manager: it must pass the same check
	check_python
fi

# --- the repo in chezmoi's source directory ---------------------------------------
if [ ! -d "$SRC/.git" ]; then
	for f in "$SRC"/* "$SRC"/.[!.]*; do
		[ -e "$f" ] || continue
		die "$SRC exists, is not empty and is not a git checkout; move it away (or set CHEZMOI_SOURCE_DIR) and run this again."
	done
	git clone "$REPO_URL" "$SRC"
fi

# an existing checkout must be this repo and carry the installer
origin=$(git -C "$SRC" config --get remote.origin.url 2>/dev/null || true)
case $origin in
	""|*/dotfiles|*/dotfiles.git|*:dotfiles|*:dotfiles.git) ;;
	*) say "install.sh: warning: $SRC has origin $origin, which is not the dotfiles repo." ;;
esac
[ -f "$SRC/installer/__main__.py" ] || die "$SRC/installer/__main__.py is missing: that is not a checkout of the dotfiles repo with the installer. Move it away (or set CHEZMOI_SOURCE_DIR) and run this again."

cd "$SRC"
exec python3 -m installer "$@" < "$TTY"
