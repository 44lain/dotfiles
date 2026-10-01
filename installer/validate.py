"""Validation with feedback BEFORE anything is written. Results carry a message
`code` (+ args) that the UI turns into text via messages/*, so they translate."""
from __future__ import annotations

import json
import os
import re
import stat
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
    if raw == "~":
        return home
    if raw.startswith("~/"):
        return home + raw[1:]
    return raw


def _images(path: str, max_entries: int = 20000, max_depth: int = None):
    entries_examined = 0
    for root, dirs, files in os.walk(path):
        # Limit depth if specified (max_depth=1 means allow depths 0, 1 but don't descend from 1)
        if max_depth is not None:
            depth = root[len(path):].count(os.sep)
            if depth >= max_depth:
                dirs.clear()  # Don't descend further

        entries_examined += len(dirs) + len(files)
        if entries_examined > max_entries:
            return
        for f in files:
            if os.path.splitext(f)[1].lower() in IMAGE_EXT:
                yield os.path.join(root, f)


def count_images(path: str, max_entries: int = 20000, max_depth: int = None) -> int:
    n = 0
    for _ in _images(path, max_entries=max_entries, max_depth=max_depth):
        n += 1
    return n


def first_image(raw: str, home: str) -> str:
    path = _expand(raw, home)
    if not os.path.isdir(path):
        return ""
    return min(_images(path, max_entries=20000), default="")


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
    pn = count_images(parent, max_entries=2000, max_depth=1) if parent and parent != path else 0
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
    real = os.path.realpath(path)
    data: dict = {}
    file_mode = None

    if os.path.exists(real):
        try:
            with open(real, encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError) as e:
            raise ShellJsonInvalid(f"{real}: {e}") from e
        if not isinstance(data, dict) or not isinstance(data.get("wallpaper", {}), dict):
            raise ShellJsonInvalid(f"{real}: unexpected structure")
        # Preserve existing file mode
        try:
            file_mode = stat.S_IMODE(os.stat(real).st_mode)
        except OSError:
            pass

    data.setdefault("wallpaper", {})["directory"] = directory
    os.makedirs(os.path.dirname(real), exist_ok=True)
    tmp = real + ".rice-tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        # Preserve file mode if it existed
        if file_mode is not None:
            os.chmod(tmp, file_mode)
        os.replace(tmp, real)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return path
