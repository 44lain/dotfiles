import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from installer import model, recipes, screens
from installer.messages import translator
from installer.recipes import Ctx
from installer.tests.fake_ui import FakeUI
from installer.tests.fakes import cp, make_env
from installer.ui import BACK, CANCEL

TOML = """
[packages.kitty]
desc = "terminal"
section = "Terminal & tools"
bin = "kitty"
required = true
fedora = "kitty"
debian = "kitty"
arch = "kitty"

[packages.rofi]
desc = "launcher"
section = "Terminal & tools"
bin = "rofi"
fedora = "rofi"
debian = "rofi"
arch = "rofi"
"""


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # independent of the ambient desktop session (the maintainer's machine runs Hyprland)
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        os.environ.pop("XDG_CURRENT_DESKTOP", None)
        self.tmp = Path(self._tmp.name)
        self.home = str(self.tmp / "home")
        (self.tmp / "repo/.chezmoidata").mkdir(parents=True)
        (self.tmp / "repo/.chezmoidata/packages.toml").write_text(TOML)
        os.makedirs(self.home)
        self.calls = []

    def state(self, env=None, runner=None, lang="en", family="debian"):
        env = env or make_env(home=self.home)
        ctx = Ctx(home=self.home, runner=runner or self.runner, sudo=["sudo", "-n"])
        s = screens.State(family=family, repo=self.tmp / "repo", home=self.home, env=env, ctx=ctx,
                          log_path=str(self.tmp / "install.log"))
        s.set_lang(lang)
        return s

    def runner(self, argv, on_line=None):
        self.calls.append(list(argv))
        return cp(0, "")


class ClassifyDoctor(unittest.TestCase):
    LINES = ["== services up ==", "  ok   hypridle running",
             "  FAIL grootshell (qs) not running", "  FAIL hypridle not running",
             "  WARN missing: age (age) — secrets", "  FAIL font missing: Rubik — see docs",
             "       sudo apt install x"]

    def test_session_only_failures_are_informational_outside_hyprland(self):
        out = dict((m, k) for k, m in screens.classify_doctor(self.LINES, in_hyprland=False))
        self.assertEqual(out["grootshell (qs) not running"], "info")
        self.assertEqual(out["hypridle not running"], "info")
        self.assertEqual(out["font missing: Rubik — see docs"], "fail")

    def test_inside_hyprland_they_stay_failures(self):
        out = dict((m, k) for k, m in screens.classify_doctor(self.LINES, in_hyprland=True))
        self.assertEqual(out["hypridle not running"], "fail")

    def test_kinds(self):
        kinds = [k for k, _ in screens.classify_doctor(self.LINES, in_hyprland=True)]
        self.assertEqual(kinds, ["head", "ok", "fail", "fail", "warn", "fail", "note"])


class Preferences(Base):
    def wall(self):
        d = Path(self.home, "Pictures/wp")
        d.mkdir(parents=True)
        (d / "a.jpg").write_bytes(b"x")
        return str(d)

    def test_collects_valid_answers(self):
        wall = self.wall()
        ui = FakeUI("Ana", "ana@example.com", wall, "first")
        s = self.state()
        self.assertEqual(screens.preferences(ui, s), "next")
        self.assertEqual((s.git_name, s.git_email, s.wall_dir), ("Ana", "ana@example.com", wall))
        self.assertEqual(s.wall_image, f"{wall}/a.jpg")

    def test_invalid_path_is_reported_through_the_validator(self):
        ui = FakeUI("Ana", "ana@example.com", "home/ana/wp", "skip")
        s = self.state()
        screens.preferences(ui, s)
        self.assertIn("False:", ui.text_of("validated"))
        self.assertIn("not an absolute path", ui.text_of("validated"))

    def test_back_and_cancel_propagate(self):
        self.assertEqual(screens.preferences(FakeUI(BACK), self.state()), "back")
        self.assertEqual(screens.preferences(FakeUI(CANCEL), self.state()), "cancel")


class ProfileHost(Base):
    def test_guest_gets_a_new_host_and_the_maintainers_hosts_are_not_offered(self):
        env = make_env(home=self.home, outputs={
            "chezmoi data": cp(0, '{"hosts": {"desktop": {}, "pentest": {}}}')})
        ui = FakeUI("guest", "parrot-laptop")
        s = self.state(env=env)
        self.assertEqual(screens.profile_host(ui, s), "next")
        self.assertEqual((s.profile, s.host, s.host_is_new), ("guest", "parrot-laptop", True))
        self.assertEqual([k for k, _ in ui.asked], ["menu", "text"])  # no host menu for guest

    def test_personal_can_pick_a_known_host(self):
        env = make_env(home=self.home, outputs={"chezmoi data": cp(0, '{"hosts": {"desktop": {}}}')})
        ui = FakeUI("personal", "desktop")
        s = self.state(env=env)
        screens.profile_host(ui, s)
        self.assertEqual((s.host, s.host_is_new), ("desktop", False))


class ProfileHostSecondRun(Base):
    def second_run(self, profile_answers):
        d = Path(self.home, ".config/chezmoi")
        d.mkdir(parents=True)
        (d / "chezmoi.toml").write_text('[data]\nhost = "box"\nprofile = "guest"\n[data.hosts.box]\nscale = 1\n')
        env = make_env(home=self.home, outputs={
            "chezmoi data": cp(0, '{"hosts": {"desktop": {}, "box": {}}}')})
        ui = FakeUI(*profile_answers)
        s = self.state(env=env)
        return ui, s

    def test_keep_current_host_is_offered_and_skips_the_name_prompt(self):
        ui, s = self.second_run(["guest", "keep"])
        self.assertEqual(screens.profile_host(ui, s), "next")
        self.assertEqual((s.host, s.host_is_new), ("box", False))
        self.assertEqual([k for k, _ in ui.asked], ["menu", "menu"])
        self.assertEqual(ui.last_options[0][0], "keep")
        self.assertIn("box", ui.last_options[0][1])

    def test_choosing_new_still_rejects_names_that_exist(self):
        ui, s = self.second_run(["guest", "new", "box"])
        screens.profile_host(ui, s)
        self.assertIn("already exists", ui.text_of("validated"))

    def test_first_run_has_no_keep_entry(self):
        env = make_env(home=self.home, outputs={"chezmoi data": cp(0, "{}")})
        ui = FakeUI("guest", "laptop")
        screens.profile_host(ui, self.state(env=env))
        self.assertEqual([k for k, _ in ui.asked], ["menu", "text"])


class Scan(Base):
    def test_a_no_source_item_shows_its_family_note_as_the_manual_text(self):
        (self.tmp / "repo/.chezmoidata/packages.toml").write_text(TOML + """
[packages.hypr]
desc = "compositor"
section = "x"
bin = "Hyprland"
fedora = "hypr"
debian = "hypr"
note_debian = "use the backports suite"
""")
        env = make_env(home=self.home, which={"kitty", "rofi"}, outputs={
            "apt-cache madison": cp(0, ""), "apt-cache policy": cp(0, "")})
        ui = FakeUI()
        screens.scan_screen(ui, self.state(env=env))
        self.assertIn("use the backports suite", ui.text_of("warn"))
        self.assertNotIn("Manual: -", ui.text_of("warn"))

    def test_nothing_to_do_jumps_to_configure(self):
        env = make_env(home=self.home, which={"kitty", "rofi"})
        ui = FakeUI()
        r = screens.scan_screen(ui, self.state(env=env))
        self.assertEqual(r, screens.IDX["configure"])

    def test_missing_continues_to_the_plan(self):
        env = make_env(home=self.home, which={"kitty"}, outputs={
            "apt-cache madison rofi": cp(0, " rofi | 1.7 | https://x stable/main amd64 Packages\n"),
            "apt-cache policy rofi": cp(0, "Candidate: 1.7\n")})
        ui = FakeUI("next")
        s = self.state(env=env)
        self.assertEqual(screens.scan_screen(ui, s), "next")
        self.assertEqual([x.key for x in model.actionable(s.statuses)], ["rofi"])


class Plan(Base):
    def prepared(self, env=None):
        env = env or make_env(home=self.home, which={"kitty"}, outputs={
            "apt-cache madison rofi": cp(0, " rofi | 1.7 | https://x stable/main amd64 Packages\n"),
            "apt-cache policy rofi": cp(0, "Candidate: 1.7\n"),
            "apt-get -s install rofi": cp(0, "Inst rofi\n")})
        s = self.state(env=env)
        s.statuses = model.scan(model.load_packages(s.repo / ".chezmoidata/packages.toml"), s.family, env)
        return s

    def test_declining_the_confirmation_installs_nothing(self):
        # Review Focus 1
        ui = FakeUI(["rofi"], "next", False)
        s = self.prepared()
        self.assertEqual(screens.plan_screen(ui, s), "back")
        self.assertEqual(self.calls, [])
        self.assertEqual(s.plan, [])

    def test_back_and_cancel_at_the_confirmation_install_nothing(self):
        for answer, expected in ((BACK, "back"), (CANCEL, "cancel")):
            self.calls.clear()
            s = self.prepared()
            self.assertEqual(screens.plan_screen(FakeUI(["rofi"], "next", answer), s), expected)
            self.assertEqual(self.calls, [])
            self.assertEqual(s.plan, [])

    def test_confirming_stores_the_plan_and_shows_exact_commands(self):
        ui = FakeUI(["rofi"], "next", True)
        s = self.prepared()
        self.assertEqual(screens.plan_screen(ui, s), "next")
        self.assertEqual(len(s.plan), 1)
        self.assertIn("sudo apt-get install -y rofi", " ".join(ui.table_lines()))
        self.assertIn("NOT removed", ui.text_of("warn"))

    def test_the_whole_plan_is_scrollable_rows_shown_before_the_confirmation(self):
        # at 80x24 messages are cut to the last rows: the plan must be table rows
        ui = FakeUI(["rofi"], "next", True)
        screens.plan_screen(ui, self.prepared())
        self.assertEqual([k for k, _ in ui.asked], ["checklist", "table", "confirm"])
        self.assertIn("sudo apt-get install -y rofi", [x.strip() for x in ui.table_lines()])  # exact line, own row
        self.assertTrue(any("Dry run passed" in x for x in ui.table_lines()))
        self.assertNotIn("sudo apt-get install -y rofi", ui.text_of("info"))
        order = [k for k, _ in ui.events if k in ("table", "warn")]
        self.assertEqual(order[0], "table")  # warnings and summary come after the rows

    def test_back_and_cancel_at_the_plan_table_install_nothing(self):
        for answer, expected in ((BACK, "back"), (CANCEL, "cancel")):
            ui = FakeUI(["rofi"], answer)
            s = self.prepared()
            self.assertEqual(screens.plan_screen(ui, s), expected)
            self.assertEqual(s.plan, [])
            self.assertNotIn("confirm", [k for k, _ in ui.asked])

    def test_a_failed_simulation_is_shown_before_the_confirmation(self):
        env = make_env(home=self.home, which={"kitty"}, outputs={
            "apt-cache madison rofi": cp(0, " rofi | 1.7 | https://x stable/main amd64 Packages\n"),
            "apt-cache policy rofi": cp(0, "Candidate: 1.7\n"),
            "apt-get -s install rofi": cp(100, "E: Unable to correct problems\n")})
        ui = FakeUI(["rofi"], "next", False)
        screens.plan_screen(ui, self.prepared(env))
        self.assertIn("Unable to correct problems", " ".join(ui.table_lines()))
        self.assertIn("probably fail", ui.text_of("warn"))

    def test_a_dry_run_timeout_is_a_neutral_warning_not_an_error(self):
        env = make_env(home=self.home, which={"kitty"}, outputs={
            "apt-cache madison rofi": cp(0, " rofi | 1.7 | https://x stable/main amd64 Packages\n"),
            "apt-cache policy rofi": cp(0, "Candidate: 1.7\n"),
            "apt-get -s install rofi": cp(127, "", "timeout")})
        ui = FakeUI(["rofi"], "next", True)
        self.assertEqual(screens.plan_screen(ui, self.prepared(env)), "next")
        self.assertIn("could not finish in time", ui.text_of("warn"))
        self.assertNotIn("probably fail", ui.text_of("warn"))
        self.assertEqual(ui.text_of("error"), "")

    def test_required_items_are_preselected(self):
        ui = FakeUI(CANCEL)
        screens.plan_screen(ui, self.prepared())
        self.assertEqual({i.key: i.checked for i in ui.last_items}, {"rofi": False})


class Install(Base):
    def planned(self, runner):
        env = make_env(home=self.home, which={"kitty"}, outputs={
            "apt-cache madison rofi": cp(0, " rofi | 1.7 | https://x stable/main amd64 Packages\n"),
            "apt-cache policy rofi": cp(0, "Candidate: 1.7\n")})
        s = self.state(env=env, runner=runner)
        sts = model.scan(model.load_packages(s.repo / ".chezmoidata/packages.toml"), s.family, env)
        s.plan = model.build_plan(sts, {"rofi"}, s.family)
        return s

    def test_runs_every_step_and_summarises(self):
        s = self.planned(self.runner)
        ui = FakeUI()
        self.assertEqual(screens.install_screen(ui, s), "next")
        self.assertIn(["sudo", "-n", "apt-get", "install", "-y", "rofi"], self.calls)
        self.assertIn("Installed: 1", ui.text_of("info") + ui.text_of("success"))
        self.assertIn(["sudo", "-v"], ui.suspended)

    def test_a_step_skipped_after_a_failure_counts_as_failed_and_is_listed(self):
        bad = lambda argv, on_line=None: cp(100, "E: boom\n")
        ui = FakeUI("skip")
        self.assertEqual(screens.install_screen(ui, self.planned(bad)), "next")
        summary = ui.text_of("info")
        self.assertIn("Installed: 0 · skipped: 0 · failed: 1", summary)
        self.assertIn("Install 1 package(s)", ui.text_of("error").split("Failed step")[-1])

    def test_failure_offers_retry_skip_abort(self):
        # Review Focus 5: a failing step never produces a traceback
        outcomes = [cp(100, "E: network is unreachable\n"), cp(0, "")]
        s = self.planned(lambda argv, on_line=None: outcomes.pop(0))
        ui = FakeUI("retry")
        self.assertEqual(screens.install_screen(ui, s), "next")
        self.assertIn("network is unreachable", ui.text_of("error"))
        self.assertEqual(outcomes, [])

    def test_skip_continues_and_abort_stops(self):
        bad = lambda argv, on_line=None: cp(100, "E: boom\n")
        self.assertEqual(screens.install_screen(FakeUI("skip"), self.planned(bad)), "next")
        ui = FakeUI("abort")
        self.assertEqual(screens.install_screen(ui, self.planned(bad)), "cancel")
        self.assertIn("rice tui again", ui.text_of("warn") + ui.text_of("info"))

    def test_expired_sudo_reauthenticates_and_retries(self):
        outcomes = [cp(1, "sudo: a password is required\n"), cp(0, "")]
        s = self.planned(lambda argv, on_line=None: outcomes.pop(0))
        ui = FakeUI()
        screens.install_screen(ui, s)
        self.assertEqual(ui.suspended.count(["sudo", "-v"]), 2)

    def test_refusing_sudo_installs_nothing(self):
        s = self.planned(self.runner)
        ui = FakeUI()
        ui.suspend_rc = 1
        self.assertEqual(screens.install_screen(ui, s), "cancel")
        self.assertEqual(self.calls, [])

    def test_a_second_visit_executes_nothing(self):
        s = self.planned(self.runner)
        screens.install_screen(FakeUI(), s)
        self.assertEqual(s.plan, [])
        self.calls.clear()
        ui = FakeUI()
        self.assertEqual(screens.install_screen(ui, s), "next")
        self.assertEqual(self.calls, [])
        self.assertEqual(ui.suspended, [])

    def test_ctx_log_is_restored_after_the_installation(self):
        s = self.planned(self.runner)
        original = lambda line: None  # noqa: E731
        s.ctx.log = original
        screens.install_screen(FakeUI(), s)
        self.assertIs(s.ctx.log, original)

    def test_ctx_log_is_restored_when_a_step_fails(self):
        s = self.planned(lambda argv, on_line=None: cp(100, "E: boom\n"))
        original = lambda line: None  # noqa: E731
        s.ctx.log = original
        screens.install_screen(FakeUI("abort"), s)
        self.assertIs(s.ctx.log, original)

    def test_sudo_reauthentication_is_bounded(self):
        n = []

        def runner(argv, on_line=None):
            n.append(1)
            if len(n) > 50:
                raise AssertionError("unbounded sudo re-authentication")
            return cp(1, "sudo: a password is required\n")

        s = self.planned(runner)
        ui = FakeUI("skip")
        self.assertEqual(screens.install_screen(ui, s), "next")
        self.assertLessEqual(ui.suspended.count(["sudo", "-v"]), 3)
        self.assertIn("password is required", ui.text_of("error"))

    def test_root_needs_no_sudo_prompt(self):
        s = self.planned(self.runner)
        s.ctx.sudo = []
        ui = FakeUI()
        screens.install_screen(ui, s)
        self.assertEqual(ui.suspended, [])


class Configure(Base):
    def ready(self, **kw):
        s = self.state()
        s.profile, s.host, s.host_is_new = "guest", "parrot", True
        s.git_name, s.git_email = "Ana", "ana@example.com"
        s.wall_dir, s.wall_image = kw.get("wall_dir", ""), kw.get("wall_image", "")
        return s

    def test_runs_init_bin_then_onboard_with_flags(self):
        Path(self.home, ".bashrc").write_text("# stock\n")
        s = self.ready(wall_dir=str(self.tmp), wall_image="")
        ui = FakeUI(True, True)  # loader? yes; apply now? yes
        self.assertEqual(screens.configure_screen(ui, s), "next")
        flat = [" ".join(c) for c in self.calls]
        self.assertTrue(any(c.startswith("chezmoi init --promptDefaults") for c in flat))
        self.assertTrue(any(c.startswith("chezmoi apply") and c.endswith(".local/bin") for c in flat))
        onboard = ui.suspended[0]
        self.assertTrue(onboard[0].endswith("rice-onboard"))
        for pair in (["--profile", "guest"], ["--host", "parrot"], ["--git-name", "Ana"],
                     ["--git-email", "ana@example.com"], ["--bashrc-loader", "yes"]):
            i = onboard.index(pair[0])
            self.assertEqual(onboard[i + 1], pair[1])
        self.assertIn("--accept-detected", onboard)
        shell = json.loads(Path(self.home, ".config/grootshell/shell.json").read_text())
        self.assertEqual(shell["wallpaper"]["directory"], str(self.tmp))

    def test_init_does_not_leave_the_maintainers_defaults_behind(self):
        # chezmoi's --promptString has no effect on promptStringOnce (checked with
        # chezmoi 2.70), so the chosen profile/host are written right after init.
        cfg = Path(self.home, ".config/chezmoi/chezmoi.toml")

        def runner(argv, on_line=None):
            self.calls.append(list(argv))
            if argv[:2] == ["chezmoi", "init"]:
                cfg.parent.mkdir(parents=True, exist_ok=True)
                cfg.write_text('[data]\n    profile = "guest"\n    host    = "desktop"\n    wallpaper_path = ""\n')
            return cp(0, "")
        s = self.state(runner=runner)
        s.profile, s.host, s.git_name, s.git_email = "personal", "parrot", "Ana", "ana@example.com"
        self.assertEqual(screens.configure_screen(FakeUI(True), s), "next")
        self.assertIn(["chezmoi", "init", "--promptDefaults"], self.calls)
        text = cfg.read_text()
        # the template's spacing is kept: rice-onboard's later sed matches `^    host    = `
        self.assertIn('\n    profile = "personal"\n', text)
        self.assertIn('\n    host    = "parrot"\n', text)
        self.assertNotIn("desktop", text)
        self.assertIn('wallpaper_path = ""', text)

    def test_pinned_host_can_still_be_changed_by_rice_onboards_sed(self):
        # Regression: the pin used to rewrite `host    =` as `host =`, so onboard's
        # `sed "s/^    host    = .*/…/"` never matched again on a re-run with a new host.
        import subprocess
        cfg = Path(self.home, ".config/chezmoi/chezmoi.toml")
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text('[data]\n    profile = "guest"\n    host    = "desktop"\n')
        screens._pin_profile_host(str(cfg), "guest", "parrot")
        subprocess.run(["sed", "-i", 's/^    host    = .*/    host    = "laptop"/', str(cfg)], check=True)
        subprocess.run(["sed", "-i", 's/^    profile = .*/    profile = "personal"/', str(cfg)], check=True)
        text = cfg.read_text()
        self.assertIn('    host    = "laptop"', text)
        self.assertIn('    profile = "personal"', text)
        self.assertNotIn("parrot", text)

    def test_pin_handles_a_file_without_the_keys_and_odd_spacing(self):
        cfg = Path(self.home, "c.toml")
        cfg.write_text('[data]\n  profile="guest"\n  host\t=\t"desktop"\n')
        screens._pin_profile_host(str(cfg), "personal", "x")
        text = cfg.read_text()
        self.assertIn('  profile="personal"', text)
        self.assertIn('  host\t=\t"x"', text)
        cfg.write_text('[data]\n')
        screens._pin_profile_host(str(cfg), "guest", "x")
        self.assertEqual(cfg.read_text(), '[data]\n')

    def test_declining_applies_nothing(self):
        s = self.ready()
        ui = FakeUI(False, False)
        self.assertEqual(screens.configure_screen(ui, s), screens.IDX["prefs"])
        self.assertEqual(self.calls, [])
        self.assertEqual(ui.suspended, [])

    def test_back_and_cancel_at_the_confirmations(self):
        for answers, expected in (((BACK,), screens.IDX["prefs"]), ((CANCEL,), "cancel")):
            s = self.ready()  # no ~/.bashrc: only the "apply now?" confirm is asked
            ui = FakeUI(*answers)
            self.assertEqual(screens.configure_screen(ui, s), expected)
            self.assertEqual(self.calls, [])
            self.assertEqual(ui.suspended, [])
        Path(self.home, ".bashrc").write_text("# stock\n")
        for answers, expected in (((BACK,), screens.IDX["prefs"]), ((CANCEL,), "cancel")):
            ui = FakeUI(*answers)  # the loader confirm comes first
            self.assertEqual(screens.configure_screen(ui, self.ready()), expected)
            self.assertEqual(self.calls, [])

    def test_a_failing_chezmoi_apply_returns_to_preferences(self):
        def runner(argv, on_line=None):
            self.calls.append(list(argv))
            return cp(1, "boom") if argv[:2] == ["chezmoi", "apply"] else cp(0, "")
        s = self.state(runner=runner)
        s.profile, s.host, s.git_name, s.git_email = "guest", "parrot", "Ana", "ana@example.com"
        ui = FakeUI(True)
        self.assertEqual(screens.configure_screen(ui, s), screens.IDX["prefs"])
        self.assertEqual(ui.suspended, [])
        self.assertFalse(any(c[0] == "apt-get" or c[:2] == ["sudo", "-n"] for c in self.calls))

    def test_a_failing_onboard_returns_to_preferences(self):
        s = self.ready()
        ui = FakeUI(True)
        ui.suspend_rc = 3
        self.assertEqual(screens.configure_screen(ui, s), screens.IDX["prefs"])

    def test_invalid_shell_json_is_reported_and_left_alone(self):
        p = Path(self.home, ".config/grootshell/shell.json")
        p.parent.mkdir(parents=True)
        p.write_text("{ nope")
        s = self.ready(wall_dir=str(self.tmp))
        ui = FakeUI(True, True)
        screens.configure_screen(ui, s)
        self.assertEqual(p.read_text(), "{ nope")
        self.assertIn("left untouched", ui.text_of("error"))


class Verify(Base):
    def test_shows_doctor_results_and_the_way_back(self):
        doctor = "== services up ==\n  FAIL hypridle not running\n  ok   fonts\n"
        s = self.state(runner=lambda argv, on_line=None: cp(1, doctor))
        os.makedirs(os.path.join(self.home, ".local/bin"))
        Path(self.home, ".local/bin/rice").write_text("#!/bin/sh\n")
        ui = FakeUI("next")
        self.assertEqual(screens.verify_screen(ui, s), "next")
        rows = ui.table_lines()
        self.assertEqual(len(ui.tables), 1)  # one scrollable table holds everything
        self.assertIn("ok   fonts", rows)
        self.assertTrue(any(r.startswith("info ") and "starts with the Hyprland session" in r for r in rows))
        self.assertTrue(any("How to go back" in r for r in rows))
        self.assertTrue(any("rice uninstall" in r for r in rows))
        self.assertTrue(any("Stays installed" in r for r in rows))

    def test_doctor_failures_are_rows_of_the_table_with_a_kind_prefix(self):
        doctor = "== fonts ==\n  FAIL font missing: Rubik\n  WARN missing: age\n       sudo apt install x\n"
        s = self.state(runner=lambda argv, on_line=None: cp(1, doctor))
        ui = FakeUI("next")
        screens.verify_screen(ui, s)
        rows = ui.table_lines()
        self.assertIn("== fonts ==", rows)
        self.assertIn("FAIL font missing: Rubik", rows)
        self.assertIn("WARN missing: age", rows)
        self.assertIn("note sudo apt install x", rows)
        self.assertIn("1 check(s) failed", ui.text_of("warn"))

    def test_back_from_the_final_table_goes_to_configure(self):
        s = self.state(runner=lambda argv, on_line=None: cp(0, "  ok   fonts\n"))
        self.assertEqual(screens.verify_screen(FakeUI(BACK), s), screens.IDX["configure"])
        self.assertEqual(screens.verify_screen(FakeUI(CANCEL), s), "cancel")

    def test_missing_doctor_is_a_message_not_a_crash(self):
        s = self.state(runner=lambda argv, on_line=None: cp(127, "command not found"))
        ui = FakeUI()
        screens.verify_screen(ui, s)
        self.assertIn("could not be run", ui.text_of("error"))


class Flow(Base):
    def test_cancel_at_the_first_screen(self):
        ui = FakeUI(CANCEL)
        self.assertEqual(screens.run_flow(ui, self.state()), 1)
        self.assertIn("Stopped", ui.text_of("warn"))

    def test_declining_configure_when_nothing_is_missing_ends_in_preferences(self):
        env = make_env(home=self.home, which={"kitty", "rofi"})
        # welcome, profile, host name, git name, e-mail, wallpaper dir, image, configure? no
        ui = FakeUI("go", "guest", "box", "Ana", "ana@example.com", "", "skip", False)
        self.assertEqual(screens.run_flow(ui, self.state(env=env)), 1)
        kinds = [k for k, _ in ui.asked]
        self.assertEqual(kinds, ["menu", "menu", "text", "text", "text", "text", "menu", "confirm", "text"])
        self.assertEqual(self.calls, [])

    def test_language_switch_redraws_in_portuguese(self):
        ui = FakeUI("lang", CANCEL)
        s = self.state()
        screens.run_flow(ui, s)
        self.assertEqual(s.lang, "pt_br")
        self.assertIn("Boas-vindas", ui.text_of("title"))


if __name__ == "__main__":
    unittest.main()
