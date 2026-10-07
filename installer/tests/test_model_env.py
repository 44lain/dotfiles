import os
import subprocess
import tempfile
import unittest

from installer import model
from installer.model import Env, _default_run


class DefaultRun(unittest.TestCase):
    def test_nonexistent_command_returns_127_without_raising(self):
        """Running a nonexistent command should return 127, not raise."""
        result = _default_run(["/nonexistent/command/that/does/not/exist"])
        self.assertEqual(result.returncode, 127)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "failed")

    def test_timeout_returns_127_without_raising(self):
        """A command exceeding timeout should return 127, not raise."""
        result = _default_run(["sleep", "5"], timeout=0.2)
        self.assertEqual(result.returncode, 127)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "timeout")

    def test_bad_shebang_returns_127_without_raising(self):
        """A bad-shebang executable should return 127, not raise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = os.path.join(tmpdir, "bad_shebang.sh")
            with open(script_path, "w") as f:
                f.write("#!/nonexistent/interp\necho hello\n")
            os.chmod(script_path, 0o755)

            result = _default_run([script_path])
            self.assertEqual(result.returncode, 127)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "failed")


class EnvIntegration(unittest.TestCase):
    def test_default_env_uses_default_run(self):
        """Env.run should use _default_run as default."""
        env = Env()
        result = env.run(["/nonexistent/command"])
        self.assertEqual(result.returncode, 127)


class Derivatives(unittest.TestCase):
    CASES = {
        'ID=arch\n': "arch",
        'ID=endeavouros\nID_LIKE=arch\n': "arch",
        'ID=cachyos\nID_LIKE=arch\n': "arch",
        'ID=garuda\nID_LIKE=arch\n': "arch",
        'ID=manjaro\nID_LIKE=arch\n': "arch",
        'ID="manjaro"\nID_LIKE="arch"\n': "arch",
        'ID=artix\nID_LIKE=arch\n': "unknown",  # no systemd: the session cannot work
    }

    def test_families(self):
        import tempfile
        for text, want in self.CASES.items():
            with tempfile.NamedTemporaryFile("w", suffix=".osr", delete=False) as f:
                f.write(text)
            self.assertEqual(model.os_family(f.name), want, text)
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
