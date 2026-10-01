#!/usr/bin/env bash
# Every pinned download in packages.toml still resolves and still has the pinned sha256.
# Needs network (no docker); run with `make pins-check`.
set -u
repo=$(cd "$(dirname "$0")/../.." && pwd)
fail=0
tmp=$(mktemp -d); trap 'rm -rf "${tmp:?}"' EXIT
python3 - "$repo/.chezmoidata/packages.toml" > "$tmp/pins.tsv" <<'PY'
import sys, tomllib
for key, p in tomllib.load(open(sys.argv[1], "rb"))["packages"].items():
    r = p.get("recipe") or {}
    if "url" in r and "sha256" in r:
        print(f"{key}\t{r['url']}\t{r['sha256']}")
    if "key_url" in r:
        print(f"{key}\t{r['key_url']}\t{r['key_sha256']}")
    for f in r.get("files", []):
        print(f"{key}\t{f['url']}\t{f['sha256']}")
PY
if [ ! -s "$tmp/pins.tsv" ]; then echo "FAIL: no pins found in packages.toml"; exit 1; fi
while IFS=$'\t' read -r key url want; do
	if ! curl -fsSL --max-time 120 -o "$tmp/f" "$url"; then
		printf '  FAIL %s: cannot download %s\n' "$key" "$url"; fail=1; continue
	fi
	got=$(sha256sum "$tmp/f" | cut -d' ' -f1)
	if [ "$got" = "$want" ]; then printf '  ok   %s pin matches\n' "$key"
	else printf '  FAIL %s: sha256 changed (%s -> %s), the pin is stale: %s\n' "$key" "$want" "$got" "$url"; fail=1; fi
done < "$tmp/pins.tsv"
exit $fail
