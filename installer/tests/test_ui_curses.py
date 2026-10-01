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


def run_in_pty(rows, cols, steps, scenario="menu", wait=1.0, tail=8):
    """Run CHILD in a pty. `steps` is a list of byte strings to type, or
    ("resize", rows, cols) tuples; each is applied `wait` seconds after the last
    output (the first one after the first output). Returns (output, exit code or
    None when the child had to be killed)."""
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
                r, _, _ = select.select([fd], [], [], 0.1)
                if r:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        return False
                    if not chunk:
                        return False
                    out += chunk
            return True

        alive = True
        start = time.time()
        while alive and not out and time.time() - start < 8:
            alive = pump(0.2)
        for step in steps:
            if not alive:
                break
            alive = pump(wait)
            if not alive:
                break
            if isinstance(step, tuple):
                fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", step[1], step[2], 0, 0))
            else:
                os.write(fd, step)
        end = time.time() + tail
        while alive and time.time() < end:
            alive = pump(0.2)
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


class Smoke(unittest.TestCase):
    def test_draws_the_frame_and_esc_cancels(self):
        out, code = run_in_pty(30, 100, [b"\x1b"])
        self.assertEqual(code, 0)
        self.assertIn("Preferences", out)
        self.assertIn("hello from the frame", out)
        self.assertIn("Alpha", out)
        self.assertIn("RESULT CANCEL", out)

    def test_enter_selects_the_first_option(self):
        out, code = run_in_pty(30, 100, [b"\n"])
        self.assertEqual(code, 0)
        self.assertIn("RESULT a", out)

    def test_down_then_enter_selects_the_second_option(self):
        out, code = run_in_pty(30, 100, [DOWN, b"\n"])
        self.assertEqual(code, 0)
        self.assertIn("RESULT b", out)

    def test_left_arrow_goes_back_from_a_menu(self):
        out, code = run_in_pty(30, 100, [LEFT])
        self.assertEqual(code, 0)
        self.assertIn("RESULT BACK", out)

    def test_a_small_terminal_shows_the_resize_notice_instead_of_crashing(self):
        out, code = run_in_pty(10, 40, [b"x"], tail=2)
        self.assertIn("too small", out)
        self.assertNotIn("Traceback", out)

    def test_growing_the_terminal_redraws_instead_of_counting_as_input(self):
        out, code = run_in_pty(10, 40, [("resize", 30, 100), b"\n"])
        self.assertIn("too small", out)
        self.assertIn("Alpha", out)
        self.assertEqual(code, 0)
        self.assertIn("RESULT a", out)

    def test_text_keeps_accented_input_intact_and_shows_the_validation_message(self):
        out, code = run_in_pty(30, 100, ["ã".encode(), b"\n"], scenario="text")
        self.assertEqual(code, 0)
        self.assertIn("type something", out)
        self.assertIn("looks good", out)
        self.assertIn("RESULT 'ã'", out)

    def test_text_refuses_enter_while_invalid_then_esc_cancels(self):
        out, code = run_in_pty(30, 100, [b"\n", b"\x1b"], scenario="text")
        self.assertEqual(code, 0)
        self.assertIn("RESULT CANCEL", out)

    def test_checklist_space_toggles_and_enter_returns_the_selection(self):
        # Yankee starts checked; toggle Xray (cursor on it), keep Yankee.
        out, code = run_in_pty(30, 100, [b" ", b"\n"], scenario="checklist")
        self.assertEqual(code, 0)
        self.assertIn("RESULT ['x', 'y']", out)


if __name__ == "__main__":
    unittest.main()
