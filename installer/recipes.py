"""Recipes: how the installer gets things the distro does not package.
Every download is pinned (url + sha256) and verified BEFORE anything is written."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from typing import Callable


class RecipeError(Exception):
    pass


class SudoExpired(RecipeError):
    pass


def _expand(path: str, home: str) -> str:
    return home + path[1:] if path.startswith("~") else path


def _fetch(url: str, dest: str) -> None:
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    except OSError as e:  # URLError, HTTPError and timeouts all derive from OSError
        raise RecipeError(f"download failed: {url}: {e}") from e


def stream_run(argv, on_line=None):
    """Run argv, feed each output line to on_line, return a CompletedProcess."""
    try:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1)
    except (FileNotFoundError, PermissionError):
        return subprocess.CompletedProcess(argv, 127, f"{argv[0]}: command not found", "")
    out = []
    for line in p.stdout:
        out.append(line)
        if on_line:
            on_line(line.rstrip("\n"))
    p.wait()
    return subprocess.CompletedProcess(argv, p.returncode, "".join(out), "")


@dataclass
class Ctx:
    home: str
    runner: Callable | None = None
    fetch: Callable = _fetch
    exists: Callable = os.path.exists
    sudo: list = field(default_factory=lambda: [] if os.geteuid() == 0 else ["sudo", "-n"])
    log: Callable = lambda line: None

    def run(self, argv):
        return (self.runner or stream_run)(argv, self.log)


def default_ctx(home: str, log_path: str) -> Ctx:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def log(line):
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    return Ctx(home=home, log=log)


def _tail(text: str, n: int = 8) -> str:
    return "\n".join((text or "").strip().splitlines()[-n:])


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify(path: str, expected: str, url: str) -> None:
    got = _sha256(path)
    if got != expected.lower():
        raise RecipeError(f"checksum mismatch for {url}: expected {expected}, got {got}. "
                          "The pinned version may be out of date.")


def _read_member(archive: str, member: str) -> bytes:
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                if m.isfile() and os.path.basename(m.name) == member:
                    return t.extractfile(m).read()
    elif zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                if os.path.basename(n) == member:
                    return z.read(n)
    raise RecipeError(f"{member!r} not found in the downloaded archive")


def _check(ctx: Ctx, argv: list) -> None:
    cp = ctx.run(argv)
    if cp.returncode != 0:
        out = cp.stdout or ""
        if "password is required" in out.lower():
            raise SudoExpired(out)
        raise RecipeError(_tail(out) or f"{' '.join(argv)} exited with {cp.returncode}")


def _release_binary(spec: dict, ctx: Ctx) -> None:
    dest = _expand(spec["dest"], ctx.home)
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "download")
        ctx.fetch(spec["url"], archive)
        _verify(archive, spec["sha256"], spec["url"])
        data = _read_member(archive, spec["member"])
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    staging = dest + ".rice-tmp"
    with open(staging, "wb") as f:
        f.write(data)
    os.chmod(staging, 0o755)
    os.replace(staging, dest)


def _fonts(spec: dict, ctx: Ctx) -> None:
    dest = _expand(spec.get("dest", "~/.local/share/fonts/dotfiles-required"), ctx.home)
    staged = []
    with tempfile.TemporaryDirectory() as tmp:  # verify EVERYTHING before writing anything
        for i, f in enumerate(spec["files"]):
            path = os.path.join(tmp, str(i))
            ctx.fetch(f["url"], path)
            _verify(path, f["sha256"], f["url"])
            if f.get("members"):
                for m in f["members"]:
                    staged.append((os.path.basename(m), _read_member(path, m)))
            else:
                with open(path, "rb") as fh:
                    staged.append((f["name"], fh.read()))
    os.makedirs(dest, exist_ok=True)
    for name, data in staged:
        with open(os.path.join(dest, name), "wb") as fh:
            fh.write(data)
    _check(ctx, ["fc-cache", "-f"])


def _git_clone(spec: dict, ctx: Ctx) -> None:
    dest = _expand(spec["dest"], ctx.home)
    if os.path.isdir(os.path.join(dest, ".git")):
        ctx.log(f"already present: {dest}")
        return
    if os.path.exists(dest):
        raise RecipeError(f"{dest} exists and is not a git checkout; move it away and retry")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    _check(ctx, ["git", "clone", "--branch", spec["branch"], spec["url"], dest])


KINDS = {"release-binary": _release_binary, "fonts": _fonts, "git-clone": _git_clone}


def run_recipe(spec: dict, ctx: Ctx) -> None:
    try:
        KINDS[spec["kind"]](spec, ctx)
    except KeyError as e:
        raise RecipeError(f"recipe is missing {e} or has an unknown kind") from e


def describe(spec: dict, home: str) -> list[str]:
    """Plain-text lines for the plan screen: exactly what this recipe will do."""
    kind = spec["kind"]
    if kind == "release-binary":
        return [f"download {spec['url']}",
                f"verify sha256 {spec['sha256'][:12]}…",
                f"install {spec['member']} -> {_expand(spec['dest'], home)}"]
    if kind == "fonts":
        dest = _expand(spec.get("dest", "~/.local/share/fonts/dotfiles-required"), home)
        lines = [f"download {f['url']} (sha256 {f['sha256'][:12]}…)" for f in spec["files"]]
        return lines + [f"copy the fonts to {dest}", "fc-cache -f"]
    if kind == "git-clone":
        return [f"git clone --branch {spec['branch']} {spec['url']} {_expand(spec['dest'], home)}"]
    if kind == "apt-repo":
        return [f"download the signing key {spec['key_url']} (sha256 {spec['key_sha256'][:12]}…)",
                f"install it as {spec['key_dest']}",
                f"write {spec['source_file']}: {spec['source']}",
                "apt-get update"]
    if kind == "dnf-copr":
        return [f"dnf copr enable -y {spec['name']}"]
    raise RecipeError(f"unknown recipe kind {kind!r}")
