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
PACMAN_SYNC_DB = "/var/lib/pacman/sync/core.db"  # absent until the first `pacman -Sy(u)`


def os_family(path: str | None = None) -> str:
    """Same rules as the copy in executable_rice-doctor: ID, then ID_LIKE."""
    path = path or os.environ.get("RICE_OS_RELEASE", "/etc/os-release")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return "unknown"
    kv = {}
    for line in text.splitlines():
        k, _, v = line.partition("=")
        kv[k] = v.strip().strip('"')
    if kv.get("ID") == "artix":
        return "unknown"  # ID_LIKE=arch, but no systemd: the session cannot work
    for word in (kv.get("ID", "") + " " + kv.get("ID_LIKE", "")).split():
        if word in ("fedora", "rhel"):
            return "fedora"
        if word in ("debian", "ubuntu"):
            return "debian"
        if word == "arch":
            return "arch"
    return "unknown"


def c_locale() -> dict:
    """Environment for probes whose output is parsed: messages in English."""
    return {**os.environ, "LC_ALL": "C"}


def _default_run(argv, **kw):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=kw.pop("timeout", 30), **kw)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 127, "", "timeout")
    except OSError:
        return subprocess.CompletedProcess(argv, 127, "", "failed")


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
    for line in env.run(["apt-cache", "madison", pkg], env=c_locale()).stdout.splitlines():
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < 3 or not parts[1] or "dpkg/status" in parts[2]:
            continue
        fields = parts[2].split()
        s = fields[1].split("/")[0] if len(fields) > 1 else ""
        if best is None or (parts[1] != best and vkey(parts[1]) > vkey(best)):
            best, suite = parts[1], s
    if best is None:
        return None
    pol = env.run(["apt-cache", "policy", pkg], env=c_locale()).stdout
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


def _manual(p: Package, family: str) -> str:
    """The item's own manual text, or this family's note when it has none."""
    return p.manual or p.notes.get(family, "")


def _resolve(p: Package, state: str, family: str, env: Env) -> Status:
    base = dict(key=p.key, desc=p.desc, required=p.required, manual=_manual(p, family))
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
                              source=None, manual=_manual(p, family)))
            continue
        out.append(_resolve(p, "too_old" if old else "missing", family, env))
    return out


def actionable(statuses: list[Status]) -> list[Status]:
    return [s for s in statuses if s.state in ("missing", "too_old") and s.source]


@dataclass
class Step:
    id: str
    kind: str                 # repo | packages | recipe
    title_key: str
    title_args: dict
    commands: list            # argv lists WITHOUT sudo (the runner adds it when sudo=True)
    items: list               # package keys this step serves
    sudo: bool
    recipe: dict | None
    names: list
    flag: str
    sim_names: list           # names that can be simulated now (no repo needed first)


def _install_cmd(family: str, flag: str, names: list) -> list:
    f = flag.split() if flag else []
    if family == "fedora":
        return ["dnf", "install", "-y", *names]
    if family == "debian":
        return ["apt-get", "install", "-y", *f, *names]
    if family == "arch":
        # -Syu, always: a stale database 404s and -Sy alone is an unsupported partial upgrade
        return ["pacman", "-Syu", "--needed", "--noconfirm", *names]
    raise ValueError(f"no package manager for family {family!r}")


def build_plan(statuses: list[Status], selected, family: str) -> list[Step]:
    chosen = [s for s in statuses if s.key in selected and s.source]
    steps: list[Step] = []
    seen = set()
    for s in chosen:  # 1. repositories
        if s.repo and s.recipe:
            ident = (s.recipe["kind"], s.recipe.get("name") or s.recipe.get("source_file"))
            if ident in seen:
                continue
            seen.add(ident)
            steps.append(Step(id=f"repo:{ident[1]}", kind="repo", title_key="step.repo",
                              title_args={"name": ident[1]}, commands=[], items=[s.key],
                              sudo=True, recipe=s.recipe, names=[], flag="", sim_names=[]))
    groups: dict = {}
    for s in chosen:  # 2. distro packages, fewest commands: required first, one per suite flag;
        if s.source == "distro":  # names that need a repository get their own command
            groups.setdefault((not s.required, s.flag, s.repo), []).append(s)
    for (optional, flag, needs_repo), items in sorted(groups.items()):
        names = list(dict.fromkeys(i.name for i in items))
        steps.append(Step(
            id="pkgs:" + (flag or "default") + (":opt" if optional else "") + (":repo" if needs_repo else ""), kind="packages",
            title_key="step.packages",
            title_args={"n": len(names), "suite": f" ({flag})" if flag else ""},
            commands=[_install_cmd(family, flag, names)], items=[i.key for i in items], sudo=True,
            recipe=None, names=names, flag=flag,
            sim_names=[i.name for i in items if not i.repo]))
    for s in chosen:  # 3. standalone recipes
        if s.source == "recipe":
            steps.append(Step(id=f"recipe:{s.key}", kind="recipe", title_key="step.recipe",
                              title_args={"desc": s.desc}, commands=[], items=[s.key], sudo=False,
                              recipe=s.recipe, names=[], flag="", sim_names=[]))
    return steps


def _tail(text: str, n: int = 6) -> str:
    return "\n".join(text.strip().splitlines()[-n:])


def simulate(step: Step, family: str, env: Env):
    """('ok'|'fail'|'timeout'|'unsynced'|'skipped', output tail). Dry run of the distro package step."""
    if step.kind != "packages" or not step.sim_names:
        return ("skipped", "")
    f = step.flag.split() if step.flag else []
    if family == "debian":
        argv = ["apt-get", "-s", "install", *f, *step.sim_names]
    elif family == "fedora":
        argv = ["dnf", "install", "--assumeno", *step.sim_names]
    elif family == "arch":
        if not env.exists(PACMAN_SYNC_DB):
            return ("unsynced", "")  # -Sp would say "not found" for everything; the step syncs
        argv = ["pacman", "-Sp", *step.sim_names]
    else:
        return ("skipped", "")
    cp = env.run(argv, timeout=300, env=c_locale())  # dnf may download metadata first
    out = (cp.stdout or "") + (cp.stderr or "")
    if cp.returncode == 127 and (cp.stderr or "") == "timeout":
        return ("timeout", "")
    if cp.returncode == 0 or (family == "fedora" and "abort" in out.lower()):
        return ("ok", _tail(out))
    return ("fail", _tail(out))


def known_hosts(env: Env) -> list[str]:
    cp = env.run(["chezmoi", "data", "--format=json"])
    if cp.returncode != 0:
        return []
    try:
        return sorted((json.loads(cp.stdout).get("hosts") or {}).keys())
    except (ValueError, AttributeError):
        return []


def _local_config(env: Env) -> dict:
    path = os.path.join(env.home, ".config", "chezmoi", "chezmoi.toml")
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def local_hosts(env: Env) -> list[str]:
    """Hosts defined only in this machine's ~/.config/chezmoi/chezmoi.toml."""
    hosts = (_local_config(env).get("data") or {}).get("hosts")
    return sorted(hosts) if isinstance(hosts, dict) else []


def current_host(env: Env) -> str:
    host = (_local_config(env).get("data") or {}).get("host")
    return host if isinstance(host, str) else ""


def repo_hosts(repo) -> list[str]:
    """Hosts of the shared .chezmoidata/hosts.toml."""
    try:
        with open(os.path.join(str(repo), ".chezmoidata", "hosts.toml"), "rb") as f:
            return sorted(tomllib.load(f).get("hosts") or {})
    except (OSError, tomllib.TOMLDecodeError):
        return []


def detect_summary(env: Env) -> dict:
    kb = ""
    for line in (env.run(["localectl", "status"]).stdout or "").splitlines():
        if "X11 Layout:" in line:
            kb = line.split(":", 1)[1].strip()
    gpu = ""
    for line in (env.run(["lspci"]).stdout or "").splitlines():
        if re.search(r"vga|3d controller", line, re.I):
            gpu = line.split(": ", 1)[-1].strip()
            break
    return {"kb": kb, "gpu": gpu}
