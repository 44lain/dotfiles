import io
import unittest

from installer import ui
from installer.messages import translator

t = translator("en")


def plain(answers: str):
    out = io.StringIO()
    return ui.PlainUI(t, stdin=io.StringIO(answers), stdout=out), out


class ClosedStdin(unittest.TestCase):
    def test_make_ui_and_plainui_treat_a_missing_stdin_as_eof(self):
        from unittest import mock
        with mock.patch.object(ui.sys, "stdin", None):
            u = ui.make_ui(t, plain=True, stdin=None, stdout=io.StringIO())
            self.assertIsInstance(u, ui.PlainUI)
            self.assertIs(u.menu("Pick", [("a", "A")]), ui.CANCEL)
            self.assertIs(u.confirm("ok?"), ui.CANCEL)
            self.assertIs(u.text("name"), ui.CANCEL)
            self.assertIsInstance(ui.make_ui(t, stdin=None, stdout=io.StringIO()), ui.PlainUI)

    def test_python_m_installer_plain_with_stdin_closed_stops_cleanly(self):
        import subprocess
        import sys
        from pathlib import Path
        repo = Path(__file__).resolve().parents[2]
        r = subprocess.run(["bash", "-c", f'"{sys.executable}" -m installer --plain --lang en <&-'],
                           cwd=repo, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("Stopped", r.stdout)


class Menu(unittest.TestCase):
    OPTS = [("a", "Alpha"), ("b", "Beta")]

    def test_number_selects(self):
        u, out = plain("2\n")
        self.assertEqual(u.menu("Pick", self.OPTS), "b")
        self.assertIn("1) Alpha", out.getvalue())

    def test_enter_takes_the_default(self):
        u, _ = plain("\n")
        self.assertEqual(u.menu("Pick", self.OPTS, default=1), "b")

    def test_b_is_back_q_is_cancel_eof_is_cancel(self):
        self.assertIs(plain("b\n")[0].menu("Pick", self.OPTS), ui.BACK)
        self.assertIs(plain("q\n")[0].menu("Pick", self.OPTS), ui.CANCEL)
        self.assertIs(plain("")[0].menu("Pick", self.OPTS), ui.CANCEL)

    def test_invalid_input_asks_again(self):
        u, out = plain("9\nx\n1\n")
        self.assertEqual(u.menu("Pick", self.OPTS), "a")
        self.assertIn("1-2", out.getvalue())


class Checklist(unittest.TestCase):
    ITEMS = [ui.Item("a", "Alpha", True), ui.Item("b", "Beta", False), ui.Item("c", "Gamma", False)]

    def test_enter_keeps_the_preselection(self):
        u, _ = plain("\n")
        self.assertEqual(u.checklist("Pick", self.ITEMS), ["a"])

    def test_toggle_numbers_then_confirm(self):
        u, _ = plain("2 3\n\n")
        self.assertEqual(u.checklist("Pick", self.ITEMS), ["a", "b", "c"])

    def test_all_and_none(self):
        self.assertEqual(plain("a\n\n")[0].checklist("Pick", self.ITEMS), ["a", "b", "c"])
        self.assertEqual(plain("n\n\n")[0].checklist("Pick", self.ITEMS), [])

    def test_navigation(self):
        self.assertIs(plain("q\n")[0].checklist("Pick", self.ITEMS), ui.CANCEL)
        self.assertIs(plain("b\n")[0].checklist("Pick", self.ITEMS), ui.BACK)


class Text(unittest.TestCase):
    def test_default_and_value(self):
        self.assertEqual(plain("\n")[0].text("Name", "dflt"), "dflt")
        self.assertEqual(plain("ana\n")[0].text("Name", "dflt"), "ana")

    def test_validation_message_then_retry(self):
        u, out = plain("bad\ngood\n")
        v = lambda x: (x == "good", "must be good")
        self.assertEqual(u.text("Name", "", v), "good")
        self.assertIn("must be good", out.getvalue())

    def test_back_and_quit_commands(self):
        self.assertIs(plain("/back\n")[0].text("Name"), ui.BACK)
        self.assertIs(plain("/quit\n")[0].text("Name"), ui.CANCEL)
        self.assertIs(plain("")[0].text("Name"), ui.CANCEL)


class Confirm(unittest.TestCase):
    def test_answers(self):
        self.assertIs(plain("y\n")[0].confirm("Sure?"), True)
        self.assertIs(plain("n\n")[0].confirm("Sure?"), False)
        self.assertIs(plain("\n")[0].confirm("Sure?"), False)          # default is NO
        self.assertIs(plain("\n")[0].confirm("Sure?", default=True), True)
        self.assertIs(plain("q\n")[0].confirm("Sure?"), ui.CANCEL)
        self.assertIs(plain("b\n")[0].confirm("Sure?"), ui.BACK)
        self.assertIs(plain("s\n")[0].confirm("Sure?"), True)
        self.assertIs(plain("")[0].confirm("Sure?"), ui.CANCEL)


class Output(unittest.TestCase):
    def test_messages_progress_table(self):
        u, out = plain("\n")
        u.title(3, 8, "Preferences")
        u.info("hello")
        u.success("good")
        u.warn("careful")
        u.error("broken")
        with u.progress("Installing") as push:
            push("line one")
        self.assertEqual(u.table(["A", "B"], [["x", "y"]]), "next")
        text = out.getvalue()
        for needle in ("3/8", "Preferences", "hello", "good", "careful", "broken", "Installing", "line one", "x"):
            self.assertIn(needle, text)

    def test_suspend_runs_the_command(self):
        u, _ = plain("\n")
        self.assertEqual(u.suspend(["true"]), 0)
        self.assertNotEqual(u.suspend(["false"]), 0)

    def test_suspend_missing_command_returns_127(self):
        u, _ = plain("\n")
        # Test with a command that doesn't exist
        self.assertEqual(u.suspend(["/nonexistent_command_xyz"]), 127)


class Close(unittest.TestCase):
    def test_close_accepts_wait(self):
        u, _ = plain("")
        u.close()
        u.close(wait=False)


class MakeUi(unittest.TestCase):
    def test_plain_flag_and_non_tty_give_plain_ui(self):
        self.assertIsInstance(ui.make_ui(t, plain=True), ui.PlainUI)
        self.assertIsInstance(ui.make_ui(t, plain=False, stdin=io.StringIO(), stdout=io.StringIO()), ui.PlainUI)

    def test_dumb_terminal_gives_plain_ui(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True
        self.assertIsInstance(ui.make_ui(t, term="dumb", stdin=Tty(), stdout=Tty()), ui.PlainUI)


if __name__ == "__main__":
    unittest.main()
