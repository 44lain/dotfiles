"""Validation with feedback BEFORE anything is written. Results carry a message
`code` (+ args) that the UI turns into text via messages/*, so they translate."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
HOST_RE = re.compile(r"^[A-Za-z0-9_-]+$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ShellJsonInvalid(Exception):
    pass


@dataclass
class Result:
    ok: bool
    value: str
    code: str
    args: dict = field(default_factory=dict)
    suggestion: str | None = None


def _expand(raw: str, home: str) -> str:
    raw = raw.strip()
    return home + raw[1:] if raw.startswith("~") else raw


def _images(path: str):
    for root, _dirs, files in os.walk(path):
        for f in files:
            if os.path.splitext(f)[1].lower() in IMAGE_EXT:
                yield os.path.join(root, f)


def count_images(path: str, cap: int = 100000) -> int:
    n = 0
    for _ in _images(path):
        n += 1
        if n >= cap:
            break
    return n


def first_image(raw: str, home: str) -> str:
    path = _expand(raw, home)
    if not os.path.isdir(path):
        return ""
    return min(_images(path), default="")


def check_wallpaper_dir(raw: str, home: str) -> Result:
    if not raw.strip():
        return Result(True, "", "wallpaper.skipped")
    path = _expand(raw, home)
    if not os.path.isabs(path):
        return Result(False, path, "wallpaper.relative", {"path": path})
    if not os.path.exists(path):
        return Result(False, path, "wallpaper.missing", {"path": path})
    if not os.path.isdir(path):
        return Result(False, path, "wallpaper.not_dir", {"path": path})
    path = path.rstrip("/") or "/"
    n = count_images(path)
    if n:
        return Result(True, path, "wallpaper.ok", {"count": n})
    parent = os.path.dirname(path)
    pn = count_images(parent) if parent and parent != path else 0
    if pn:
        return Result(False, path, "wallpaper.empty_parent", {"parent": parent, "count": pn}, suggestion=parent)
    return Result(False, path, "wallpaper.empty", {"path": path})


def check_wallpaper_image(raw: str, home: str) -> Result:
    if not raw.strip():
        return Result(True, "", "image.skipped")
    path = _expand(raw, home)
    if not os.path.isabs(path):
        return Result(False, path, "image.relative", {"path": path})
    if not os.path.exists(path):
        return Result(False, path, "image.missing", {"path": path})
    if os.path.isdir(path):
        return Result(False, path, "image.is_dir", {"path": path})
    if os.path.splitext(path)[1].lower() not in IMAGE_EXT:
        return Result(False, path, "image.not_image", {"path": path})
    return Result(True, path, "image.ok")


def check_name(raw: str) -> Result:
    v = raw.strip()
    return Result(bool(v), v, "ok" if v else "name.empty")


def check_email(raw: str) -> Result:
    v = raw.strip()
    return Result(bool(EMAIL_RE.match(v)), v, "ok" if EMAIL_RE.match(v) else "email.invalid")


def check_host_name(raw: str, known: list) -> Result:
    v = raw.strip()
    if not HOST_RE.match(v):
        return Result(False, v, "host.invalid")
    if v in known:
        return Result(False, v, "host.exists", {"name": v})
    return Result(True, v, "ok")


def write_shell_json(directory: str, home: str) -> str:
    """Set wallpaper.directory in ~/.config/grootshell/shell.json, keeping every
    other key. An existing file that is not valid JSON (or not the expected shape)
    is NEVER overwritten."""
    path = os.path.join(home, ".config", "grootshell", "shell.json")
    data: dict = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError) as e:
            raise ShellJsonInvalid(f"{path}: {e}") from e
        if not isinstance(data, dict) or not isinstance(data.get("wallpaper", {}), dict):
            raise ShellJsonInvalid(f"{path}: unexpected structure")
    data.setdefault("wallpaper", {})["directory"] = directory
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".rice-tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return path
