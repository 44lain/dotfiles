"""Package data, distro detection, scan and plan. No UI; every side effect goes
through the injected `Env` so the tests can fake it."""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from typing import Callable

FAMILIES = ("fedora", "debian", "arch")
REPO_FAMILY = {"apt-repo": "debian", "dnf-copr": "fedora"}


def os_family(path: str | None = None) -> str:
    """Same rules as the copy in executable_rice-doctor: ID, then ID_LIKE."""
    path = path or os.environ.get("RICE_OS_RELEASE", "/etc/os-release")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return "unknown"
    kv = {}
    for line in text.splitlines():
        k, _, v = line.partition("=")
        kv[k] = v.strip().strip('"')
    for word in (kv.get("ID", "") + " " + kv.get("ID_LIKE", "")).split():
        if word in ("fedora", "rhel"):
            return "fedora"
        if word in ("debian", "ubuntu"):
            return "debian"
        if word == "arch":
            return "arch"
    return "unknown"


def _default_run(argv, **kw):
    try:
        return subprocess.run(argv, capture_output=True, text=True, **kw)
    except (FileNotFoundError, PermissionError):
        return subprocess.CompletedProcess(argv, 127, "", "command not found")


@dataclass
class Env:
    which: Callable = shutil.which
    run: Callable = _default_run
    exists: Callable = os.path.exists
    home: str = field(default_factory=lambda: os.path.expanduser("~"))
    machine: Callable = platform.machine


def default_env() -> Env:
    return Env()


@dataclass(frozen=True)
class Package:
    key: str
    desc: str
    section: str
    bin: str
    required: bool
    min_version: str
    names: dict
    notes: dict
    manual: str
    recipe: dict | None
    check: str


def load_packages(path) -> list[Package]:
    with open(path, "rb") as f:
        data = tomllib.load(f)["packages"]
    out = []
    for key, p in data.items():
        out.append(Package(
            key=key, desc=p.get("desc", ""), section=p.get("section", ""),
            bin=p.get("bin", ""), required=bool(p.get("required", False)),
            min_version=p.get("min_version", ""),
            names={f: p.get(f, "") for f in FAMILIES},
            notes={f: p.get("note_" + f, "") for f in FAMILIES},
            manual=p.get("manual", ""), recipe=p.get("recipe"), check=p.get("check", ""),
        ))
    return out


def vkey(version: str) -> tuple:
    """Comparable key from a version string: every integer in it, in order."""
    return tuple(int(x) for x in re.findall(r"\d+", version))


def installed_version(binary: str, env: Env) -> str:
    cp = env.run([binary, "--version"])
    m = re.search(r"\d+\.\d+(?:\.\d+)?", (cp.stdout or "") + (cp.stderr or ""))
    return m.group(0) if m else ""


def apt_lookup(pkg: str, env: Env):
    """(best_version, flag) from apt's local cache, or None if apt knows no
    version. flag is "-t <suite>" when the newest version is not the default
    candidate (backports). Read-only, no network, no root."""
    best = suite = None
    for line in env.run(["apt-cache", "madison", pkg]).stdout.splitlines():
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < 3 or not parts[1] or "dpkg/status" in parts[2]:
            continue
        fields = parts[2].split()
        s = fields[1].split("/")[0] if len(fields) > 1 else ""
        if best is None or (parts[1] != best and vkey(parts[1]) > vkey(best)):
            best, suite = parts[1], s
    if best is None:
        return None
    pol = env.run(["apt-cache", "policy", pkg]).stdout
    m = re.search(r"^\s*Candidate:\s*(\S+)", pol, re.M)
    flag = "" if (m and m.group(1) == best) else f"-t {suite}"
    return best, flag


@dataclass(frozen=True)
class Status:
    key: str
    desc: str
    required: bool
    state: str          # ok | missing | too_old | no_source
    source: str | None  # distro | recipe | None
    name: str = ""      # distro package name to install
    flag: str = ""      # "-t <suite>" for apt
    repo: bool = False  # a repository must be added first
    detail: str = ""    # apt_unknown | apt_too_old | no_package
    info: str = ""
    manual: str = ""
    recipe: dict | None = None


def _present(p: Package, env: Env):
    """True/False, or None for documentation-only items (no bin, no check)."""
    if p.bin:
        return env.which(p.bin) is not None
    kind, _, arg = p.check.partition(":")
    if kind == "font":
        return arg.lower() in (env.run(["fc-list"]).stdout or "").lower()
    if kind == "path":
        return env.exists(env.home + arg[1:] if arg.startswith("~") else arg)
    return None


def _applicable_recipe(p: Package, family: str, env: Env):
    r = p.recipe
    if not r:
        return None
    kind = r["kind"]
    if kind in REPO_FAMILY:
        return r if REPO_FAMILY[kind] == family else None
    if r.get("arch") and r["arch"] != env.machine():
        return None
    if p.names.get(family):
        return None  # the distro packages it; the recipe is only the fallback
    return r


def _resolve(p: Package, state: str, family: str, env: Env) -> Status:
    base = dict(key=p.key, desc=p.desc, required=p.required, manual=p.manual)
    r = _applicable_recipe(p, family, env)
    name = p.names.get(family, "")
    if r and r["kind"] in REPO_FAMILY:
        return Status(state=state, source="distro", name=r.get("package") or name,
                      repo=True, recipe=r, **base)
    if r:
        return Status(state=state, source="recipe", recipe=r, **base)
    if name:
        flag = ""
        if family == "debian":
            hit = apt_lookup(name, env)
            if hit is None:
                return Status(state="no_source", source=None, name=name, detail="apt_unknown", **base)
            best, flag = hit
            if p.min_version and vkey(best) < vkey(p.min_version):
                return Status(state="no_source", source=None, name=name,
                              detail="apt_too_old", info=best, **base)
        return Status(state=state, source="distro", name=name, flag=flag, **base)
    return Status(state="no_source", source=None, detail="no_package", **base)


def scan(packages: list[Package], family: str, env: Env) -> list[Status]:
    out = []
    for p in packages:
        present = _present(p, env)
        if present is None:
            continue
        old = False
        if present and p.min_version and p.bin:
            ver = installed_version(p.bin, env)
            old = bool(ver) and vkey(ver) < vkey(p.min_version)
        if present and not old:
            out.append(Status(key=p.key, desc=p.desc, required=p.required, state="ok",
                              source=None, manual=p.manual))
            continue
        out.append(_resolve(p, "too_old" if old else "missing", family, env))
    return out


def actionable(statuses: list[Status]) -> list[Status]:
    return [s for s in statuses if s.state in ("missing", "too_old") and s.source]
