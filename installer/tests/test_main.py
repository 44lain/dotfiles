import io
import os
import tempfile
import unittest
from pathlib import Path

from installer import __main__ as cli


class Args(unittest.TestCase):
    def test_defaults(self):
        a = cli.parse_args([])
        self.assertEqual((a.plain, a.lang, a.repo), (False, None, None))

    def test_flags(self):
        a = cli.parse_args(["--plain", "--lang", "pt-BR", "--repo", "/x"])
        self.assertEqual((a.plain, a.lang, a.repo), (True, "pt-BR", "/x"))


class Build(unittest.TestCase):
    def test_state_uses_lang_flag_over_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = cli.build_state(cli.parse_args(["--lang", "pt"]), {"LANG": "en_US"}, home=tmp)
            self.assertEqual(s.lang, "pt_br")
            self.assertTrue(s.log_path.startswith(os.path.join(tmp, ".local/state/rice/install-")))

    def test_state_falls_back_to_lang_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cli.build_state(cli.parse_args([]), {"LANG": "pt_BR.UTF-8"}, home=tmp).lang, "pt_br")

    def test_repo_defaults_to_the_package_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = cli.build_state(cli.parse_args([]), {}, home=tmp)
            self.assertTrue((s.repo / ".chezmoidata" / "packages.toml").exists())


class Main(unittest.TestCase):
    def test_plain_flow_cancels_cleanly_on_eof(self):
        # Review Focus 4: no terminal -> plain mode, EOF -> cancelled, never a traceback
        import contextlib
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(out):
            rc = cli.main(["--plain", "--lang", "en"], stdin=io.StringIO(""), env={"HOME": tmp}, home=tmp)
        self.assertEqual(rc, 1)
        self.assertIn("Welcome", out.getvalue())
        self.assertIn("Stopped", out.getvalue())

    def test_local_bin_is_put_on_path_so_tools_installed_there_are_found(self):
        import contextlib
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"PATH": "/usr/bin"}), \
                contextlib.redirect_stdout(io.StringIO()):
            cli.main(["--plain", "--lang", "en"], stdin=io.StringIO(""), env={}, home=tmp)
            self.assertEqual(os.environ["PATH"].split(":")[0], os.path.join(tmp, ".local", "bin"))
            cli.main(["--plain", "--lang", "en"], stdin=io.StringIO(""), env={}, home=tmp)
            self.assertEqual(os.environ["PATH"].count(os.path.join(tmp, ".local", "bin")), 1)

    def test_unreadable_packages_file_is_an_error_not_a_traceback(self):
        import contextlib
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            rc = cli.main(["--plain", "--repo", tmp], stdin=io.StringIO(""), env={}, home=tmp)
        self.assertEqual(rc, 2)
        self.assertIn("packages.toml", err.getvalue())

    def test_keyboard_interrupt_restores_terminal_and_exits_130(self):
        import contextlib
        from unittest import mock

        class FakeUI:
            closed = 0
            waits = []
            def close(self, wait=True):
                FakeUI.closed += 1
                FakeUI.waits.append(wait)

        def boom(ui, state):
            raise KeyboardInterrupt

        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err), \
                mock.patch.object(cli.ui, "make_ui", return_value=FakeUI()), \
                mock.patch.object(cli.screens, "run_flow", boom):
            rc = cli.main(["--plain", "--lang", "en"], stdin=io.StringIO(""), env={}, home=tmp)
        self.assertEqual(rc, 130)
        self.assertEqual(FakeUI.closed, 1)
        self.assertEqual(FakeUI.waits, [False])  # Ctrl-C must never wait for a key
        self.assertNotIn("Traceback", err.getvalue())


if __name__ == "__main__":
    unittest.main()
