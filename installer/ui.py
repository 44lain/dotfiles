"""Terminal UI. Screens talk to the small UI protocol below; two implementations:
PlainUI (print/input, used without an interactive terminal) and CursesUI (Task 9).

>>> EDIT HERE to restyle: colours, frame characters and the minimum size. <<<"""
from __future__ import annotations

import os
import subprocess
import sys
import time
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

    def close(self, wait=True):
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
        """bool | BACK (b) | CANCEL (q or end of input)."""
        while True:
            a = self._read(f"{prompt} [{'Y/n' if default else 'y/N'}] ")
            if a is None or a.strip().lower() == "q":
                return CANCEL
            a = a.strip().lower()
            if a == "b":
                return BACK
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


class CursesUI:
    """Boxed frame, arrow-key navigation. Messages accumulate on the screen until
    the next title(); widgets draw below them."""

    def __init__(self, t):
        import curses
        import locale
        try:
            locale.setlocale(locale.LC_ALL, "")
        except locale.Error:
            pass
        os.environ.setdefault("ESCDELAY", "25")
        self.curses = curses
        self.t = t
        self._open = False
        self._eof = False
        self.scr = curses.initscr()
        self._open = True
        try:
            curses.noecho()
            curses.cbreak()
            self.scr.keypad(True)
            try:
                curses.curs_set(0)
            except curses.error:
                pass
            self.color = curses.has_colors() and "NO_COLOR" not in os.environ
            self.attrs = {}
            if self.color:
                curses.start_color()
                try:
                    curses.use_default_colors()
                    bg = -1
                except curses.error:
                    bg = curses.COLOR_BLACK
                for i, (name, col) in enumerate(PALETTE.items(), 1):
                    curses.init_pair(i, getattr(curses, "COLOR_" + col), bg)
                    self.attrs[name] = curses.color_pair(i)
            enc = (locale.getpreferredencoding(False) or "").upper().replace("-", "")
            utf8 = enc == "UTF8"
            self.f = FRAME_UTF8 if utf8 else FRAME_ASCII
            self.marks = ("✓", "!", "✗", "·", "↑", "↓") if utf8 else ("+", "!", "x", "-", "^", "v")
            self.step = (0, 0, "")
            self.lines = []  # (text, attr-name)
        except BaseException:
            self.close()  # a failed start must never leave the terminal broken
            raise

    # -- low level
    def _put(self, y, x, text, attr=0):
        try:
            self.scr.addstr(y, x, text, attr)
        except (self.curses.error, UnicodeError):
            pass  # too-small window or an unencodable character: never fatal

    def _attr(self, name):
        return self.attrs.get(name, 0) if name else 0

    def _fit(self, text, width):
        import textwrap
        out = []
        for para in str(text).split("\n"):
            out += textwrap.wrap(para, max(width, 1)) or [""]
        return out

    def _key(self):
        """Next key: an int for special/control keys (10 = Enter, 27 = ESC, curses
        KEY_* codes) or a one-character str for printable input, so multi-byte
        characters such as 'ã' arrive whole. KEY_RESIZE is returned as is;
        callers redraw on any key they do not handle."""
        failures = 0
        while True:
            try:
                k = self.scr.get_wch()
            except self.curses.error:
                failures += 1
                if failures > 20:  # input is gone (closed tty): behave like ESC
                    self._eof = True
                    return 27
                time.sleep(0.02)
                continue
            if isinstance(k, str):
                o = ord(k)
                return o if o < 32 or o == 127 else k
            return k

    def _sync_size(self):
        """Without reading keys curses never learns about a resize; ask the tty."""
        try:
            size = os.get_terminal_size(1)
            if self.curses.is_term_resized(size.lines, size.columns):
                self.curses.resizeterm(size.lines, size.columns)
        except (OSError, ValueError, AttributeError, self.curses.error):
            pass

    def _draw(self, body, hint, block=True, focus=None, pinned=0, scroll=None):
        """body: list of (text, attr-name, bold?). On a too-small window shows the
        resize notice; with block=True it then waits for a key or resize, with
        block=False it returns at once (for progress, which must never stall).
        Overflowing bodies show their tail, unless the first `pinned` entries are
        to stay put and the rest scrolls: `focus` (body index) keeps that entry
        visible, `scroll` is an explicit first visible row. Returns (first
        visible row of the scrollable part, its page size)."""
        c = self.curses
        while True:
            if not block:
                self._sync_size()
            h, w = self.scr.getmaxyx()
            if (h >= MIN_H and w >= MIN_W) or self._eof:
                break
            self.scr.erase()
            self._put(0, 0, self.t("ui.too_small", w=MIN_W, h=MIN_H)[: max(w - 1, 0)])
            try:
                self.scr.refresh()
            except c.error:
                pass
            if not block:
                return (0, 0)
            self._key()  # any key (or KEY_RESIZE) re-checks the size
        self.scr.erase()
        f = self.f
        step, total, text = self.step
        title = self.t("app.title")
        dot = self.marks[3]
        head = f" {title} {dot} {step}/{total} {dot} {text} " if total else f" {title} "
        self._put(0, 0, f["tl"] + f["h"] * (w - 2))
        self._put(0, 0, f["tl"] + f["h"] + head, self._attr("accent") | c.A_BOLD)
        self._put(0, w - 1, f["tr"])
        for y in range(1, h - 1):
            self._put(y, 0, f["v"])
            self._put(y, w - 1, f["v"])
        self._put(h - 1, 0, f["bl"] + f["h"] * (w - 2))
        self._put(h - 1, w - 1, f["br"])
        rows = []
        for n, (text, name, bold) in enumerate(body):
            for part in self._fit(text, w - 6):
                rows.append((part, name, bold, n))
        room = max(h - 4, 1)
        start, page = 0, room
        if focus is None and scroll is None:
            shown = rows[-room:]
        else:
            head = [r for r in rows if r[3] < pinned][-max(room - 3, 1):]
            rest = [r for r in rows if r[3] >= pinned]
            page = max(room - len(head), 1)
            window = rest[:page]
            if len(rest) > page:
                last = len(rest) - page
                if scroll is not None:
                    start = min(max(scroll, 0), last)
                else:
                    f = next((i for i, r in enumerate(rest) if r[3] == focus), 0)
                    start = min(max(f - page // 2, 0), last)
                window = rest[start:start + page]
                if start > 0:
                    window[0] = (self.marks[4] + " ...", "dim", False, -1)
                if start + page < len(rest):
                    window[-1] = (self.marks[5] + " ...", "dim", False, -1)
            shown = head + window
        for i, (part, name, bold, _n) in enumerate(shown):
            self._put(1 + i, 2, part, self._attr(name) | (c.A_BOLD if bold else 0))
        self._put(h - 2, 2, hint[: max(w - 4, 0)], self._attr("dim"))
        try:
            self.scr.refresh()
        except c.error:
            pass
        return (start, page)

    _seen = 0  # how many of self.lines have been drawn at least once

    def _msgs(self):
        self._seen = len(self.lines)
        return [(t, n, False) for t, n in self.lines]

    def _unseen(self):
        return list(getattr(self, "lines", [])[self._seen:])

    def _flush(self):
        """Messages added since the last draw would vanish with the next screen
        (or the exit): draw them and wait for a key first."""
        if self._unseen() and not self._eof:
            self._draw(self._msgs(), self.t("hint.table"))
            try:
                self._key()
            except KeyboardInterrupt:
                pass  # Ctrl-C must never trap the user inside this wait

    # -- output
    def title(self, step, total, text):
        self._flush()
        self.step = (step, total, text)
        self.lines = []
        self._seen = 0

    def info(self, text):
        self.lines.append((text, None))

    def success(self, text):
        self.lines.append((self.marks[0] + " " + text, "ok"))

    def warn(self, text):
        self.lines.append((self.marks[1] + " " + text, "warn"))

    def error(self, text):
        self.lines.append((self.marks[2] + " " + text, "err"))

    def table(self, header, rows):
        widths = [max(len(str(x)) for x in col) for col in zip(header, *rows)] if rows else [len(h) for h in header]
        fmt = lambda r: "  ".join(str(c).ljust(wd) for c, wd in zip(r, widths))
        body = self._msgs() + [(fmt(header), "accent", True)] + [(fmt(r), None, False) for r in rows]
        c = self.curses
        pinned = len(self._msgs()) + 1  # messages and the header stay put
        top, page = 0, 1
        while True:
            top, page = self._draw(body, self.t("hint.table"), pinned=pinned, scroll=top)
            k = self._key()
            if k in (c.KEY_UP, "k"):
                top -= 1
            elif k in (c.KEY_DOWN, "j"):
                top += 1
            elif k == c.KEY_PPAGE:
                top -= max(page - 1, 1)
            elif k == c.KEY_NPAGE:
                top += max(page - 1, 1)
            elif k == c.KEY_HOME:
                top = 0
            elif k == c.KEY_END:
                top = 10 ** 9
            elif k in (10, 13, c.KEY_ENTER, c.KEY_RIGHT):
                return "next"
            if k == c.KEY_LEFT:
                return BACK
            if k == 27:
                return CANCEL

    @contextmanager
    def progress(self, label):
        from collections import deque
        buf = deque(maxlen=10)
        tick = [0]

        def push(line=""):
            if line:
                buf.append(line)
            tick[0] += 1
            body = self._msgs() + [(f"{SPINNER[tick[0] % 4]} {label}", "accent", True)]
            body += [("   " + ln, "dim", False) for ln in buf]
            self._draw(body, self.t("hint.wait"), block=False)

        push()
        yield push

    def suspend(self, argv):
        """Run an interactive command outside curses; always restores the screen."""
        c = self.curses
        c.def_prog_mode()
        c.endwin()
        try:
            try:
                rc = subprocess.call(argv)
            except (FileNotFoundError, PermissionError):
                rc = 127
            try:
                input("\n" + self.t("ui.press_enter"))
            except EOFError:
                pass
            return rc
        finally:
            try:
                c.reset_prog_mode()
                self.scr.clear()
                self.scr.refresh()
            except c.error:
                pass

    def close(self, wait=True):
        """Idempotent: restores the terminal once, later calls do nothing.
        wait=False (the Ctrl-C path) skips the "press a key" pause; the pending
        messages are still printed to the scrollback."""
        if not self._open:
            return
        pending = self._unseen()
        try:
            if wait:
                self._flush()
        finally:
            self._open = False
            try:
                self.curses.endwin()
            except self.curses.error:
                pass
        for text, _name in pending:  # keep the last words in the scrollback
            try:
                print(text, flush=True)
            except OSError:
                break

    # -- input
    def menu(self, prompt, options, default=0):
        c = self.curses
        if not options:
            return CANCEL
        idx = min(max(default, 0), len(options) - 1)
        while True:
            body = self._msgs() + [(prompt, None, True)]
            pinned = len(body)
            for i, (_k, label) in enumerate(options):
                body.append((("> " if i == idx else "  ") + label, "accent" if i == idx else None, i == idx))
            self._draw(body, self.t("hint.menu"), focus=pinned + idx, pinned=pinned)
            k = self._key()
            if k in (c.KEY_UP, "k"):
                idx = (idx - 1) % len(options)
            elif k in (c.KEY_DOWN, "j"):
                idx = (idx + 1) % len(options)
            elif k in (10, 13, " ", c.KEY_ENTER, c.KEY_RIGHT):
                return options[idx][0]
            elif k == c.KEY_LEFT:
                return BACK
            elif k == 27:
                return CANCEL

    def checklist(self, prompt, items):
        c = self.curses
        if not items:
            return []
        state = {i.key: i.checked for i in items}
        idx = 0
        while True:
            body = self._msgs() + [(prompt, None, True)]
            pinned = len(body)
            for n, i in enumerate(items):
                mark = "[x]" if state[i.key] else "[ ]"
                body.append((f"{'>' if n == idx else ' '} {mark} {i.label}", "accent" if n == idx else None, n == idx))
            self._draw(body, self.t("hint.checklist"), focus=pinned + idx, pinned=pinned)
            k = self._key()
            if k in (c.KEY_UP, "k"):
                idx = (idx - 1) % len(items)
            elif k in (c.KEY_DOWN, "j"):
                idx = (idx + 1) % len(items)
            elif k == " ":
                state[items[idx].key] = not state[items[idx].key]
            elif k == "a":
                every = all(state.values())
                state = {key: not every for key in state}
            elif k in (10, 13, c.KEY_ENTER):
                return [i.key for i in items if state[i.key]]
            elif k == c.KEY_LEFT:
                return BACK
            elif k == 27:
                return CANCEL

    def text(self, prompt, default="", validate=None):
        c = self.curses
        value = default
        while True:
            ok, msg = (True, "")
            if validate:
                ok, msg = validate(value)
            body = self._msgs() + [(prompt, None, True), ("> " + value + "_", "accent", False)]
            if msg:
                body.append(((self.marks[0] if ok else self.marks[2]) + " " + msg, "ok" if ok else "err", False))
            self._draw(body, self.t("hint.text"))
            k = self._key()
            if k in (10, 13, c.KEY_ENTER):
                if ok:
                    return value
            elif k in (c.KEY_BACKSPACE, 127, 8):
                value = value[:-1]
            elif k == c.KEY_LEFT and value == "":
                return BACK
            elif k == 27:
                return CANCEL
            elif isinstance(k, str):
                value += k  # KEY_RESIZE and other key codes are ints: ignored, redraw

    def confirm(self, prompt, default=False):
        """bool | BACK (LEFT) | CANCEL (ESC)."""
        r = self.menu(prompt, [("y", self.t("ui.yes")), ("n", self.t("ui.no"))], default=0 if default else 1)
        if r is BACK or r is CANCEL:
            return r
        return r == "y"
