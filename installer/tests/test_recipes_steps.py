import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from installer import model, recipes
from installer.recipes import Ctx, RecipeError, SudoExpired
from installer.tests.fakes import cp

KEY = b"-----BEGIN PGP PUBLIC KEY BLOCK-----\nabc\n"
APT = {"kind": "apt-repo", "key_sha256": hashlib.sha256(KEY).hexdigest(), "dearmor": True,
       "key_dest": "/etc/apt/keyrings/charm.gpg", "source_file": "/etc/apt/sources.list.d/charm.list",
       "source": "deb [signed-by=/etc/apt/keyrings/charm.gpg] https://repo.charm.sh/apt/ * *",
       "package": "gum"}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.calls = []
        keyfile = self.tmp / "key"
        keyfile.write_bytes(KEY)
        self.spec = dict(APT, key_url=keyfile.as_uri())
        self.ctx = Ctx(home=str(self.tmp), runner=self.runner, sudo=["sudo", "-n"], exists=lambda p: False)

    def tearDown(self):
        self._tmp.cleanup()

    def runner(self, argv, on_line=None):
        self.calls.append(list(argv))
        return cp(0, "")


class AptRepo(Base):
    def test_adds_key_source_and_updates_with_sudo(self):
        recipes.run_recipe(self.spec, self.ctx)
        joined = [" ".join(c) for c in self.calls]
        self.assertTrue(any(c.startswith("gpg --dearmor") for c in joined))
        self.assertTrue(any(c.startswith("sudo -n install -Dm644") and c.endswith("/etc/apt/keyrings/charm.gpg") for c in joined))
        self.assertTrue(any(c.endswith("/etc/apt/sources.list.d/charm.list") for c in joined))
        self.assertEqual(self.calls[-1], ["sudo", "-n", "apt-get", "update"])

    def test_key_checksum_mismatch_runs_nothing_privileged(self):
        spec = dict(self.spec, key_sha256="0" * 64)
        with self.assertRaises(RecipeError):
            recipes.run_recipe(spec, self.ctx)
        self.assertFalse(any(c[:1] == ["sudo"] for c in self.calls))

    def test_already_configured_is_skipped(self):
        self.ctx.exists = lambda p: p == APT["source_file"]
        recipes.run_recipe(self.spec, self.ctx)
        self.assertEqual(self.calls, [])

    def test_running_as_root_has_no_sudo_prefix(self):
        self.ctx.sudo = []
        recipes.run_recipe(self.spec, self.ctx)
        self.assertEqual(self.calls[-1], ["apt-get", "update"])


class DnfCopr(Base):
    def test_enable_copr(self):
        recipes.run_recipe({"kind": "dnf-copr", "name": "sdegler/hyprland"}, self.ctx)
        self.assertEqual(self.calls, [["sudo", "-n", "dnf", "copr", "enable", "-y", "sdegler/hyprland"]])


class Execute(Base):
    def step(self, kind="packages"):
        s = model.Status(key="kitty", desc="terminal", required=True, state="missing",
                         source="distro", name="kitty")
        return model.build_plan([s], {"kitty"}, "debian")[0]

    def test_packages_step_runs_with_sudo(self):
        recipes.execute(self.step(), self.ctx)
        self.assertEqual(self.calls, [["sudo", "-n", "apt-get", "install", "-y", "kitty"]])

    def test_failure_carries_the_output_tail(self):
        self.ctx.runner = lambda argv, on_line=None: cp(100, "E: Unable to locate package kitty\n")
        with self.assertRaises(RecipeError) as cm:
            recipes.execute(self.step(), self.ctx)
        self.assertIn("Unable to locate", str(cm.exception))

    def test_expired_sudo_is_its_own_error(self):
        self.ctx.runner = lambda argv, on_line=None: cp(1, "sudo: a password is required\n")
        with self.assertRaises(SudoExpired):
            recipes.execute(self.step(), self.ctx)

    def test_declined_plan_never_executes_anything(self):
        # Review Focus 1: executing is only ever reached through screens.install; an
        # empty plan must be a no-op that never touches sudo.
        for step in model.build_plan([], set(), "debian"):
            recipes.execute(step, self.ctx)
        self.assertEqual(self.calls, [])


class DescribeStep(unittest.TestCase):
    def test_packages_step_shows_the_sudo_command(self):
        s = model.Status(key="kitty", desc="t", required=True, state="missing", source="distro", name="kitty")
        step = model.build_plan([s], {"kitty"}, "debian")[0]
        self.assertEqual(recipes.describe_step(step, "/h"), ["sudo apt-get install -y kitty"])

    def test_repo_step_uses_recipe_description(self):
        r = {"kind": "dnf-copr", "name": "a/b"}
        s = model.Status(key="x", desc="x", required=True, state="missing", source="distro",
                         name="x", repo=True, recipe=r)
        step = model.build_plan([s], {"x"}, "fedora")[0]
        self.assertEqual(recipes.describe_step(step, "/h"), ["dnf copr enable -y a/b"])


if __name__ == "__main__":
    unittest.main()
