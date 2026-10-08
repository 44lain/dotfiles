#!/usr/bin/env python3
"""Pseudo-terminal driver for test/distro/installer-e2e.sh (standard library only).

Runs a command (the real CursesUI installer, or install.sh) in a 30x100 xterm pty,
feeds it real key presses and asserts on the RENDERED screen. A small VT100
emulator is built in, because curses only redraws what changed: matching the raw
byte stream would miss text, the emulator gives the screen a human would see.

  e2e_driver.py SCENARIO --cmd 'shell command' [--pkg fzf] [--log FILE]

Scenarios
  walk    welcome .. verify with the real keys (one package selected), incl. a back step
  cancel  walk until the plan confirmation, press ESC, expect the documented cancel (exit 1)
  ctrlc   walk until the scan table, press Ctrl-C, expect exit 130 and a restored terminal
  --prelude  first answer install.sh's own [y/N] prompt (shows what a stranger sees)

Prints a human-readable transcript (a snapshot of the screen at every step) and
`E2E-CHECK ok|FAIL <name>` lines; exit status 0 only if no check failed.
"""
import argparse
import codecs
import fcntl
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import time

ROWS, COLS = 30, 100

ENTER, ESC, BACKSPACE, CTRL_C = b"\r", b"\x1b", b"\x7f", b"\x03"
UP, DOWN, RIGHT, LEFT = b"\x1bOA", b"\x1bOB", b"\x1bOC", b"\x1bOD"  # xterm terminfo, keypad mode
PGDN = b"\x1b[6~"


class Term:
    """Just enough of a VT100/xterm for what ncurses emits for TERM=xterm."""

    def __init__(self, rows=ROWS, cols=COLS):
        self.rows, self.cols = rows, cols
        self.main = self._blank()
        self.alt = self._blank()
        self.use_alt = False
        self.r = self.c = 0
        self.wrap = False
        self.top, self.bot = 0, rows - 1
        self.saved = (0, 0)
        self.scrollback = []
        self.mainlog = ""          # every character written to the main screen, in order
        self.state = "g"
        self.buf = ""
        self.last = " "
        self.dec = codecs.getincrementaldecoder("utf-8")("replace")
        self.headers = {}          # step number -> title seen on the frame's top row

    def _blank(self):
        return [[" "] * self.cols for _ in range(self.rows)]

    @property
    def g(self):
        return self.alt if self.use_alt else self.main

    def lines(self):
        return ["".join(row).rstrip() for row in self.g]

    def text(self):
        return "\n".join(self.lines())

    # -- scrolling
    def _scroll_up(self, n=1):
        g = self.g
        for _ in range(n):
            gone = g.pop(self.top)
            if not self.use_alt and self.top == 0 and self.bot == self.rows - 1:
                self.scrollback.append("".join(gone).rstrip())
            g.insert(self.bot, [" "] * self.cols)

    def _scroll_down(self, n=1):
        g = self.g
        for _ in range(n):
            g.pop(self.bot)
            g.insert(self.top, [" "] * self.cols)

    def _lf(self):
        if self.r == self.bot:
            self._scroll_up()
        elif self.r < self.rows - 1:
            self.r += 1

    def _put(self, ch):
        if self.wrap:
            self.c = 0
            self._lf()
            self.wrap = False
        self.g[self.r][self.c] = ch
        self.last = ch
        if not self.use_alt:
            self.mainlog += ch
        if self.c == self.cols - 1:
            self.wrap = True
        else:
            self.c += 1

    # -- input
    def feed(self, data):
        for ch in self.dec.decode(data):
            self._char(ch)
        row0 = "".join(self.alt[0])
        m = re.search(r"rice setup · (\d)/8 · ([^─┐]*)", row0)
        if m:
            self.headers[int(m.group(1))] = m.group(2).strip()

    def _char(self, ch):
        s = self.state
        if s == "g":
            if ch == "\x1b":
                self.state = "e"
            elif ch == "\n":
                self.wrap = False
                if not self.use_alt:
                    self.mainlog += "\n"
                self._lf()
            elif ch == "\r":
                self.c = 0
                self.wrap = False
            elif ch == "\b":
                self.c = max(0, self.c - 1)
                self.wrap = False
            elif ch == "\t":
                self.c = min(self.cols - 1, (self.c // 8 + 1) * 8)
            elif ch >= " " and ch != "\x7f":
                self._put(ch)
        elif s == "e":
            self.state = "g"
            if ch == "[":
                self.state, self.buf = "c", ""
            elif ch in "]P^_X":
                self.state = "o"
            elif ch in "()*+#%":
                self.state = "x"
            elif ch == "7":
                self.saved = (self.r, self.c)
            elif ch == "8":
                self.r, self.c = self.saved
            elif ch == "M":
                if self.r == self.top:
                    self._scroll_down()
                else:
                    self.r = max(0, self.r - 1)
            elif ch == "D":
                self._lf()
            elif ch == "E":
                self.c = 0
                self._lf()
            elif ch == "c":
                self.__init__(self.rows, self.cols)
        elif s == "x":
            self.state = "g"
        elif s == "o":
            if ch == "\x07":
                self.state = "g"
            elif ch == "\x1b":
                self.state = "x"  # ST = ESC \ : swallow the backslash
        elif s == "c":
            if "\x40" <= ch <= "\x7e":
                self.state = "g"
                self._csi(self.buf, ch)
            else:
                self.buf += ch

    def _csi(self, buf, f):
        priv = buf[:1] in ("?", ">", "=", "!")
        nums = [int(x) if x.isdigit() else 0 for x in re.split(r"[;:]", buf.lstrip("?>=!"))] if buf.lstrip("?>=!") else []
        n = lambda i, d=1: (nums[i] if len(nums) > i and nums[i] else d)
        self.wrap = False if f not in "m" else self.wrap
        g = self.g
        if priv:
            if f in "hl" and any(p in (1049, 47, 1047) for p in nums):
                if f == "h":
                    self.saved = (self.r, self.c)
                    self.use_alt = True
                    self.alt = self._blank()
                else:
                    self.use_alt = False
                    self.r, self.c = self.saved
            return
        if f == "A":
            self.r = max(self.top if self.r >= self.top else 0, self.r - n(0))
        elif f == "B":
            self.r = min(self.bot if self.r <= self.bot else self.rows - 1, self.r + n(0))
        elif f == "C":
            self.c = min(self.cols - 1, self.c + n(0))
        elif f == "D":
            self.c = max(0, self.c - n(0))
        elif f in "Hf":
            self.r, self.c = min(n(0) - 1, self.rows - 1), min(n(1) - 1, self.cols - 1)
        elif f == "G":
            self.c = min(n(0) - 1, self.cols - 1)
        elif f == "d":
            self.r = min(n(0) - 1, self.rows - 1)
        elif f == "J":
            m = nums[0] if nums else 0
            if m == 0:
                g[self.r][self.c:] = [" "] * (self.cols - self.c)
                for i in range(self.r + 1, self.rows):
                    g[i] = [" "] * self.cols
            elif m == 1:
                g[self.r][: self.c + 1] = [" "] * (self.c + 1)
                for i in range(self.r):
                    g[i] = [" "] * self.cols
            else:
                for i in range(self.rows):
                    g[i] = [" "] * self.cols
        elif f == "K":
            m = nums[0] if nums else 0
            if m == 0:
                g[self.r][self.c:] = [" "] * (self.cols - self.c)
            elif m == 1:
                g[self.r][: self.c + 1] = [" "] * (self.c + 1)
            else:
                g[self.r] = [" "] * self.cols
        elif f == "X":
            k = min(n(0), self.cols - self.c)
            g[self.r][self.c:self.c + k] = [" "] * k
        elif f == "P":
            k = min(n(0), self.cols - self.c)
            del g[self.r][self.c:self.c + k]
            g[self.r].extend([" "] * k)
        elif f == "@":
            k = min(n(0), self.cols - self.c)
            g[self.r][self.c:] = ([" "] * k + g[self.r][self.c:])[: self.cols - self.c]
        elif f == "L":
            for _ in range(n(0)):
                g.pop(self.bot)
                g.insert(self.r, [" "] * self.cols)
        elif f == "M":
            for _ in range(n(0)):
                g.pop(self.r)
                g.insert(self.bot, [" "] * self.cols)
        elif f == "S":
            self._scroll_up(n(0))
        elif f == "T":
            self._scroll_down(n(0))
        elif f == "b":
            for _ in range(n(0)):
                self._put(self.last)
        elif f == "r":
            self.top, self.bot = n(0) - 1, (nums[1] - 1 if len(nums) > 1 and nums[1] else self.rows - 1)
            self.r = self.c = 0
        elif f == "s":
            self.saved = (self.r, self.c)
        elif f == "u":
            self.r, self.c = self.saved
        # m (colours), t (window ops), h/l (modes), n, ... : irrelevant


class Fail(Exception):
    pass


class Session:
    def __init__(self, cmd, env, logfile):
        self.term = Term()
        self.checks = []
        self.raw = bytearray()
        self.mainpos = 0
        self.exit = None
        self.log = open(logfile, "w", encoding="utf-8") if logfile else None
        pid, fd = pty.fork()
        if pid == 0:
            os.execvpe("/bin/sh", ["sh", "-c", cmd], env)
        self.pid, self.fd = pid, fd
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
        os.kill(pid, signal.SIGWINCH)

    # -- reporting
    def say(self, msg=""):
        print(msg, flush=True)
        if self.log:
            self.log.write(msg + "\n")

    def check(self, name, ok, detail=""):
        self.checks.append((name, bool(ok)))
        self.say(f"E2E-CHECK {'ok' if ok else 'FAIL'} {name}" + (f"  ({detail})" if detail and not ok else ""))
        return ok

    def snapshot(self, label):
        self.say(f"--- screen after: {label} " + "-" * max(0, 60 - len(label)))
        for ln in self.term.lines():
            if ln.strip():
                self.say("  | " + ln)

    # -- io
    def pump(self, timeout=0.2):
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return False
        try:
            data = os.read(self.fd, 65536)
        except OSError:
            data = b""
        if not data:
            self._reap()
            time.sleep(0.05)  # EOF: never spin while the child is being reaped
            return False
        self.raw += data
        self.term.feed(data)
        return True

    def _reap(self):
        if self.exit is None:
            try:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:
                self.exit = -1
                return
            if pid:
                self.exit = os.waitstatus_to_exitcode(status)

    def wait_for(self, pattern, timeout=60, main=False, what=None):
        """Wait until pattern (regex) is on the visible screen, or (main=True) in the
        main-screen output written since the previous main wait."""
        rx = re.compile(pattern, re.S)
        end = time.time() + timeout
        while True:
            if main:
                m = rx.search(self.term.mainlog, self.mainpos)
                if m:
                    self.mainpos = m.end()
                    return m
            elif rx.search(self.term.text()):
                return True
            if time.time() > end:
                self.snapshot(f"TIMEOUT waiting for {what or pattern}")
                raise Fail(f"timeout waiting for {what or pattern!r}")
            if not self.pump(0.1):
                self._reap()
                if self.exit is not None and not select.select([self.fd], [], [], 0)[0]:
                    # drain what is left, then give up
                    if (rx.search(self.term.mainlog, self.mainpos) if main else rx.search(self.term.text())):
                        continue
                    self.snapshot(f"process exited ({self.exit}) while waiting for {what or pattern}")
                    raise Fail(f"process exited with {self.exit} while waiting for {what or pattern!r}")

    def send(self, keys, delay=0.05):
        if isinstance(keys, str):
            keys = keys.encode()
        os.write(self.fd, keys)
        time.sleep(delay)
        while self.pump(0.05):
            pass

    def type(self, text):
        for ch in text:
            self.send(ch, 0.01)

    def step(self, label, pattern, keys=None, timeout=60, snap=True):
        """Wait for a screen, record it, then press keys."""
        self.wait_for(pattern, timeout, what=label)
        while self.pump(0.15):  # let the frame finish drawing
            pass
        if snap:
            self.snapshot(label)
        if keys is not None:
            self.send(keys)

    def finish(self, timeout=60):
        end = time.time() + timeout
        while self.exit is None and time.time() < end:
            self.pump(0.1)
            self._reap()
        while self.pump(0.2):
            pass
        if self.exit is None:
            os.kill(self.pid, signal.SIGKILL)
            self.exit = "hung"
        try:
            self.tio = termios.tcgetattr(self.fd)
        except termios.error:
            self.tio = None
        return self.exit

    def kill(self):
        if self.exit is None:
            try:
                os.kill(self.pid, signal.SIGKILL)
                os.waitpid(self.pid, 0)
            except (OSError, ChildProcessError):
                pass


def alltext(s):
    ansi = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[()][A-Za-z0-9]|\x1b[=>78]")
    return ansi.sub("", s.raw.decode("utf-8", "replace"))


def final_checks(s, name, expect_exit):
    code = s.finish()
    s.check(f"{name}: exit code is {expect_exit}", code == expect_exit, f"got {code}")
    s.check(f"{name}: no Python traceback anywhere in the output", "Traceback (most recent call last)" not in alltext(s))
    t = s.tio
    if t is not None:
        lflag = t[3]
        s.check(f"{name}: terminal restored (echo and line mode back on)",
                bool(lflag & termios.ECHO) and bool(lflag & termios.ICANON))
    s.check(f"{name}: screen left the alternate buffer (curses ended)", not s.term.use_alt)


# ---------------------------------------------------------------------------
def select_only(s, pkgs):
    """Checklist: clear every pre-selected item, then tick only pkgs."""
    s.send("a")
    s.send("a")  # first 'a' = all, second = none (required items start ticked, so not "all")
    for pkg in pkgs:
        tick(s, pkg)


def tick(s, pkg):
    for _ in range(200):
        rows = [ln.replace("│", " ").strip() for ln in s.term.lines()]
        if any(re.match(rf">\s+\[.\]\s+{re.escape(pkg)}\s+—", r) for r in rows):
            break
        s.send(DOWN, 0.02)
    else:
        raise Fail(f"{pkg} is not in the checklist")
    s.send(" ")
    s.wait_for(rf">\s+\[x\]\s+{re.escape(pkg)}\s+—", 5, what=f"{pkg} ticked")
    s.snapshot(f"{pkg} ticked")


def _rows(s):
    out = set()
    for ln in s.term.lines():
        ln = ln.replace("│", " ").strip()
        if ln and not ln.startswith(("↑", "↓", "┌", "└")):
            out.add(re.sub(r"\s+", " ", ln))
    return out


def page_rows(s, key, limit=60):
    """All rows seen scrolling a table from its top with `key` (PGDN pages, DOWN lines)."""
    for _ in range(80):
        s.send(UP, 0.005)
    seen, last = set(), None
    for _ in range(limit * (1 if key == PGDN else 8)):
        seen |= _rows(s)
        cur = s.term.text()
        if cur == last:
            break
        last = cur
        s.send(key, 0.01)
    return seen


def scroll_table(s, pattern, label, limit=40):
    """Scroll with PgDn, then line by line, until pattern shows; True if it did."""
    pg = page_rows(s, PGDN)
    if any(re.search(pattern, r) for r in pg):
        return True
    ln = page_rows(s, DOWN)
    s.say(f"NOTE {label}: PgDn paging showed {len(pg)} distinct rows, line-by-line scrolling showed {len(ln)}")
    missed = sorted(ln - pg)
    if missed:
        s.say("NOTE rows never visible with PgDn paging (only with arrows): " + " || ".join(m[:60] for m in missed[:6]))
    s.pgdn_missed = getattr(s, "pgdn_missed", []) + missed
    for _ in range(80):
        s.send(UP, 0.005)
    for _ in range(300):
        if any(re.search(pattern, r) for r in _rows(s)):
            return True
        s.send(DOWN, 0.01)
    return False


def walk(s, a, until=None):
    pkg, host = a.pkg, a.host
    if a.prelude:
        oneliner_prelude(s, a)
    s.step("1/8 welcome", r"1/8.*Welcome.*What now\?", ENTER)
    s.step("2/8 profile", r"2/8.*Profile and host.*\n.*guest \(recommended\)", ENTER)
    s.step("2/8 host name", r"Name for this machine", None)
    # <- (back): on an empty field it goes back one screen
    s.send(BACKSPACE * 80)
    s.send(LEFT)
    s.step("back to 1/8 with <-", r"1/8.*Welcome.*What now\?", ENTER)
    s.step("2/8 profile again", r"2/8.*Profile and host", ENTER)
    s.step("2/8 host name again", r"Name for this machine", None, snap=False)
    s.send(BACKSPACE * 80)
    s.type(host)
    s.snapshot("host name typed")
    s.send(ENTER)
    s.step("3/8 git name", r"3/8.*Your preferences.*Git name for this machine", None)
    s.send(BACKSPACE * 80)
    s.type(a.name)
    s.send(ENTER)
    s.step("3/8 git e-mail", r"Git e-mail for this machine", None, snap=False)
    s.send(BACKSPACE * 80)
    s.type(a.email)
    s.send(ENTER)
    s.step("3/8 wallpaper folder (left empty)", r"Wallpaper folder \(empty = skip\)", ENTER)
    s.step("3/8 lock image menu (skip)", r"Lock-screen image", DOWN + ENTER)
    s.step("4/8 scan table", r"4/8.*Scan", None, timeout=180)
    found = scroll_table(s, rf"{re.escape(pkg)} missing distro package", "scan table")
    s.check("scan table: PgDn paging shows every row (none is hidden by the ... markers)", not getattr(s, "pgdn_missed", []),
            "rows skipped by PgDn: " + "; ".join(m[:40] for m in getattr(s, "pgdn_missed", [])[:3]))
    s.snapshot("scan table scrolled to the package row")
    s.check(f"scan lists {pkg} as missing / distro package", found)
    for _ in range(40):
        s.send(UP, 0.01)
    if until == "scan":
        s.send(CTRL_C)
        return
    s.send(ENTER)
    s.step("5/8 plan checklist", r"5/8.*Plan.*Choose what to install", None, timeout=60)
    select_only(s, [pkg] + a.extra)
    s.send(ENTER)
    # the plan table: every command and dry run is shown BEFORE the confirmation
    s.step("5/8 plan table (commands + dry run)", r"Dry run passed|FAIL Dry run|Dry run could not", None, timeout=300)
    seen = ""
    cmd_rx = rf"(apt-get install -y|dnf install -y|pacman -Syu --needed --noconfirm) .*\b{re.escape(pkg)}\b"
    for _ in range(30):
        seen += "\n" + s.term.text()
        if re.search(r"Dry run passed", seen) and re.search(cmd_rx, seen):
            break
        before = s.term.text()
        s.send(PGDN)
        if s.term.text() == before:
            break
    s.snapshot("plan table")
    s.check("plan table shows the exact install command", re.search(cmd_rx, seen))
    s.check("plan table shows the dry-run result", "Dry run passed" in seen)
    for extra in a.extra:
        s.check(f"plan table also shows the install command for {extra}",
                re.search(rf"(apt-get install -y|dnf install -y|pacman -Syu --needed --noconfirm) .*\b{re.escape(extra)}\b", seen))
    s.check("plan has only the ticked packages", len(re.findall(r"Install \d+ package", seen)) <= 1 + len(a.extra),
            "more steps than selected packages")
    s.send(ENTER)
    s.step("5/8 plan confirmation", r"Run this plan now\?", None)
    s.check("confirmation appears after the commands were shown", True)
    if until == "plan-confirm":
        s.send(ESC)
        s.step("cancel message", r"Stopped\. Nothing after this point was done", ENTER)
        return
    s.send(UP + ENTER)  # the default is No; Up selects Yes
    s.step("6/8 install finished", r"Installed: \d+ . skipped: 0 . failed: 0", None, timeout=900)
    s.check("6/8 install summary says skipped 0, failed 0", True)
    s.send(ENTER)
    s.step("7/8 configure", r"7/8.*Configure", None, timeout=60)
    if re.search(r"Add the loader\?", s.term.text()):
        s.step("7/8 bashrc loader question", r"Add the loader\?", ENTER)  # default Yes
    s.step("7/8 apply now?", r"Apply the configuration now\?", UP + ENTER)
    # curses is suspended; rice-onboard + rice apply talk to the real terminal
    s.wait_for(r"onboarding done . profile=guest host=" + re.escape(host), 120, main=True, what="onboarding done (main screen)")
    s.wait_for(r"apply\? \[y/N\]", 120, main=True, what="rice apply confirmation")
    s.say("--- suspended terminal (main screen) so far:")
    for ln in (s.term.scrollback + s.term.lines())[-14:]:
        if ln.strip():
            s.say("  | " + ln)
    s.send("y\r")
    s.wait_for(r"Press ENTER to return to the installer", 120, main=True, what="press ENTER to return")
    s.send(ENTER)
    s.step("7/8 configuration applied", r"Configuration applied\.", ENTER, timeout=60)
    s.step("8/8 verify (doctor ran)", r"8/8.*Verify", None, timeout=120)
    ok = scroll_table(s, r"Everything checks out|check\(s\) failed", "doctor summary")
    s.snapshot("verify screen")
    s.check("8/8 verify screen shows the rice doctor result", ok or re.search(r"== |ok\s", s.term.text()))
    s.send(ENTER)


def oneliner_prelude(s, a):
    """install.sh's own questions, before the TUI (what a stranger sees)."""
    s.wait_for(r"To open the guided installer I first need:", 120, main=True, what="install.sh missing-list")
    s.wait_for(r"Install these now\? \[y/N\] ", 30, main=True, what="install.sh [y/N]")
    s.say("--- what install.sh printed before asking (main screen, as the stranger sees it):")
    log = s.term.mainlog
    for ln in log[log.rfind("To open the guided installer"):].splitlines():
        s.say("  | " + ln)
    s.send("y\r")
    s.wait_for(r"rice setup . 1/8", 900, what="TUI opened after the installs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=["walk", "cancel", "ctrlc"])
    ap.add_argument("--cmd", required=True)
    ap.add_argument("--pkg", default="fzf")
    ap.add_argument("--host", default="e2e-box")
    ap.add_argument("--name", default="E2E Bot")
    ap.add_argument("--email", default="e2e@example.com")
    ap.add_argument("--log")
    ap.add_argument("--extra", default="", help="more packages to tick, comma separated")
    ap.add_argument("--expect-exit", type=int, help="exit code of the command (default: by scenario)")
    ap.add_argument("--prelude", action="store_true", help="first answer install.sh's own [y/N] prompt")
    a = ap.parse_args()
    env = {**os.environ, "TERM": "xterm", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "COLUMNS": str(COLS), "LINES": str(ROWS)}
    env.pop("NO_COLOR", None)
    a.extra = [x for x in a.extra.split(",") if x]
    s = Session(a.cmd, env, a.log)
    expect, until = 0, None
    if a.scenario == "cancel":
        expect, until = 1, "plan-confirm"
    elif a.scenario == "ctrlc":
        expect, until = 130, "scan"
    if a.expect_exit is not None:
        expect = a.expect_exit
    try:
        walk(s, a, until)
        if a.scenario == "walk":
            s.check("every screen 1..8 was drawn", all(i in s.term.headers for i in range(1, 9)),
                    f"saw {sorted(s.term.headers)}")
            s.say("screens seen: " + ", ".join(f"{i}/8 {s.term.headers[i]}" for i in sorted(s.term.headers)))
        if a.scenario == "ctrlc":
            s.wait_for(r"rice tui: interrupted\.", 15, main=True, what="interrupted message")
            s.check("Ctrl-C printed the interruption notice", True)
        final_checks(s, a.scenario, expect)
    except Fail as e:
        s.check(f"{a.scenario}: flow completed", False, str(e))
        s.kill()
    except Exception as e:  # a harness bug must be visible, never a silent pass
        s.check(f"{a.scenario}: driver error", False, repr(e))
        s.snapshot("driver error")
        s.kill()
    bad = [n for n, ok in s.checks if not ok]
    s.say(f"driver: {len(s.checks) - len(bad)} checks ok, {len(bad)} failed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
