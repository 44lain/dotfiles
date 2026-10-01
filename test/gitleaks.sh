#!/usr/bin/env bash
# The gitleaks allowlist must cover the pinned sha256 digests in packages.toml
# and nothing else: a real-looking secret in any other file must still be caught.
set -u

test_dir=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$test_dir/.." && pwd)
fail=0
pass()  { printf '  ok   %s\n' "$1"; }
flunk() { printf '  FAIL %s\n' "$1"; fail=1; }

if ! command -v gitleaks >/dev/null; then
	echo "  skip gitleaks not installed"
	exit 0
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# --- 1. packages.toml with the repo's config: no leaks -------------------------
a="$tmp/a"
mkdir -p "$a/.chezmoidata"
cp "$repo/.chezmoidata/packages.toml" "$a/.chezmoidata/packages.toml"
[ -f "$repo/.gitleaks.toml" ] && cp "$repo/.gitleaks.toml" "$a/.gitleaks.toml"
git -C "$a" init -q
git -C "$a" add -A
git -C "$a" -c user.name=t -c user.email=t@example.invalid commit -q -m t
if gitleaks detect --source "$a" --no-banner --redact >/dev/null 2>&1; then
	pass "gitleaks: pinned digests in packages.toml are allowed"
else
	flunk "gitleaks reports a leak in packages.toml (pinned sha256 digests)"
fi

# --- 2. the allowlist is not a blanket pass -------------------------------------
b="$tmp/b"
mkdir -p "$b"
cp "$repo/.gitleaks.toml" "$b/.gitleaks.toml" 2>/dev/null
printf 'api_key = "AKIAIOSFODNN7EXAMPLE"\n' > "$b/other.toml"
printf 'api_key = "%s"\n' \
	"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" > "$b/hex.toml"
git -C "$b" init -q
git -C "$b" add -A
git -C "$b" -c user.name=t -c user.email=t@example.invalid commit -q -m t
if gitleaks detect --source "$b" --no-banner --redact >/dev/null 2>&1; then
	flunk "gitleaks no longer reports a fake key outside packages.toml"
else
	pass "gitleaks: a key in any other file is still reported"
fi

exit "$fail"
