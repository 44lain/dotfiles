SHELL := /bin/bash
STOW   ?= stow
TARGET ?= $(HOME)

# Packages per host role. Kept explicit rather than auto-detected: a wrong
# guess here silently symlinks a desktop config onto a headless server.
DESKTOP := shell starship konsole cursor kde git bin hypr
PENTEST := shell starship konsole cursor kde git
SERVER  := shell starship git

.DEFAULT_GOAL := help

.PHONY: help desktop pentest server unstow dry-run check bashrc-hook cursor-extensions

help:
	@echo "Targets:"
	@echo "  make desktop            stow $(DESKTOP)"
	@echo "  make pentest            stow $(PENTEST)"
	@echo "  make server             stow $(SERVER)"
	@echo "  make dry-run PKG=shell  simulate one package, change nothing"
	@echo "  make unstow PKG=shell   remove one package's symlinks"
	@echo "  make bashrc-hook        add the ~/.bashrc.d loop (Debian/Parrot only)"
	@echo "  make cursor-extensions  install the extensions listed in docs/"
	@echo "  make check              shellcheck + gitleaks"

desktop: ; @$(STOW) --target=$(TARGET) --restow --verbose $(DESKTOP)
pentest: ; @$(STOW) --target=$(TARGET) --restow --verbose $(PENTEST)
server:  ; @$(STOW) --target=$(TARGET) --restow --verbose $(SERVER)

dry-run:
	@test -n "$(PKG)" || { echo "usage: make dry-run PKG=<package>" >&2; exit 2; }
	@$(STOW) --target=$(TARGET) --simulate --verbose=2 $(PKG)

unstow:
	@test -n "$(PKG)" || { echo "usage: make unstow PKG=<package>" >&2; exit 2; }
	@$(STOW) --target=$(TARGET) --delete --verbose $(PKG)

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
		shellcheck --severity=style shell/.bashrc.d/*.sh bin/bin/*.sh bin/.local/bin/* || fail=1; \
	else echo "shellcheck not installed — skipped" >&2; fi; \
	if command -v gitleaks >/dev/null; then \
		gitleaks detect --source . --no-banner --redact || fail=1; \
	else echo "gitleaks NOT installed — cannot verify before push" >&2; fail=1; fi; \
	exit $$fail
