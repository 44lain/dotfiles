#!/usr/bin/env bash
# packages.toml schema + cross-file consistency. Fast, no chezmoi/docker needed.
set -u

test_dir=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$test_dir/.." && pwd)
fail=0
pass()  { printf '  ok   %s\n' "$1"; }
flunk() { printf '  FAIL %s\n' "$1"; fail=1; }

# --- 1. schema ---------------------------------------------------------------
if out=$(python3 - "$repo/.chezmoidata/packages.toml" <<'PY' 2>&1
import sys, tomllib
sections = {"Compositor & session", "Bar / theming", "Terminal & tools",
            "Clipboard & screenshots", "Media / audio",
            "System tray / hardware", "Optional"}
data = tomllib.load(open(sys.argv[1], "rb"))["packages"]
errs = []
for key, p in data.items():
    if not isinstance(p.get("desc"), str) or not p["desc"]:
        errs.append(f"{key}: desc missing")
    if p.get("section") not in sections:
        errs.append(f"{key}: section {p.get('section')!r} not in the known list")
    for f in ("bin", "min_version", "manual"):
        if f in p and not isinstance(p[f], str):
            errs.append(f"{key}: {f} must be a string")
    if "required" in p and not isinstance(p["required"], bool):
        errs.append(f"{key}: required must be true/false")
    for fam in ("fedora", "debian", "arch"):
        if not p.get(fam) and not p.get("manual") and not p.get("note_" + fam):
            errs.append(f"{key}: no {fam} package, so it needs `manual` or `note_{fam}`")
    for k, v in p.items():
        if isinstance(v, str) and ("\x1f" in v or "\n" in v):
            errs.append(f"{key}.{k}: control character in value")
print("\n".join(errs))
sys.exit(1 if errs else 0)
PY
); then
	pass "packages.toml: schema valid"
else
	flunk "packages.toml schema: $out"
fi

exit $fail
