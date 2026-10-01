import hashlib
import io
import os
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from installer import recipes
from installer.recipes import Ctx, RecipeError
from installer.tests.fakes import cp


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = str(self.tmp / "home")
        os.makedirs(self.home)
        self.calls = []
        self.ctx = Ctx(home=self.home, runner=self.runner, sudo=["sudo", "-n"])

    def tearDown(self):
        self._tmp.cleanup()

    def runner(self, argv, on_line=None):
        self.calls.append(list(argv))
        return cp(0, "")

    def url(self, name, data: bytes) -> str:
        p = self.tmp / name
        p.write_bytes(data)
        return p.as_uri()


class ReleaseBinary(Base):
    def archive(self, member=b"#!/bin/sh\necho ok\n"):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            info = tarfile.TarInfo("matugen")
            info.size = len(member)
            t.addfile(info, io.BytesIO(member))
        return buf.getvalue()

    def spec(self, data, sha256=None):
        return {"kind": "release-binary", "url": self.url("m.tgz", data),
                "sha256": sha256 or sha(data), "member": "matugen", "dest": "~/.local/bin/matugen"}

    def test_installs_executable_into_home(self):
        data = self.archive()
        recipes.run_recipe(self.spec(data), self.ctx)
        dest = Path(self.home, ".local/bin/matugen")
        self.assertEqual(dest.read_bytes(), b"#!/bin/sh\necho ok\n")
        self.assertTrue(os.access(dest, os.X_OK))

    def test_checksum_mismatch_aborts_and_writes_nothing(self):
        data = self.archive()
        with self.assertRaises(RecipeError) as cm:
            recipes.run_recipe(self.spec(data, sha256="0" * 64), self.ctx)
        self.assertIn("checksum mismatch", str(cm.exception))
        self.assertIn("m.tgz", str(cm.exception))
        self.assertFalse(Path(self.home, ".local/bin/matugen").exists())

    def test_missing_member(self):
        spec = self.spec(self.archive())
        spec["member"] = "nope"
        with self.assertRaises(RecipeError):
            recipes.run_recipe(spec, self.ctx)

    def test_unreachable_url_is_a_clear_error(self):
        spec = self.spec(self.archive())
        spec["url"] = (self.tmp / "does-not-exist").as_uri()
        with self.assertRaises(RecipeError) as cm:
            recipes.run_recipe(spec, self.ctx)
        self.assertIn("download failed", str(cm.exception))

    def test_running_twice_is_safe(self):
        spec = self.spec(self.archive())
        recipes.run_recipe(spec, self.ctx)
        recipes.run_recipe(spec, self.ctx)
        self.assertTrue(Path(self.home, ".local/bin/matugen").exists())


class Fonts(Base):
    def test_plain_file_and_zip_members(self):
        ttf = b"TTF-DATA"
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w") as z:
            z.writestr("CaskaydiaCoveNerdFontMono-Regular.ttf", b"REG")
            z.writestr("Other.ttf", b"NOPE")
        zdata = zbuf.getvalue()
        spec = {"kind": "fonts", "files": [
            {"url": self.url("R.ttf", ttf), "sha256": sha(ttf), "name": "Rubik.ttf"},
            {"url": self.url("C.zip", zdata), "sha256": sha(zdata),
             "members": ["CaskaydiaCoveNerdFontMono-Regular.ttf"]},
        ]}
        recipes.run_recipe(spec, self.ctx)
        d = Path(self.home, ".local/share/fonts/dotfiles-required")
        self.assertEqual((d / "Rubik.ttf").read_bytes(), ttf)
        self.assertEqual((d / "CaskaydiaCoveNerdFontMono-Regular.ttf").read_bytes(), b"REG")
        self.assertFalse((d / "Other.ttf").exists())
        self.assertIn(["fc-cache", "-f"], self.calls)

    def test_one_bad_checksum_writes_no_font_at_all(self):
        a, b = b"AAA", b"BBB"
        spec = {"kind": "fonts", "files": [
            {"url": self.url("a.ttf", a), "sha256": sha(a), "name": "a.ttf"},
            {"url": self.url("b.ttf", b), "sha256": "1" * 64, "name": "b.ttf"},
        ]}
        with self.assertRaises(RecipeError):
            recipes.run_recipe(spec, self.ctx)
        self.assertFalse(Path(self.home, ".local/share/fonts/dotfiles-required").exists())
        self.assertNotIn(["fc-cache", "-f"], self.calls)


class GitClone(Base):
    SPEC = {"kind": "git-clone", "url": "https://example.invalid/g", "branch": "rice",
            "dest": "~/.config/quickshell/grootshell"}

    def test_clones_with_branch(self):
        recipes.run_recipe(self.SPEC, self.ctx)
        self.assertEqual(self.calls[-1], ["git", "clone", "--branch", "rice",
                                          "https://example.invalid/g",
                                          f"{self.home}/.config/quickshell/grootshell"])

    def test_existing_checkout_is_left_alone(self):
        dest = Path(self.home, ".config/quickshell/grootshell/.git")
        dest.mkdir(parents=True)
        recipes.run_recipe(self.SPEC, self.ctx)
        self.assertEqual(self.calls, [])

    def test_existing_non_git_directory_is_an_error(self):
        Path(self.home, ".config/quickshell/grootshell").mkdir(parents=True)
        with self.assertRaises(RecipeError):
            recipes.run_recipe(self.SPEC, self.ctx)

    def test_clone_failure_is_reported(self):
        self.ctx.runner = lambda argv, on_line=None: cp(128, "fatal: unable to access")
        with self.assertRaises(RecipeError) as cm:
            recipes.run_recipe(self.SPEC, self.ctx)
        self.assertIn("unable to access", str(cm.exception))


class Describe(unittest.TestCase):
    def test_release_binary_text_names_url_checksum_and_destination(self):
        lines = recipes.describe({"kind": "release-binary", "url": "https://x/y.tgz", "sha256": "ab" * 32,
                                  "member": "m", "dest": "~/.local/bin/m"}, "/h")
        text = "\n".join(lines)
        self.assertIn("https://x/y.tgz", text)
        self.assertIn("abababababab", text)
        self.assertIn("/h/.local/bin/m", text)

    def test_git_clone_text(self):
        text = "\n".join(recipes.describe(GitClone.SPEC, "/h"))
        self.assertIn("git clone --branch rice https://example.invalid/g /h/.config/quickshell/grootshell", text)


class StreamRun(unittest.TestCase):
    def test_streams_output_and_returns_combined_stdout(self):
        """Test that stream_run properly collects output and calls on_line callback."""
        lines = []
        cp = recipes.stream_run(["sh", "-c", "echo one; echo two"], on_line=lines.append)
        self.assertEqual(lines, ["one", "two"])
        self.assertEqual(cp.returncode, 0)
        self.assertIn("one", cp.stdout)
        self.assertIn("two", cp.stdout)

    def test_nonexistent_command_returns_127_without_raising(self):
        """Test that nonexistent command returns rc 127 without raising."""
        cp = recipes.stream_run(["this-command-definitely-does-not-exist-xyz-123"])
        self.assertEqual(cp.returncode, 127)
        self.assertIn("command not found", cp.stdout)

    def test_invalid_utf8_output_handled_gracefully(self):
        """Test that invalid UTF-8 output is handled gracefully with errors=replace."""
        # Use printf with octal escape to produce invalid UTF-8 byte
        cp = recipes.stream_run(["sh", "-c", "printf '\\xff\\n'"])
        # Should not raise UnicodeDecodeError, should return rc 0
        self.assertEqual(cp.returncode, 0)
        # The invalid byte should be replaced, not cause an exception
        self.assertIsNotNone(cp.stdout)


class Fetch(unittest.TestCase):
    def test_malformed_url_raises_recipe_error_with_download_failed(self):
        """Test that malformed URL raises RecipeError with 'download failed' message."""
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "test")
            with self.assertRaises(RecipeError) as cm:
                recipes._fetch("not a url", dest)
            self.assertIn("download failed", str(cm.exception))

    def test_http_incomplete_read_raises_recipe_error_with_download_failed(self):
        """Test that http.client.HTTPException raises RecipeError with 'download failed' message."""
        import http.client
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "test")
            with mock.patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.side_effect = http.client.IncompleteRead(b"x")
                with self.assertRaises(RecipeError) as cm:
                    recipes._fetch("http://example.invalid/test", dest)
                self.assertIn("download failed", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
