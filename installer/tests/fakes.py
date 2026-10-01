"""Test doubles shared by the installer tests."""
import subprocess

from installer.model import Env


def cp(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


def make_env(which=(), outputs=None, exists=(), home="/home/t", machine="x86_64"):
    """Env whose `run` answers by command prefix: outputs = {"apt-cache madison foo": cp(...)}.
    Unknown commands return rc 127. Every call is recorded in env.calls."""
    outputs = outputs or {}
    calls = []

    def run(argv, **kw):
        calls.append(list(argv))
        line = " ".join(argv)
        for prefix, result in outputs.items():
            if line.startswith(prefix):
                return result
        return cp(127, "")

    env = Env(
        which=lambda b: "/usr/bin/" + b if b in which else None,
        run=run,
        exists=lambda p: p in exists,
        home=home,
        machine=lambda: machine,
    )
    env.calls = calls
    return env
