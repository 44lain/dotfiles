SHELL := /bin/bash

# Stow retired 2026-09-12: every package that was still Stow-managed either
# migrated to chezmoi (docs/track-E.md) or was dropped from the repo (kde,
# cursor, konsole — too personal/idiosyncratic for a public "clone and use"
# rice). Install/apply goes through `chezmoi init` / `chezmoi diff` /
# `chezmoi apply` + `rice apply` (README), not `make`.

.DEFAULT_GOAL := help

.PHONY: help check test docs distro-check bashrc-hook cursor-extensions

help:
	@echo "Targets:"
	@echo "  make bashrc-hook        add the ~/.bashrc.d loop (Debian/Parrot only)"
	@echo "  make cursor-extensions  install the extensions listed in docs/"
	@echo "  make check              shellcheck + gitleaks"
	@echo "  make test               run test/*.sh (needs chezmoi; luajit optional)"
	@echo "  make docs               regenerate docs/dependencies.md from .chezmoidata/packages.toml"
	@echo "  make distro-check       verify package names and a guest install in containers (docker, network)"
	@echo ""
	@echo "To apply the dotfiles themselves: chezmoi init, chezmoi diff, chezmoi apply,"
	@echo "then 'rice apply' for any later change. See README.md."

test:
	@fail=0; \
	for t in test/*.sh; do \
		echo "==> $$t"; \
		bash "$$t" </dev/null || fail=1; \
	done; \
	exit $$fail

# Fedora's stock ~/.bashrc sources ~/.bashrc.d/*; Debian's and Parrot's do not.
# Idempotent: appends the loop only when it is not already present.
bashrc-hook:
	@if grep -q '\.bashrc\.d' "$(HOME)/.bashrc" 2>/dev/null; then \
		echo "already hooked: $(HOME)/.bashrc"; \
	else \
		printf '\n# Load ~/.bashrc.d fragments (managed by dotfiles)\nif [ -d ~/.bashrc.d ]; then\n    for rc in ~/.bashrc.d/*.sh; do\n        [ -f "$$rc" ] && . "$$rc"\n    done\n    unset rc\nfi\n' >> "$(HOME)/.bashrc"; \
		echo "hooked: $(HOME)/.bashrc"; \
	fi

cursor-extensions:
	@command -v cursor >/dev/null || { echo "cursor not on PATH" >&2; exit 1; }
	@while read -r ext; do \
		[ -n "$$ext" ] || continue; \
		echo "==> $$ext"; \
		cursor --install-extension "$$ext" --force || echo "FAILED: $$ext" >&2; \
	done < docs/cursor-extensions.txt

check:
	@fail=0; \
	if command -v shellcheck >/dev/null; then \
		shellcheck --severity=style dot_bashrc.d/*.sh test/*.sh test/distro/*.sh bin/executable_*.sh dot_local/bin/* || fail=1; \
	else echo "shellcheck not installed — skipped" >&2; fi; \
	if command -v gitleaks >/dev/null; then \
		gitleaks detect --source . --no-banner --redact || fail=1; \
	else echo "gitleaks NOT installed — cannot verify before push" >&2; fail=1; fi; \
	exit $$fail

docs:
	@tmp=$$(mktemp) && chezmoi --source "$(CURDIR)" execute-template < docs/dependencies.md.tmpl > "$$tmp" \
		&& mv "$$tmp" docs/dependencies.md || { rm -f "$$tmp"; echo "render failed, docs/dependencies.md untouched" >&2; exit 1; }
	@echo "wrote docs/dependencies.md"

distro-check:
	@bash test/distro/packages.sh && bash test/distro/guest-install.sh
