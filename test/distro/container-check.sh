#!/usr/bin/env bash
# Runs INSIDE a container. Usage: container-check.sh <family>
# Reads /rice/names.tsv (package<TAB>min_version) and reports every package
# the distro's repos do not know, or whose newest version is below min_version.
set -uo pipefail
family=$1
missing=0

case $family in
	debian)
		export DEBIAN_FRONTEND=noninteractive
		apt-get update -qq >/dev/null 2>&1
		# Plain Debian images ship without the backports suite; add it so the
		# check sees what a user with backports enabled sees.
		# shellcheck disable=SC1091  # exists only inside the container
		. /etc/os-release
		if [ "${ID:-}" = debian ] && ! grep -rqs "${VERSION_CODENAME}-backports" /etc/apt; then
			echo "deb http://deb.debian.org/debian ${VERSION_CODENAME}-backports main" > /etc/apt/sources.list.d/rice-bp.list
			apt-get update -qq >/dev/null 2>&1
		fi
		newest() {  # newest version apt knows for $1, empty if none
			apt-cache madison "$1" 2>/dev/null | awk -F'|' '{gsub(/ /,"",$2); print $2}' | sort -V | tail -1
		}
		;;
	fedora)
		# Stock Fedora has no Hyprland stack, yazi or starship. The names are
		# verified against the repos packages.toml tells the user to enable:
		# COPR sdegler/hyprland and Terra.
		dnf -q install -y dnf-plugins-core >/dev/null 2>&1
		dnf -q copr enable -y sdegler/hyprland >/dev/null 2>&1
		# shellcheck disable=SC2016  # $releasever is dnf's variable, not ours
		dnf -q install -y --nogpgcheck --repofrompath 'terra,https://repos.fyralabs.com/terra$releasever' terra-release >/dev/null 2>&1
		newest() { dnf -q -y repoquery --qf '%{version}\n' "$1" 2>/dev/null | sort -V | tail -1; }
		;;
	arch)
		pacman -Sy --noconfirm >/dev/null 2>&1
		newest() { pacman -Si "$1" 2>/dev/null | sed -n 's/^Version *: *//p' | head -1; }
		;;
	*) echo "unknown family $family"; exit 2 ;;
esac

while IFS=$'\t' read -r pkg minv; do
	[ -n "$pkg" ] || continue
	v=$(newest "$pkg")
	if [ -z "$v" ]; then
		echo "  MISSING $pkg"; missing=$((missing + 1))
	elif [ -n "$minv" ] && [ "$(printf '%s\n%s\n' "$minv" "$v" | sort -V | head -1)" != "$minv" ]; then
		echo "  TOO OLD $pkg $v (< $minv)"; missing=$((missing + 1))
	else
		echo "  ok      $pkg $v"
	fi
done < /rice/names.tsv
exit $((missing > 0))
