import unittest

from installer import model
from installer.model import Status
from installer.tests.fakes import cp, make_env


def st(key, **kw):
    d = dict(key=key, desc=key, required=True, state="missing", source="distro", name=key)
    d.update(kw)
    return Status(**d)


class Plan(unittest.TestCase):
    def test_order_repos_then_packages_then_recipes(self):
        repo = {"kind": "apt-repo", "source_file": "/etc/apt/sources.list.d/c.list"}
        recipe = {"kind": "release-binary"}
        statuses = [
            st("matugen", source="recipe", name="", recipe=recipe),
            st("gum", required=False, repo=True, recipe=repo),
            st("kitty"),
            st("hyprland", flag="-t echo-backports"),
        ]
        steps = model.build_plan(statuses, {s.key for s in statuses}, "debian")
        self.assertEqual([s.kind for s in steps], ["repo", "packages", "packages", "packages", "recipe"])
        pk = [s for s in steps if s.kind == "packages"]
        self.assertEqual(pk[0].commands, [["apt-get", "install", "-y", "kitty"]])
        self.assertEqual(pk[1].commands, [["apt-get", "install", "-y", "-t", "echo-backports", "hyprland"]])
        self.assertEqual(pk[2].commands, [["apt-get", "install", "-y", "gum"]])  # optional last
        self.assertTrue(all(s.sudo for s in steps if s.kind in ("repo", "packages")))
        self.assertFalse(steps[-1].sudo)

    def test_only_selected_items(self):
        statuses = [st("a"), st("b")]
        steps = model.build_plan(statuses, {"a"}, "fedora")
        self.assertEqual(steps[0].commands, [["dnf", "install", "-y", "a"]])
        self.assertEqual(steps[0].items, ["a"])

    def test_repo_step_deduplicated(self):
        r = {"kind": "dnf-copr", "name": "x/y"}
        statuses = [st("a", repo=True, recipe=r), st("b", repo=True, recipe=r)]
        steps = model.build_plan(statuses, {"a", "b"}, "fedora")
        self.assertEqual([s.kind for s in steps].count("repo"), 1)

    def test_pacman_command(self):
        steps = model.build_plan([st("a")], {"a"}, "arch")
        self.assertEqual(steps[0].commands, [["pacman", "-S", "--needed", "--noconfirm", "a"]])

    def test_sim_names_exclude_items_that_need_a_repo(self):
        r = {"kind": "apt-repo", "source_file": "/x"}
        statuses = [st("kitty"), st("gum", repo=True, recipe=r)]
        steps = model.build_plan(statuses, {"kitty", "gum"}, "debian")
        pk = next(s for s in steps if s.kind == "packages")
        self.assertEqual(pk.sim_names, ["kitty"])


class Simulate(unittest.TestCase):
    def step(self, family="debian", flag=""):
        s = st("kitty", flag=flag)
        return model.build_plan([s], {"kitty"}, family)[0]

    def test_apt_ok_and_conflict(self):
        ok = make_env(outputs={"apt-get -s install kitty": cp(0, "Inst kitty\n")})
        self.assertEqual(model.simulate(self.step(), "debian", ok)[0], "ok")
        bad = make_env(outputs={"apt-get -s install kitty": cp(100, "E: Unable to correct problems\n")})
        status, text = model.simulate(self.step(), "debian", bad)
        self.assertEqual(status, "fail")
        self.assertIn("Unable to correct", text)

    def test_apt_uses_suite_flag(self):
        env = make_env(outputs={"apt-get -s install -t echo-backports kitty": cp(0, "ok")})
        self.assertEqual(model.simulate(self.step(flag="-t echo-backports"), "debian", env)[0], "ok")

    def test_dnf_assumeno_abort_counts_as_ok(self):
        env = make_env(outputs={"dnf install --assumeno kitty": cp(1, "Operation aborted by the user.\n")})
        self.assertEqual(model.simulate(self.step("fedora"), "fedora", env)[0], "ok")

    def test_nothing_to_simulate(self):
        step = model.Step(id="p", kind="packages", title_key="step.packages", title_args={},
                          commands=[], items=[], sudo=True, recipe=None, names=[], flag="", sim_names=[])
        self.assertEqual(model.simulate(step, "debian", make_env())[0], "skipped")


class Detect(unittest.TestCase):
    def test_known_hosts(self):
        env = make_env(outputs={"chezmoi data": cp(0, '{"hosts": {"desktop": {}, "pentest": {}}}')})
        self.assertEqual(model.known_hosts(env), ["desktop", "pentest"])
        self.assertEqual(model.known_hosts(make_env()), [])

    def test_detect_summary(self):
        env = make_env(outputs={
            "localectl status": cp(0, "   System Locale: LANG=en_US\n       X11 Layout: us,br\n"),
            "lspci": cp(0, "00:02.0 VGA compatible controller: Intel Corporation HD Graphics 520\n"),
        })
        d = model.detect_summary(env)
        self.assertEqual(d["kb"], "us,br")
        self.assertIn("Intel", d["gpu"])
        self.assertEqual(model.detect_summary(make_env()), {"kb": "", "gpu": ""})


if __name__ == "__main__":
    unittest.main()
