"""python3 -m installer [--plain] [--lang en|pt-BR] [--repo PATH]"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

from installer import messages, model, recipes, screens, ui


def parse_args(argv):
    p = argparse.ArgumentParser(prog="rice tui", description="Guided installer for the dotfiles rice.")
    p.add_argument("--plain", action="store_true", help="plain prompts instead of the full-screen interface")
    p.add_argument("--lang", help="en or pt-BR (default: from $LANG)")
    p.add_argument("--repo", help="the dotfiles checkout (default: the folder this package lives in)")
    return p.parse_args(argv)


def build_state(args, environ, home=None):
    home = home or os.path.expanduser("~")
    repo = Path(args.repo) if args.repo else Path(__file__).resolve().parents[1]
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = os.path.join(home, ".local", "state", "rice", f"install-{stamp}.log")
    env = model.Env(home=home)
    s = screens.State(family=model.os_family(), repo=repo, home=home, env=env,
                      ctx=recipes.default_ctx(home, log_path), log_path=log_path)
    s.set_lang(args.lang or messages.detect(environ))
    return s


def main(argv=None, stdin=None, env=None, home=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    environ = os.environ if env is None else env
    state = build_state(args, environ, home)
    pk = state.repo / ".chezmoidata" / "packages.toml"
    if not pk.is_file():
        print(f"rice tui: {pk} not found (is --repo the dotfiles checkout?)", file=sys.stderr)
        return 2
    interface = ui.make_ui(state.t, plain=args.plain, stdin=stdin)
    interrupted = False
    try:
        return screens.run_flow(interface, state)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        interface.close()  # always restore the terminal
    if interrupted:
        print("\nrice tui: interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
