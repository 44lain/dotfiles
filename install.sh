#!/bin/sh
# install.sh — entry point of the guided installer.
#   curl -fsSL https://raw.githubusercontent.com/44lain/dotfiles/main/install.sh | sh
# or, to read it first:
#   git clone https://github.com/44lain/dotfiles ~/.local/share/chezmoi && ~/.local/share/chezmoi/install.sh
#
# It checks the minimum the installer itself needs (python3 >= 3.11, git, curl,
# chezmoi), shows what is missing and ASKS before installing it, makes sure the
# repo is in chezmoi's source directory, then opens the TUI.
set -eu

REPO_URL=${RICE_REPO_URL:-https://github.com/44lain/dotfiles.git}
SRC=${CHEZMOI_SOURCE_DIR:-$HOME/.local/share/chezmoi}
TTY=${RICE_TTY:-/dev/tty}
OSR=${RICE_OS_RELEASE:-/etc/os-release}

say() { printf '%s\n' "$*"; }
die() { printf 'install.sh: %s\n' "$*" >&2; exit 1; }

family() {
	[ -r "$OSR" ] || { echo unknown; return; }
	# shellcheck disable=SC1090 # os-release path is a test hook; its content is plain KEY=value
	( . "$OSR"
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
missing=""
have python3 || missing="$missing python3"
have git     || missing="$missing git"
have curl    || missing="$missing curl"
need_chezmoi=0
have chezmoi || need_chezmoi=1

pm=""
if [ -n "$missing" ]; then
	case $fam in
		fedora) pm="sudo dnf install -y" ;;
		debian) pm="sudo apt-get install -y" ;;
		arch)   pm="sudo pacman -S --needed --noconfirm"
			missing=$(printf '%s' "$missing" | sed 's/python3/python/') ;;
		*) die "distro not recognised; install$missing yourself and run this again." ;;
	esac
fi

if [ -n "$missing" ] || [ "$need_chezmoi" -eq 1 ]; then
	say "To open the guided installer I first need:"
	[ -z "$missing" ] || say "  - system packages, with:  $pm$missing"
	[ "$need_chezmoi" -eq 0 ] || say "  - chezmoi: this downloads and runs a script from get.chezmoi.io, with:  sh -c \"\$(curl -fsLS get.chezmoi.io)\" -- -b ~/.local/bin"
	printf 'Install these now? [y/N] '
	read -r reply < "$TTY" || reply=""
	case $reply in y|Y|yes|YES|s|S|sim) ;; *) die "nothing installed; install them yourself and run this again." ;; esac
	if [ -n "$missing" ]; then
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

cd "$SRC"
exec python3 -m installer "$@" < "$TTY"
