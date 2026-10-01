import os
import tempfile
import unittest

from installer import model
from installer.tests.fakes import cp, make_env

TOML = """
[packages.hyprland]
desc = "compositor"
section = "Compositor & session"
bin = "Hyprland"
required = true
min_version = "0.55"
fedora = "hyprland"
debian = "hyprland"
arch = "hyprland"

[packages.kitty]
desc = "terminal"
section = "Terminal & tools"
bin = "kitty"
required = true
fedora = "kitty"
debian = "kitty"
arch = "kitty"

[packages.matugen]
desc = "palette"
section = "Bar / theming"
bin = "matugen"
required = true
fedora = ""
debian = ""
arch = "matugen"
manual = "cargo install matugen"
[packages.matugen.recipe]
kind = "release-binary"
arch = "x86_64"
url = "https://example.invalid/m.tgz"
sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
member = "matugen"
dest = "~/.local/bin/matugen"

[packages.gum]
desc = "prompts"
section = "Optional"
bin = "gum"
fedora = "gum"
debian = ""
arch = "gum"
manual = "charm repo"
[packages.gum.recipe]
kind = "apt-repo"
key_url = "https://example.invalid/k"
key_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
key_dest = "/etc/apt/keyrings/c.gpg"
source_file = "/etc/apt/sources.list.d/c.list"
source = "deb x y z"
package = "gum"

[packages.font-rubik]
desc = "Rubik"
section = "Fonts"
bin = ""
check = "font:Rubik"
fedora = ""
debian = ""
arch = ""
manual = "download it"
[packages.font-rubik.recipe]
kind = "fonts"
files = [ { url = "https://example.invalid/R.ttf", sha256 = "0000000000000000000000000000000000000000000000000000000000000000", name = "Rubik.ttf" } ]

[packages.polkit]
desc = "doc only"
section = "Compositor & session"
bin = ""
fedora = "p"
debian = "p"
arch = "p"
"""

MADISON_BACKPORTS = (
    " hyprland | 0.55.2-1~bpo13+1 | https://deb.parrot.sh/parrot echo-backports/main amd64 Packages\n"
    " hyprland | 0.52.2-1 | https://deb.parrot.sh/parrot echo/main amd64 Packages\n"
)
POLICY_DEFAULT_OLD = "hyprland:\n  Installed: (none)\n  Candidate: 0.52.2-1\n"


def packages():
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
        f.write(TOML)
    try:
        return {p.key: p for p in model.load_packages(f.name)}
    finally:
        os.unlink(f.name)


def one(statuses, key):
    return next(s for s in statuses if s.key == key)


class OsFamily(unittest.TestCase):
    def fam(self, text):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(text)
        try:
            return model.os_family(f.name)
        finally:
            os.unlink(f.name)

    def test_families(self):
        self.assertEqual(self.fam('ID=fedora\n'), "fedora")
        self.assertEqual(self.fam('ID=parrot\nID_LIKE=debian\n'), "debian")
        self.assertEqual(self.fam('ID=linuxmint\nID_LIKE="ubuntu debian"\n'), "debian")
        self.assertEqual(self.fam('ID=arch\n'), "arch")
        self.assertEqual(self.fam('ID=nixos\n'), "unknown")

    def test_missing_file(self):
        self.assertEqual(model.os_family("/nonexistent/os-release"), "unknown")


class Loading(unittest.TestCase):
    def test_fields(self):
        p = packages()
        self.assertEqual(p["hyprland"].min_version, "0.55")
        self.assertTrue(p["hyprland"].required)
        self.assertEqual(p["matugen"].names["debian"], "")
        self.assertEqual(p["matugen"].recipe["kind"], "release-binary")
        self.assertEqual(p["font-rubik"].check, "font:Rubik")


class Scan(unittest.TestCase):
    def scan(self, family, env):
        return model.scan(list(packages().values()), family, env)

    def test_present_is_ok_and_doc_only_is_skipped(self):
        env = make_env(which={"Hyprland", "kitty", "matugen", "gum"},
                       outputs={"Hyprland --version": cp(0, "Hyprland 0.55.2 built from x"),
                                "fc-list": cp(0, "Rubik:style=Regular")})
        st = self.scan("debian", env)
        self.assertTrue(all(s.state == "ok" for s in st))
        self.assertNotIn("polkit", [s.key for s in st])

    def test_debian_missing_uses_backports_flag(self):
        env = make_env(which={"kitty", "matugen", "gum"},
                       outputs={"apt-cache madison hyprland": cp(0, MADISON_BACKPORTS),
                                "apt-cache policy hyprland": cp(0, POLICY_DEFAULT_OLD),
                                "fc-list": cp(0, "Rubik")})
        s = one(self.scan("debian", env), "hyprland")
        self.assertEqual((s.state, s.source, s.name, s.flag), ("missing", "distro", "hyprland", "-t echo-backports"))

    def test_debian_apt_knows_nothing(self):
        env = make_env(which={"kitty", "matugen", "gum"},
                       outputs={"apt-cache madison hyprland": cp(0, ""), "fc-list": cp(0, "Rubik")})
        s = one(self.scan("debian", env), "hyprland")
        self.assertEqual((s.state, s.detail), ("no_source", "apt_unknown"))

    def test_debian_best_version_too_old(self):
        madison = " hyprland | 0.52.2-1 | https://x echo/main amd64 Packages\n"
        env = make_env(which={"kitty", "matugen", "gum"},
                       outputs={"apt-cache madison hyprland": cp(0, madison),
                                "apt-cache policy hyprland": cp(0, POLICY_DEFAULT_OLD),
                                "fc-list": cp(0, "Rubik")})
        s = one(self.scan("debian", env), "hyprland")
        self.assertEqual((s.state, s.detail, s.info), ("no_source", "apt_too_old", "0.52.2-1"))

    def test_installed_but_too_old(self):
        env = make_env(which={"Hyprland", "kitty", "matugen", "gum"},
                       outputs={"Hyprland --version": cp(0, "Hyprland 0.52.2 built"),
                                "apt-cache madison hyprland": cp(0, MADISON_BACKPORTS),
                                "apt-cache policy hyprland": cp(0, POLICY_DEFAULT_OLD),
                                "fc-list": cp(0, "Rubik")})
        s = one(self.scan("debian", env), "hyprland")
        self.assertEqual((s.state, s.source, s.flag), ("too_old", "distro", "-t echo-backports"))

    def test_recipe_is_the_fallback_when_family_has_no_package(self):
        env = make_env(which={"kitty", "Hyprland", "gum"},
                       outputs={"Hyprland --version": cp(0, "Hyprland 0.55.2"), "fc-list": cp(0, "Rubik")})
        s = one(self.scan("debian", env), "matugen")
        self.assertEqual((s.state, s.source), ("missing", "recipe"))
        self.assertEqual(s.recipe["kind"], "release-binary")

    def test_distro_package_wins_over_recipe(self):
        env = make_env(which={"kitty", "Hyprland", "gum"},
                       outputs={"Hyprland --version": cp(0, "Hyprland 0.55.2"), "fc-list": cp(0, "Rubik")})
        s = one(self.scan("arch", env), "matugen")
        self.assertEqual((s.source, s.name), ("distro", "matugen"))

    def test_recipe_ignored_on_other_architecture(self):
        env = make_env(which={"kitty", "Hyprland", "gum"}, machine="aarch64",
                       outputs={"Hyprland --version": cp(0, "Hyprland 0.55.2"), "fc-list": cp(0, "Rubik")})
        s = one(self.scan("debian", env), "matugen")
        self.assertEqual((s.state, s.detail), ("no_source", "no_package"))

    def test_repo_recipe_skips_apt_lookup_and_flags_repo(self):
        env = make_env(which={"kitty", "Hyprland", "matugen"},
                       outputs={"Hyprland --version": cp(0, "Hyprland 0.55.2"), "fc-list": cp(0, "Rubik")})
        s = one(self.scan("debian", env), "gum")
        self.assertEqual((s.source, s.name, s.repo), ("distro", "gum", True))
        self.assertFalse(any(c[:2] == ["apt-cache", "madison"] and c[2] == "gum" for c in env.calls))

    def test_repo_recipe_does_not_apply_on_other_family(self):
        env = make_env(which={"kitty", "Hyprland", "matugen"},
                       outputs={"Hyprland --version": cp(0, "Hyprland 0.55.2"), "fc-list": cp(0, "Rubik")})
        s = one(self.scan("fedora", env), "gum")
        self.assertEqual((s.source, s.name, s.repo), ("distro", "gum", False))

    def test_font_check_uses_fc_list(self):
        env = make_env(which={"kitty", "Hyprland", "matugen", "gum"},
                       outputs={"Hyprland --version": cp(0, "Hyprland 0.55.2"), "fc-list": cp(0, "DejaVu Sans")})
        s = one(self.scan("debian", env), "font-rubik")
        self.assertEqual((s.state, s.source), ("missing", "recipe"))

    def test_actionable_excludes_ok_and_no_source(self):
        env = make_env(which={"kitty", "Hyprland", "gum"},
                       outputs={"Hyprland --version": cp(0, "Hyprland 0.55.2"), "fc-list": cp(0, "Rubik")})
        act = model.actionable(self.scan("debian", env))
        self.assertEqual([s.key for s in act], ["matugen"])


if __name__ == "__main__":
    unittest.main()


class NotesAsManual(unittest.TestCase):
    TOML2 = """
[packages.hypr2]
desc = "compositor"
section = "x"
bin = "Hypr2"
required = true
fedora = "hypr2"
debian = "hypr2"
arch = "hypr2"
note_debian = "use backports; never add Debian repos on Ubuntu"
[packages.hypr3]
desc = "other"
section = "x"
bin = "Hypr3"
fedora = "hypr3"
debian = "hypr3"
arch = "hypr3"
manual = "do it by hand"
note_debian = "ignored when manual exists"
"""

    def test_a_debian_note_fills_manual_when_the_package_has_none(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write(self.TOML2)
        try:
            pk = model.load_packages(f.name)
        finally:
            os.unlink(f.name)
        env = make_env(outputs={"apt-cache madison": cp(0, ""), "apt-cache policy": cp(0, "")})
        out = {s.key: s for s in model.scan(pk, "debian", env)}
        self.assertEqual(out["hypr2"].state, "no_source")
        self.assertIn("never add Debian repos on Ubuntu", out["hypr2"].manual)
        self.assertEqual(out["hypr3"].manual, "do it by hand")
        fed = {s.key: s for s in model.scan(pk, "fedora", make_env())}
        self.assertEqual(fed["hypr2"].manual, "")  # another family's note is not shown


class Locale(unittest.TestCase):
    def test_apt_probes_run_with_the_c_locale(self):
        env = make_env(outputs={"apt-cache madison kitty": cp(0, " kitty | 1.0 | https://x stable/main amd64 Packages\n"),
                                "apt-cache policy kitty": cp(0, "Candidate: 1.0\n")})
        model.apt_lookup("kitty", env)
        self.assertEqual(len(env.kwargs), 2)
        self.assertTrue(all(kw["env"]["LC_ALL"] == "C" for kw in env.kwargs))
