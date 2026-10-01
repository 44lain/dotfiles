import fcntl
import os
import pty
import select
import signal
import struct
import sys
import termios
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

CHILD = r"""
import sys
sys.path.insert(0, %r)
from installer import ui
from installer.messages import translator
scenario = sys.argv[1]
u = ui.CursesUI(translator("en"))
u.title(3, 8, "Preferences")
u.info("hello from the frame")
if scenario == "menu":
    r = u.menu("Pick one", [("a", "Alpha"), ("b", "Beta")])
elif scenario == "text":
    def check(v):
        return (True, "looks good") if v else (False, "type something")
    r = u.text("Your name", validate=check)
elif scenario == "bigchecklist":
    r = u.checklist("Choose", [ui.Item(f"p{i:02d}", f"Package {i + 1:02d}") for i in range(40)])
elif scenario == "table":
    r = u.table(("Name", "Value"), [(f"row{i:02d}", str(i)) for i in range(60)])
elif scenario == "checklist":
    r = u.checklist("Choose", [ui.Item("x", "Xray"), ui.Item("y", "Yankee", True), ui.Item("z", "Zulu")])
u.close()
u.close()
if r is ui.CANCEL:
    r = "CANCEL"
elif r is ui.BACK:
    r = "BACK"
print("RESULT", r if scenario == "menu" or r in ("CANCEL", "BACK") else repr(r))
"""

DOWN = b"\x1bOB"  # xterm terminfo kcud1 (keypad application mode)
LEFT = b"\x1bOD"  # kcub1


def run_in_pty(rows, cols, steps, scenario="menu", ready="Alpha", tail=8, timeout=5, offsets=None):
    """Run CHILD in a pty. Waits (up to `timeout` s) until `ready` shows up in the
    output, then applies each step: (action, expect) where action is bytes to type
    or ("resize", rows, cols) and expect is a string waited for after the action
    (None: do not wait). `offsets`, if given, receives len(output) before each step.
    Returns (output, exit code or None when the child had to be killed)."""
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm"
        os.environ["LANG"] = "C.UTF-8"
        os.execv(sys.executable, [sys.executable, "-c", CHILD % str(REPO), scenario])
    code = None
    out = b""
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

        def pump(seconds):
            nonlocal out
            end = time.time() + seconds
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.05)
                if r:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        return False
                    if not chunk:
                        return False
                    out += chunk
            return True

        def wait_for(marker, since):
            end = time.time() + timeout
            needle = marker.encode()
            while needle not in out[since:] and time.time() < end:
                if not pump(0.05):
                    return needle in out[since:]
            return needle in out[since:]

        alive = wait_for(ready, 0)
        for action, expect in steps:
            if not alive:
                break
            if offsets is not None:
                offsets.append(len(out))
            since = len(out)
            if isinstance(action, tuple):
                fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", action[1], action[2], 0, 0))
            else:
                os.write(fd, action)
            if expect:
                wait_for(expect, since)
        end = time.time() + tail
        while alive and time.time() < end:
            alive = pump(0.1)
        # EOF means the child closed the pty; give it a moment to be reapable.
        reap_until = time.time() + (3 if not alive else 0)
        while True:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                code = os.waitstatus_to_exitcode(status)
                pid = None
                break
            if time.time() >= reap_until:
                break
            time.sleep(0.05)
    finally:
        if pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
        os.close(fd)
    return out.decode("utf-8", "replace"), code


class FakeScr:
    """Stands in for a curses window: records what is drawn, fails if input is read."""

    def __init__(self, h, w):
        self.size = (h, w)
        self.drawn = []

    def getmaxyx(self):
        return self.size

    def erase(self):
        self.drawn = []

    def addstr(self, y, x, text, attr=0):
        self.drawn.append(text)

    def refresh(self):
        pass

    def get_wch(self):
        raise AssertionError("must not wait for input")

    def text(self):
        return "\n".join(self.drawn)


def fake_ui(h, w):
    from installer import ui
    from installer.messages import translator
    u = ui.CursesUI.__new__(ui.CursesUI)
    import curses
    u.curses, u.t, u.scr = curses, translator("en"), FakeScr(h, w)
    u.f, u.marks, u.attrs = ui.FRAME_UTF8, ("\u2713", "!", "\u2717", "\u00b7", "\u2191", "\u2193"), {}
    u.step, u.lines, u._eof, u._open = (1, 2, "x"), [], False, False
    return u


class Unit(unittest.TestCase):
    def test_draw_without_blocking_shows_the_notice_on_a_small_window(self):
        u = fake_ui(10, 40)
        u._draw([], "hint", block=False)
        self.assertIn("too small", u.scr.text())

    def test_progress_push_never_waits_for_input_on_a_small_window(self):
        u = fake_ui(10, 40)
        with u.progress("Installing") as push:
            push("line one")
            push("line two")
        self.assertIn("too small", u.scr.text())

    def test_progress_push_draws_the_frame_on_a_big_window(self):
        u = fake_ui(30, 100)
        with u.progress("Installing") as push:
            push("line one")
        self.assertIn("line one", u.scr.text())

    def test_table_scrolled_to_the_end_keeps_its_header(self):
        u = fake_ui(24, 80)
        body = [("Name  Value", "accent", True)] + [("row%02d" % i, None, False) for i in range(60)]
        start, page = u._draw(body, "hint", pinned=1, scroll=10 ** 9)
        text = u.scr.text()
        self.assertIn("Name  Value", text)
        self.assertIn("row59", text)
        self.assertNotIn("row00", text)
        self.assertGreater(start, 0)

    def test_empty_lists_do_not_raise_and_default_is_clamped(self):
        u = fake_ui(30, 100)
        from installer import ui
        self.assertIs(u.menu("Pick", []), ui.CANCEL)
        self.assertEqual(u.checklist("Pick", []), [])
        u._key = lambda: 10
        self.assertEqual(u.menu("Pick", [("a", "A"), ("b", "B")], default=9), "b")
        self.assertEqual(u.menu("Pick", [("a", "A"), ("b", "B")], default=-4), "a")


class Smoke(unittest.TestCase):
    def test_draws_the_frame_and_esc_cancels(self):
        out, code = run_in_pty(30, 100, [(b"\x1b", "RESULT")])
        self.assertEqual(code, 0)
        self.assertIn("Preferences", out)
        self.assertIn("hello from the frame", out)
        self.assertIn("Alpha", out)
        self.assertIn("RESULT CANCEL", out)

    def test_enter_selects_the_first_option(self):
        out, code = run_in_pty(30, 100, [(b"\n", "RESULT")])
        self.assertEqual(code, 0)
        self.assertIn("RESULT a", out)

    def test_down_then_enter_selects_the_second_option(self):
        out, code = run_in_pty(30, 100, [(DOWN, None), (b"\n", "RESULT")])
        self.assertEqual(code, 0)
        self.assertIn("RESULT b", out)

    def test_left_arrow_goes_back_from_a_menu(self):
        out, code = run_in_pty(30, 100, [(LEFT, "RESULT")])
        self.assertEqual(code, 0)
        self.assertIn("RESULT BACK", out)

    def test_a_small_terminal_shows_the_resize_notice_instead_of_crashing(self):
        out, code = run_in_pty(10, 40, [(b"x", None)], ready="too small", tail=0.5)
        self.assertIn("too small", out)
        self.assertNotIn("Traceback", out)

    def test_growing_the_terminal_redraws_instead_of_counting_as_input(self):
        out, code = run_in_pty(10, 40, [(("resize", 30, 100), "Alpha"), (b"\n", "RESULT")], ready="too small")
        self.assertIn("too small", out)
        self.assertIn("Alpha", out)
        self.assertEqual(code, 0)
        self.assertIn("RESULT a", out)

    def test_text_keeps_accented_input_intact_and_shows_the_validation_message(self):
        out, code = run_in_pty(30, 100, [("ã".encode(), "looks good"), (b"\n", "RESULT")],
                               scenario="text", ready="type something")
        self.assertEqual(code, 0)
        self.assertIn("type something", out)
        self.assertIn("looks good", out)
        self.assertIn("RESULT 'ã'", out)

    def test_text_refuses_enter_while_invalid_then_esc_cancels(self):
        out, code = run_in_pty(30, 100, [(b"\n", None), (b"\x1b", "RESULT")],
                               scenario="text", ready="type something")
        self.assertEqual(code, 0)
        self.assertIn("RESULT CANCEL", out)

    def test_checklist_space_toggles_and_enter_returns_the_selection(self):
        # Yankee starts checked; toggle Xray (cursor on it), keep Yankee.
        out, code = run_in_pty(30, 100, [(b" ", None), (b"\n", "RESULT")], scenario="checklist", ready="Xray")
        self.assertEqual(code, 0)
        self.assertIn("RESULT ['x', 'y']", out)

    def test_a_long_checklist_keeps_the_selected_item_visible(self):
        offsets = []
        out, code = run_in_pty(24, 100, [(DOWN * 35, "Package 36"), (b" ", None), (b"\n", "RESULT")],
                               scenario="bigchecklist", ready="Package 01", offsets=offsets)
        self.assertEqual(code, 0)
        self.assertNotIn("Package 36", out[:offsets[0]])
        self.assertIn("Package 36", out[offsets[0]:])
        self.assertIn("RESULT ['p35']", out)

    def test_a_long_table_keeps_its_header_and_scrolls(self):
        offsets = []
        out, code = run_in_pty(24, 100, [(DOWN * 70, "row59"), (b"\n", "RESULT")],
                               scenario="table", ready="row00", offsets=offsets)
        first = out[:offsets[0]]
        self.assertIn("Name", first)
        self.assertIn("row00", first)
        self.assertNotIn("row59", first)
        self.assertIn("row59", out)
        self.assertEqual(code, 0)
        self.assertIn("RESULT 'next'", out)


if __name__ == "__main__":
    unittest.main()
