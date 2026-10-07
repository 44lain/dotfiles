"""The eight screens. Each takes (ui, state) and returns "next", "back", "cancel"
or an int (jump to that screen index). Screens 1-5 only read; nothing is written or
installed before the confirmation in screen 5 (packages) and screen 7 (configuration)."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from installer import messages, model, recipes, validate
from installer.ui import BACK, CANCEL, Item

TOTAL = 8
IDX = dict(welcome=0, profile=1, prefs=2, scan=3, plan=4, install=5, configure=6, verify=7)
MAX_REAUTH = 2
SESSION_ONLY = ("grootshell (qs) not running", "hypridle not running")


@dataclass
class State:
    family: str
    repo: Path
    home: str
    env: model.Env
    ctx: recipes.Ctx
    log_path: str
    lang: str = "en"
    profile: str = "guest"
    host: str = ""
    host_is_new: bool = True
    git_name: str = ""
    git_email: str = ""
    wall_dir: str = ""
    wall_image: str = ""
    statuses: list = field(default_factory=list)
    plan: list = field(default_factory=list)
    t: object = None

    def set_lang(self, lang):
        self.lang = messages.normalize(lang)
        self.t = messages.translator(self.lang)


def _nav(choice):
    return "back" if choice is BACK else "cancel"


def _vr(result: validate.Result, s: State):
    """Adapter: validation Result -> (ok, translated message) for ui.text."""
    return result.ok, s.t(result.code, **result.args)


def in_hyprland() -> bool:
    return os.environ.get("XDG_CURRENT_DESKTOP") == "Hyprland" or bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))


def classify_doctor(lines, in_hyprland: bool):
    out = []
    for line in lines:
        s = line.strip()
        if s.startswith("== "):
            out.append(("head", s))
        elif s.startswith("ok "):
            out.append(("ok", s[3:].strip()))
        elif s.startswith("WARN "):
            out.append(("warn", s[5:].strip()))
        elif s.startswith("FAIL "):
            msg = s[5:].strip()
            out.append(("info" if (not in_hyprland and msg in SESSION_ONLY) else "fail", msg))
        elif s:
            out.append(("note", s))
    return out


def _git(key, s: State) -> str:
    cp = s.env.run(["git", "config", "--get", key])
    return (cp.stdout or "").strip() if cp.returncode == 0 else ""


# ---- 1 ----------------------------------------------------------------------
def welcome(ui, s):
    t = s.t
    ui.title(1, TOTAL, t("welcome.title"))
    ui.info(t("welcome.intro"))
    hypr = ""
    if s.env.which("Hyprland"):
        hypr = model.installed_version("Hyprland", s.env)
    ui.info(t("welcome.detect", family=s.family, hyprland=hypr or t("welcome.none"),
              session=os.environ.get("XDG_CURRENT_DESKTOP") or t("welcome.none")))
    if s.family == "unknown":
        ui.warn(t("welcome.unknown_family"))
    c = ui.menu(t("welcome.menu"), [("go", t("welcome.go")), ("lang", t("welcome.switch"))])
    if c is BACK or c is CANCEL:
        return "cancel"
    if c == "lang":
        s.set_lang("pt_br" if s.lang == "en" else "en")
        return IDX["welcome"]
    return "next"


# ---- 2 ----------------------------------------------------------------------
def profile_host(ui, s):
    t = s.t
    ui.title(2, TOTAL, t("host.title"))
    ui.info(t("profile.explain"))
    c = ui.menu(t("profile.prompt"), [("guest", t("profile.guest")), ("personal", t("profile.personal"))],
                default=0 if s.profile == "guest" else 1)
    if c is BACK or c is CANCEL:
        return _nav(c)
    s.profile = c
    known = model.known_hosts(s.env)
    det = model.detect_summary(s.env)
    ui.info(t("host.detected", kb=det["kb"] or t("welcome.none"), gpu=det["gpu"] or t("welcome.none")))
    cur = model.current_host(s.env)
    keep = [("keep", t("host.keep", name=cur))] if cur and cur in model.local_hosts(s.env) else []
    if keep or (s.profile == "personal" and known):
        others = [(h, h) for h in known] if s.profile == "personal" else []
        c = ui.menu(t("host.prompt"), keep + [("new", t("host.new"))] + others)
        if c is BACK or c is CANCEL:
            return _nav(c)
        if c == "keep":
            s.host, s.host_is_new = cur, False
            return "next"
        if c != "new":
            s.host, s.host_is_new = c, False
            return "next"
    else:
        ui.info(t("host.guest_new"))
    default = s.host if (s.host and s.host_is_new) else re.sub(r"[^A-Za-z0-9_-]", "-", socket.gethostname().split(".")[0])
    v = ui.text(t("host.name"), default, lambda x: _vr(validate.check_host_name(x, known), s))
    if v is BACK or v is CANCEL:
        return _nav(v)
    s.host, s.host_is_new = v.strip(), True
    return "next"


# ---- 3 ----------------------------------------------------------------------
def preferences(ui, s):
    t = s.t
    ui.title(3, TOTAL, t("prefs.title"))
    ui.info(t("prefs.explain"))
    name = ui.text(t("prefs.git_name"), s.git_name or _git("user.name", s),
                   lambda x: _vr(validate.check_name(x), s))
    if name is BACK or name is CANCEL:
        return _nav(name)
    email = ui.text(t("prefs.git_email"), s.git_email or _git("user.email", s),
                    lambda x: _vr(validate.check_email(x), s))
    if email is BACK or email is CANCEL:
        return _nav(email)
    wall = ui.text(t("prefs.wall_dir"), s.wall_dir, lambda x: _vr(validate.check_wallpaper_dir(x, s.home), s))
    if wall is BACK or wall is CANCEL:
        return _nav(wall)
    s.git_name, s.git_email = name.strip(), email.strip()
    s.wall_dir = validate.check_wallpaper_dir(wall, s.home).value
    first = validate.first_image(s.wall_dir, s.home) if s.wall_dir else ""
    opts = ([("first", t("prefs.image_first", name=os.path.basename(first)))] if first else [])
    opts += [("pick", t("prefs.image_pick")), ("skip", t("prefs.image_skip"))]
    c = ui.menu(t("prefs.image_prompt"), opts)
    if c is BACK or c is CANCEL:
        return _nav(c)
    if c == "first":
        s.wall_image = first
    elif c == "skip":
        s.wall_image = ""
    else:
        v = ui.text(t("prefs.image_path"), "", lambda x: _vr(validate.check_wallpaper_image(x, s.home), s))
        if v is BACK or v is CANCEL:
            return _nav(v)
        s.wall_image = validate.check_wallpaper_image(v, s.home).value
    return "next"


# ---- 4 ----------------------------------------------------------------------
def scan_screen(ui, s):
    t = s.t
    ui.title(4, TOTAL, t("scan.title"))
    pk = model.load_packages(s.repo / ".chezmoidata" / "packages.toml")
    s.statuses = model.scan(pk, s.family, s.env)
    for st in s.statuses:
        if st.state == "no_source":
            ui.warn(t("scan.no_source", key=st.key,
                      detail=t("detail." + st.detail, info=st.info), manual=st.manual or "-"))
    rows = [[st.key, t("state." + st.state), t("source." + (st.source or "none")), st.desc] for st in s.statuses]
    if not model.actionable(s.statuses):
        ui.success(t("scan.nothing"))
        return IDX["configure"]
    r = ui.table([t("scan.col_item"), t("scan.col_state"), t("scan.col_source"), t("scan.col_desc")], rows)
    if r is BACK or r is CANCEL:
        return _nav(r)
    return "next"


# ---- 5 ----------------------------------------------------------------------
def plan_screen(ui, s):
    t = s.t
    ui.title(5, TOTAL, t("plan.title"))
    s.plan = []
    act = model.actionable(s.statuses)
    if not act:
        ui.info(t("plan.nothing_selected"))
        return IDX["configure"]
    items = [Item(a.key, f"{a.key} — {a.desc}", a.required) for a in act]
    picked = ui.checklist(t("plan.pick"), items)
    if picked is BACK or picked is CANCEL:
        return _nav(picked)
    dropped = [a.key for a in act if a.required and a.key not in picked]
    if not picked:
        if dropped:
            ui.warn(t("plan.required_unticked", items=", ".join(dropped)))
        ui.info(t("plan.nothing_selected"))
        return IDX["configure"]
    plan = model.build_plan(s.statuses, set(picked), s.family)
    failed = timed_out = False
    rows = []  # the whole plan is table rows: the user can scroll it (messages cannot be)
    for step in plan:
        rows.append(["• " + t(step.title_key, **step.title_args)])
        rows += [["    " + line] for line in recipes.describe_step(step, s.home)]
        status, text = model.simulate(step, s.family, s.env)
        if status == "ok":
            rows.append(["    ok   " + t("plan.sim_ok")])
        elif status == "fail":
            failed = True
            rows.append(["    FAIL " + t("plan.sim_fail")])
            rows += [["         " + line] for line in text.splitlines()]
        elif status == "timeout":
            timed_out = True
            rows.append(["    ...  " + t("plan.sim_timeout")])
        elif status == "unsynced":
            rows.append(["    ...  " + t("plan.sim_unsynced")])
        rows.append([""])
    r = ui.table([t("plan.title")], rows)
    if r is BACK or r is CANCEL:
        return _nav(r)
    ui.info(t("plan.summary", n=len(plan)))
    if failed:
        ui.warn(t("plan.sim_failed_warn"))
    if timed_out:
        ui.warn(t("plan.sim_timeout"))
    ui.warn(t("plan.no_revert"))
    if s.family == "arch" and any(st.kind == "packages" for st in plan):
        ui.warn(t("plan.arch_upgrades"))
    if dropped:
        ui.warn(t("plan.required_unticked", items=", ".join(dropped)))
    c = ui.confirm(t("plan.confirm"), default=False)
    if c is CANCEL:
        return "cancel"
    if c is BACK or not c:
        return "back"
    s.plan = plan
    return "next"


# ---- 6 ----------------------------------------------------------------------
def install_screen(ui, s):
    t = s.t
    ui.title(6, TOTAL, t("install.title"))
    if any(st.sudo for st in s.plan) and s.ctx.sudo:
        ui.info(t("install.sudo_prompt"))
        if ui.suspend(["sudo", "-v"]) != 0:
            ui.error(t("install.sudo_failed"))
            return "cancel"
    ok = skipped = failed = 0
    failed_titles = []
    for step in s.plan:
        title = t(step.title_key, **step.title_args)
        reauth = 0
        while True:
            old = s.ctx.log
            try:
                with ui.progress(title) as push:
                    s.ctx.log = push
                    recipes.execute(step, s.ctx)
                ui.success(t("install.step_ok", title=title))
                ok += 1
                break
            except (recipes.RecipeError, OSError) as e:
                if isinstance(e, recipes.SudoExpired) and reauth < MAX_REAUTH:
                    reauth += 1
                    if ui.suspend(["sudo", "-v"]) != 0:
                        ui.error(t("install.sudo_failed"))
                        s.plan = []
                        return "cancel"
                    continue
                ui.error(t("install.step_failed", title=title))
                ui.error(t("install.error", error=str(e)))
                c = ui.menu(t("install.menu"), [("retry", t("install.retry")), ("skip", t("install.skip")),
                                                 ("abort", t("install.abort"))], default=1)
                if c == "retry":
                    reauth = 0
                    continue
                if c == "skip":
                    failed += 1  # skipped AFTER a failure: it did not get installed
                    failed_titles.append(title)
                    break
                # abort, BACK and CANCEL all stop the installation
                ui.warn(t("install.aborted"))
                s.plan = []
                return "cancel"
            finally:
                s.ctx.log = old
    s.plan = []  # done: revisiting this screen must never re-run anything
    ui.info(t("install.summary", ok=ok, skipped=skipped, failed=failed))
    for title in failed_titles:
        ui.error(t("install.failed_item", title=title))
    ui.info(t("install.log", path=s.log_path))
    return "next"


# ---- 7 ----------------------------------------------------------------------
def _run(s, argv):
    """Run a command; an OS-level failure becomes a rc-127 result instead of an exception."""
    try:
        return s.ctx.run(argv)
    except OSError as e:
        return subprocess.CompletedProcess(argv, 127, str(e), "")


def _fail(ui, s, what, err):
    ui.error(s.t("configure.step_failed", what=what, error=err))


def _pin_profile_host(cfg, profile, host):
    """chezmoi init --promptDefaults writes the maintainer's defaults and
    --promptString does not reach promptStringOnce, so set the chosen values."""
    with open(cfg, encoding="utf-8") as f:
        text = f.read()
    # Keep the template's own spacing (`host    = ...`): rice-onboard later rewrites
    # these lines with a sed that matches that exact layout.
    for key, value in (("profile", profile), ("host", host)):
        text = re.sub(rf"(?m)^(\s*{key}\s*=\s*).*$", lambda m, v=value: f"{m.group(1)}{json.dumps(v)}",
                      text, count=1)
    with open(cfg, "w", encoding="utf-8") as f:
        f.write(text)


PREREQS = ("chezmoi", "git", "jq")  # what the configure step runs: rice-onboard hard-requires them
CHEZMOI_ONELINER = 'sh -c "$(curl -fsLS get.chezmoi.io)" -- -b ~/.local/bin'


def _prereq_install_lines(s, missing):
    """Exact commands that install `missing` for the detected family."""
    lines = []
    pkgs = [m for m in missing if m != "chezmoi"]
    if pkgs:
        try:
            lines.append(" ".join((["sudo"] if s.ctx.sudo else []) + model._install_cmd(s.family, "", pkgs)))
        except ValueError:
            lines.append(" ".join(pkgs))
    if "chezmoi" in missing:
        lines.append(CHEZMOI_ONELINER)
    return lines


def configure_screen(ui, s):
    t = s.t
    ui.title(7, TOTAL, t("configure.title"))
    missing = [b for b in PREREQS if not s.env.which(b)]
    if missing:
        ui.error(t("configure.prereq_missing", tools=", ".join(missing)))
        for line in _prereq_install_lines(s, missing):
            ui.error(t("configure.prereq_install", cmd=line))
        return IDX["scan"]
    ui.info(t("configure.explain"))
    bashrc = os.path.join(s.home, ".bashrc")
    loader = "no"
    needs_loader = False
    if os.path.exists(bashrc):
        try:
            with open(bashrc, encoding="utf-8", errors="replace") as f:
                needs_loader = ".bashrc.d" not in f.read()
        except OSError:
            needs_loader = False
    if needs_loader:
        c = ui.confirm(t("configure.loader"), default=True)
        if c is CANCEL:
            return "cancel"
        if c is BACK:
            return IDX["prefs"]
        loader = "yes" if c else "no"
    go = ui.confirm(t("configure.go"), default=False)
    if go is CANCEL:
        return "cancel"
    if go is BACK or not go:
        return IDX["prefs"]
    cfg = os.path.join(s.home, ".config", "chezmoi", "chezmoi.toml")
    if not os.path.exists(cfg):
        ui.info(t("configure.init"))
        cp = _run(s, ["chezmoi", "init", "--promptDefaults"])
        if cp.returncode != 0:
            _fail(ui, s, "chezmoi init", (cp.stdout or "").strip()[-300:])
            return IDX["prefs"]
        try:
            if os.path.exists(cfg):
                _pin_profile_host(cfg, s.profile, s.host)
        except OSError as e:
            _fail(ui, s, "chezmoi init", str(e))
            return IDX["prefs"]
    ui.info(t("configure.bin"))
    cp = _run(s, ["chezmoi", "apply", os.path.join(s.home, ".local", "bin")])
    if cp.returncode != 0:
        _fail(ui, s, "chezmoi apply ~/.local/bin", (cp.stdout or "").strip()[-300:])
        return IDX["prefs"]
    onboard = [os.path.join(s.home, ".local", "bin", "rice-onboard"),
               "--profile", s.profile, "--host", s.host,
               "--git-name", s.git_name, "--git-email", s.git_email,
               "--wallpaper-path", s.wall_image, "--accept-detected", "--bashrc-loader", loader]
    ui.info(t("configure.onboard"))
    rc = ui.suspend(onboard)
    if rc != 0:
        ui.error(t("configure.onboard_failed", rc=rc))
        return IDX["prefs"]
    if s.wall_dir:
        try:
            ui.success(t("configure.shell_json", path=validate.write_shell_json(s.wall_dir, s.home)))
        except (validate.ShellJsonInvalid, OSError) as e:
            ui.error(t("configure.shell_json_invalid", error=str(e)))
    ui.success(t("configure.done"))
    return "next"


# ---- 8 ----------------------------------------------------------------------
def verify_screen(ui, s):
    t = s.t
    ui.title(8, TOTAL, t("verify.title"))
    ui.info(t("verify.running"))
    rice = os.path.join(s.home, ".local", "bin", "rice")
    cp = _run(s, [rice, "doctor"])
    rows = []
    prefix = {"ok": "ok   ", "warn": "WARN ", "fail": "FAIL ", "info": "info ", "note": "note ", "head": ""}
    if cp.returncode == 127:
        ui.error(t("verify.doctor_missing", error=(cp.stdout or "command not found").strip()))
    else:
        fails = 0
        for kind, msg in classify_doctor((cp.stdout or "").splitlines(), in_hyprland()):
            fails += kind == "fail"
            if kind == "info":
                msg = t("verify.session_pending", msg=msg)
            rows.append([prefix[kind] + msg])
        ui.success(t("verify.summary_ok")) if not fails else ui.warn(t("verify.summary_fail", n=fails))
        rows.append([""])
    rows += [[t(k)] for k in ("verify.next", "verify.back_title", "verify.back_text",
                              "verify.stays_text", "verify.uninstall_text")]
    r = ui.table([t("verify.title")], rows)
    if r is BACK:
        return IDX["configure"]
    return "cancel" if r is CANCEL else "next"


SCREENS = [welcome, profile_host, preferences, scan_screen, plan_screen, install_screen, configure_screen, verify_screen]


def run_flow(ui, s: State) -> int:
    """0 = finished, 1 = cancelled."""
    i = 0
    while 0 <= i < len(SCREENS):
        r = SCREENS[i](ui, s)
        if r == "next":
            i += 1
        elif r == "back":
            i = max(0, i - 1)
        elif r == "cancel":
            ui.warn(s.t("flow.cancelled"))
            return 1
        else:
            i = r
    return 0
