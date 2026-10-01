import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from installer import model

REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("chezmoi") and shutil.which("jq"), "doctor needs chezmoi and jq")
class DoctorParity(unittest.TestCase):
    def test_same_missing_binaries(self):
        pk = [p for p in model.load_packages(REPO / ".chezmoidata/packages.toml") if p.bin]
        # An empty PATH directory + a few fake tools: everything else is "missing" for both.
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            for tool in ("chezmoi", "jq", "bash", "env", "sort", "head", "tail", "awk", "sed",
                         "grep", "find", "cat", "dirname", "pgrep", "printf", "uname"):
                real = shutil.which(tool)
                if real:
                    (bindir / tool).symlink_to(real)
            for present in ("kitty", "rofi"):
                f = bindir / present
                f.write_text("#!/bin/sh\nexit 0\n")
                f.chmod(f.stat().st_mode | stat.S_IEXEC)
            osr = Path(tmp) / "os-release"
            osr.write_text("ID=fedora\n")
            # Setup chezmoi config with sourceDir pointing to REPO
            chezmoi_config_dir = Path(tmp) / ".config" / "chezmoi"
            chezmoi_config_dir.mkdir(parents=True)
            chezmoi_toml = chezmoi_config_dir / "chezmoi.toml"
            chezmoi_toml.write_text(f'sourceDir = "{REPO}"\n[data]\nprofile = "guest"\nhost = "desktop"\n')
            env = dict(os.environ, PATH=str(bindir), RICE_OS_RELEASE=str(osr), HOME=tmp)
            out = subprocess.run(
                [shutil.which("bash"), str(REPO / "dot_local/bin/executable_rice-doctor")],
                capture_output=True, text=True, env=env, cwd=REPO).stdout
            # Extract missing binaries from doctor output
            # Look for lines with "missing" and extract binary name from patterns like:
            # "FAIL missing (required): key (bin)" or "WARN missing: key (bin)"
            doctor_missing = set()
            import re as regex_module
            for line in out.splitlines():
                if "missing" in line and "(" in line:
                    # Extract binary name: look for pattern (bin) before the em-dash or end of line
                    # Format: "... key (bin) — desc" or similar
                    # We need the LAST parenthesized word before — or end of meaningful content
                    match = regex_module.search(r'\(([^)]+)\)\s*(?:—|$)', line)
                    if match:
                        content = match.group(1)
                        # The binary name should be a single word or hyphenated word, not a sentence
                        # Skip if it contains spaces (which indicates it's part of description)
                        if ' ' not in content and content not in ('required', 'optional'):
                            doctor_missing.add(content)
            e = model.Env(which=lambda b: str(bindir / b) if (bindir / b).exists() else None,
                          run=model._default_run, exists=os.path.exists, home=tmp)
            py_missing = {p.bin for p in pk if e.which(p.bin) is None}
            self.assertEqual(doctor_missing, py_missing)


if __name__ == "__main__":
    unittest.main()
