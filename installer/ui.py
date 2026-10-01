"""Terminal UI. Screens talk to the small UI protocol below; two implementations:
PlainUI (print/input, used without an interactive terminal) and CursesUI (Task 9).

>>> EDIT HERE to restyle: colours, frame characters and the minimum size. <<<"""
from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass

# ---- constants block -------------------------------------------------------
MIN_H, MIN_W = 24, 80
FRAME_UTF8 = dict(tl="┌", tr="┐", bl="└", br="┘", h="─", v="│")
FRAME_ASCII = dict(tl="+", tr="+", bl="+", br="+", h="-", v="|")
# name -> curses colour name (RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE)
PALETTE = {"ok": "GREEN", "warn": "YELLOW", "err": "RED", "accent": "CYAN", "dim": "WHITE"}
SPINNER = "|/-\\"
# ----------------------------------------------------------------------------


class _Sentinel:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


BACK = _Sentinel("BACK")
CANCEL = _Sentinel("CANCEL")


@dataclass
class Item:
    key: str
    label: str
    checked: bool = False


class PlainUI:
    """print/input implementation. Same questions as the curses screens."""

    def __init__(self, t, stdin=None, stdout=None):
        self.t = t
        self.inp = stdin or sys.stdin
        self.out = stdout or sys.stdout

    # -- plumbing
    def _say(self, text=""):
        print(text, file=self.out, flush=True)

    def _read(self, prompt):
        print(prompt, end="", file=self.out, flush=True)
        line = self.inp.readline()
        return None if line == "" else line.rstrip("\n")

    # -- output
    def title(self, step, total, text):
        self._say(f"\n== {self.t('app.title')} · {step}/{total} · {text} ==")

    def info(self, text):
        self._say(text)

    def success(self, text):
        self._say(f"  ok   {text}")

    def warn(self, text):
        self._say(f"  WARN {text}")

    def error(self, text):
        self._say(f"  FAIL {text}")

    def table(self, header, rows):
        self._say("  " + " | ".join(header))
        for r in rows:
            self._say("  " + " | ".join(str(c) for c in r))
        return "next"

    @contextmanager
    def progress(self, label):
        self._say(f"  … {label}")

        def push(line=""):
            if line:
                self._say(f"      {line}")

        yield push

    def suspend(self, argv):
        try:
            return subprocess.call(argv)
        except (FileNotFoundError, PermissionError):
            return 127

    def close(self):
        pass

    # -- input
    def menu(self, prompt, options, default=0):
        self._say(prompt)
        for i, (_k, label) in enumerate(options, 1):
            self._say(f"  {i}) {label}{'  [default]' if i - 1 == default else ''}")
        self._say("  " + self.t("plain.hint"))
        while True:
            a = self._read("> ")
            if a is None or a.strip().lower() == "q":
                return CANCEL
            a = a.strip().lower()
            if a == "b":
                return BACK
            if a == "":
                return options[default][0]
            if a.isdigit() and 1 <= int(a) <= len(options):
                return options[int(a) - 1][0]
            self._say(f"  1-{len(options)}")

    def checklist(self, prompt, items):
        state = {i.key: i.checked for i in items}
        while True:
            self._say(prompt)
            for n, i in enumerate(items, 1):
                self._say(f"  {n}) [{'x' if state[i.key] else ' '}] {i.label}")
            self._say("  numbers toggle · a = all · n = none · ENTER = confirm")
            self._say("  " + self.t("plain.hint"))
            a = self._read("> ")
            if a is None or a.strip().lower() == "q":
                return CANCEL
            a = a.strip().lower()
            if a == "b":
                return BACK
            if a == "":
                return [i.key for i in items if state[i.key]]
            if a == "a":
                state = {k: True for k in state}
            elif a == "n":
                state = {k: False for k in state}
            else:
                for tok in a.replace(",", " ").split():
                    if tok.isdigit() and 1 <= int(tok) <= len(items):
                        k = items[int(tok) - 1].key
                        state[k] = not state[k]

    def text(self, prompt, default="", validate=None):
        while True:
            a = self._read(f"{prompt}{f' [{default}]' if default else ''}: ")
            if a is None or a.strip() == "/quit":
                return CANCEL
            if a.strip() == "/back":
                return BACK
            value = a if a != "" else default
            if validate:
                ok, msg = validate(value)
                if msg:
                    self._say(f"  {'ok' if ok else 'FAIL'}   {msg}")
                if not ok:
                    continue
            return value

    def confirm(self, prompt, default=False):
        while True:
            a = self._read(f"{prompt} [{'Y/n' if default else 'y/N'}] ")
            if a is None or a.strip().lower() == "q":
                return CANCEL
            a = a.strip().lower()
            if a == "":
                return default
            if a in ("y", "yes", "s", "sim"):
                return True
            if a in ("n", "no", "nao", "não"):
                return False


def make_ui(t, plain=False, term=None, stdin=None, stdout=None):
    """CursesUI on an interactive terminal, PlainUI otherwise."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    term = os.environ.get("TERM", "") if term is None else term
    interactive = stdin.isatty() and stdout.isatty() and term not in ("", "dumb")
    if plain or not interactive:
        return PlainUI(t, stdin, stdout)
    try:
        return CursesUI(t)
    except Exception:  # curses can fail in odd terminals; the same questions still work
        return PlainUI(t, stdin, stdout)


class CursesUI:  # replaced by the real implementation in Task 9
    def __init__(self, t):
        raise NotImplementedError
