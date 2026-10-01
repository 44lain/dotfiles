import json
import os
import tempfile
import unittest
from pathlib import Path

from installer import validate


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def touch(self, rel):
        p = Path(self.home, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return p


class WallpaperDir(Base):
    def test_ok_counts_images_recursively_case_insensitive(self):
        for n in ("a.jpg", "b.PNG", "sub/c.webp", "notes.txt"):
            self.touch("Pictures/wp/" + n)
        r = validate.check_wallpaper_dir("~/Pictures/wp", self.home)
        self.assertEqual((r.ok, r.code, r.args["count"]), (True, "wallpaper.ok", 3))
        self.assertEqual(r.value, f"{self.home}/Pictures/wp")

    def test_empty_means_skip(self):
        r = validate.check_wallpaper_dir("", self.home)
        self.assertEqual((r.ok, r.value, r.code), (True, "", "wallpaper.skipped"))

    def test_path_without_leading_slash_is_rejected(self):
        # the real mistake from the first Parrot install: "home/user/Pictures"
        r = validate.check_wallpaper_dir("home/user/Pictures/wp", self.home)
        self.assertEqual((r.ok, r.code), (False, "wallpaper.relative"))

    def test_missing_and_not_a_directory(self):
        self.assertEqual(validate.check_wallpaper_dir("/nonexistent/zzz", self.home).code, "wallpaper.missing")
        f = self.touch("file.txt")
        self.assertEqual(validate.check_wallpaper_dir(str(f), self.home).code, "wallpaper.not_dir")

    def test_empty_folder_suggests_a_parent_that_has_images(self):
        # the britinhas case: the folder is empty, its parent holds the pictures
        self.touch("Pictures/wallpapers/one.jpg")
        Path(self.home, "Pictures/wallpapers/britinhas").mkdir()
        r = validate.check_wallpaper_dir(f"{self.home}/Pictures/wallpapers/britinhas", self.home)
        self.assertEqual((r.ok, r.code), (False, "wallpaper.empty_parent"))
        self.assertEqual(r.suggestion, f"{self.home}/Pictures/wallpapers")
        self.assertEqual(r.args["count"], 1)

    def test_empty_folder_without_useful_parent(self):
        Path(self.home, "Pictures/empty").mkdir(parents=True)
        r = validate.check_wallpaper_dir(f"{self.home}/Pictures/empty", self.home)
        self.assertEqual((r.ok, r.code, r.suggestion), (False, "wallpaper.empty", None))

    def test_first_image_is_sorted_and_recursive(self):
        self.touch("w/b.jpg")
        self.touch("w/a.png")
        self.assertEqual(validate.first_image(f"{self.home}/w", self.home), f"{self.home}/w/a.png")
        self.assertEqual(validate.first_image(f"{self.home}/none", self.home), "")


class WallpaperImage(Base):
    def test_file_ok(self):
        p = self.touch("w/a.jpg")
        r = validate.check_wallpaper_image(str(p), self.home)
        self.assertEqual((r.ok, r.code), (True, "image.ok"))

    def test_folder_is_explained_not_accepted(self):
        Path(self.home, "w").mkdir()
        r = validate.check_wallpaper_image(f"{self.home}/w", self.home)
        self.assertEqual((r.ok, r.code), (False, "image.is_dir"))

    def test_relative_missing_and_not_image(self):
        self.assertEqual(validate.check_wallpaper_image("w/a.jpg", self.home).code, "image.relative")
        self.assertEqual(validate.check_wallpaper_image("/nonexistent/a.jpg", self.home).code, "image.missing")
        t = self.touch("w/a.txt")
        self.assertEqual(validate.check_wallpaper_image(str(t), self.home).code, "image.not_image")

    def test_empty_means_skip(self):
        self.assertEqual(validate.check_wallpaper_image("", self.home).code, "image.skipped")


class Identity(unittest.TestCase):
    def test_name(self):
        self.assertFalse(validate.check_name("  ").ok)
        r = validate.check_name(" Ana Dev ")
        self.assertEqual((r.ok, r.value), (True, "Ana Dev"))

    def test_email(self):
        for bad in ("", "no-at", "a@b", "a b@c.d", "@x.y"):
            self.assertFalse(validate.check_email(bad).ok, bad)
        self.assertTrue(validate.check_email("ana@example.com").ok)

    def test_host_name(self):
        self.assertEqual(validate.check_host_name("my host", []).code, "host.invalid")
        self.assertEqual(validate.check_host_name("", []).code, "host.invalid")
        self.assertEqual(validate.check_host_name("desktop", ["desktop"]).code, "host.exists")
        self.assertTrue(validate.check_host_name("parrot-laptop_2", ["desktop"]).ok)


class ShellJson(Base):
    path = property(lambda self: Path(self.home, ".config/grootshell/shell.json"))

    def test_creates_the_file(self):
        out = validate.write_shell_json("/p/w", self.home)
        self.assertEqual(out, str(self.path))
        self.assertEqual(json.loads(self.path.read_text()), {"wallpaper": {"directory": "/p/w"}})

    def test_preserves_every_other_key(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"bar": {"height": 30}, "wallpaper": {"fit": "cover", "directory": "/old"}}))
        validate.write_shell_json("/new", self.home)
        self.assertEqual(json.loads(self.path.read_text()),
                         {"bar": {"height": 30}, "wallpaper": {"fit": "cover", "directory": "/new"}})

    def test_invalid_json_is_never_overwritten(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{ not json")
        with self.assertRaises(validate.ShellJsonInvalid):
            validate.write_shell_json("/x", self.home)
        self.assertEqual(self.path.read_text(), "{ not json")

    def test_wrong_shape_is_invalid_too(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"wallpaper": "oops"}))
        with self.assertRaises(validate.ShellJsonInvalid):
            validate.write_shell_json("/x", self.home)

    def test_never_touches_a_shell_json_inside_the_clone(self):
        clone = Path(self.home, ".config/quickshell/grootshell/shell.json")
        clone.parent.mkdir(parents=True)
        clone.write_text("{}")
        validate.write_shell_json("/x", self.home)
        self.assertEqual(clone.read_text(), "{}")


if __name__ == "__main__":
    unittest.main()
