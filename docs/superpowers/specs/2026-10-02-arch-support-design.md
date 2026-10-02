# Arch family support + a faster E2E matrix — design

Date: 2026-10-02 · Status: draft, awaiting review

## Intent

Someone on Arch, or on a distro that follows Arch's repositories (EndeavourOS,
CachyOS, Garuda), runs the same one-liner as on Fedora and Debian and ends with
the rice working. Arch moves from "Planned, not verified" to "Supported" in the
README, and that claim is backed by the same end-to-end proof the other two
families have.

At the same time, the E2E harness has to get cheap enough to run on all three
families in every fix loop. Today it is sequential: Debian alone took ~14 min.
Three families would take ~45 min, and a failure dumps up to 1,600 transcript
lines into the console.

| Said | Assumed (correct me) |
| ---- | -------------------- |
| Arch and derivatives | "Derivatives" = the ones on Arch's repositories (EndeavourOS, CachyOS, Garuda). Manjaro is detected (`ID_LIKE=arch`) but not promised: its repositories lag, and `rice doctor` already says when Hyprland is too old |
| Faster E2E, using fewer tokens and less time | Same scenarios, same assertions; only how they are run and reported changes |
| — | Artix (`ID_LIKE=arch`, no systemd) is **not supported**: the session relies on uwsm and systemd user units |
| — | Arch Linux ARM and AUR are out of scope (nothing in `packages.toml` needs AUR) |

## What already exists (no work needed)

- Every item has an `arch` name except `grootshell` (git-clone) and `font-rubik` (fonts recipe). Both fall back to their recipes, as they do on the other families.
- Family detection by `ID`/`ID_LIKE` in `install.sh`, `installer/model.py`, `rice-doctor` and `rice-onboard`.
- `install.sh` maps `python3` → `python` for pacman.
- `test/distro/packages.sh` resolves every Arch name in `archlinux:latest` (hard).
- `test/packages.sh` enforces "no AUR".

## Findings (probed in `archlinux:latest`, 2026-10-02)

1. **The sync database is empty.** `pacman -S jq` → `database file for 'core' does not exist … target not found`. This is the Arch twin of Debian's missing `apt-get update`. `install.sh` would die on a fresh image, and the installer's dry run (`pacman -Sp`) would report every package as "not found".
2. **A stale database is as bad as an empty one, and `-Sy` alone is not a fix.** On a real Arch the database exists but can be weeks old. Then `-S` fetches versions the mirrors have already dropped (404), and `-Sy pkg` is a partial upgrade, which Arch explicitly does not support. The only supported form is `pacman -Syu <pkgs>`.
3. **The installer can run without `install.sh` having synced anything.** `install.sh` installs prerequisites only when some are missing. Someone with python/git/curl/jq already present goes straight to the TUI with a stale database, so the fix cannot live only in `install.sh`.
4. **No Python in the image.** It has to be installed (`python`, which ships `curses` and `tomllib`). `install.sh` already handles this; the E2E proves it.
5. **`/root/.bashrc` does not exist** (only `/etc/skel/.bashrc`). Real users get it from skel. The E2E must start from that realistic state (copy skel), or the loader/uninstall assertions test nothing.
6. **The image strips locales and docs** (`NoExtract`). Our texts are our own Python strings, so this is not a problem. `C.UTF-8` is enough for curses, the same as on Debian.
7. **`sudo` is not in base.** A real Arch user without sudo gets `install.sh`'s existing "install sudo as root" message. Nothing new.
8. **`cachyos/cachyos` exists on Docker Hub.** It is a cheap way to catch derivative breakage as a *soft* (report-only) image in `packages.sh`.
9. **`hyprland-verify.sh` runs only on Debian.** Arch ships the **newest** Hyprland, so verifying `hyprland.lua` there is the earliest warning of a config-breaking Hyprland release, for every family.
10. **CI (`distro.yml` → `make distro-check`) has no Arch in `installer-flow.sh` or `guest-install.sh`.** Only package names are checked for Arch.
11. **`rice-doctor` prints `sudo pacman -S`**, and the README shows `sudo pacman -S chezmoi git`. Both become `-Syu --needed`.

## Design

### 1. One install form on Arch: `pacman -Syu --needed --noconfirm <pkgs>`

Used in `install.sh`, in `installer/model.py::_install_cmd`, in `rice-doctor`'s printed command (without `--noconfirm`), in `rice-onboard`'s hint and in the README.

- This removes the "empty vs stale database" distinction. One command, always correct, and the plan screen shows it before asking, as today.
- It also upgrades the system. On Arch that is the expected and supported behaviour. The plan screen says so in one line ("on Arch, installing also upgrades the system: pacman -Syu"), en + pt-BR, so it is never a surprise.
- `--noconfirm` with `-Syu` takes the default answer for replace/conflict prompts. Conflicts default to "no", so pacman aborts and the step fails with its output tail. That is the right outcome: the user resolves it by hand. A pacman lock (`db.lck`, a GUI updater running) also fails loudly with pacman's own message.

### 2. The dry run on Arch

`pacman -Sp` reads the *local* sync database. Three cases:

- **Database present:** run `pacman -Sp` as today and report ok or fail.
- **Database absent** (no `/var/lib/pacman/sync/core.db`): report `skipped`, with the reason "package database not synced yet; the install step syncs it (pacman -Syu)", instead of a false "not found". This is a new message key, en + pt-BR, with parity enforced by `test_parity.py`.
- **No fakeroot or temp-dbpath sync** (`checkupdates`-style). It would give a real dry run, but it adds a dependency and a code path for the one case where the install step syncs anyway. YAGNI.

### 3. Derivatives and exclusions

- Detection is unchanged (`ID_LIKE=arch`).
- `install.sh` and `rice-doctor` refuse `ID=artix` with one clear line ("Artix has no systemd; the session needs uwsm + systemd user units") instead of failing later in the session.
- `os-release` fixtures in `test/install-sh.sh` and the installer unit tests cover arch, endeavouros, cachyos, garuda, manjaro (detected as arch) and artix (refused).
- README: **Supported:** Arch, verified in containers. EndeavourOS, CachyOS and Garuda use the same repositories, are detected by `ID_LIKE`, and are not tested separately. **Not supported:** Artix. Manjaro: works if its repositories carry Hyprland 0.55+, and `rice doctor` tells you.

### 4. Tests per layer

| Layer | Change |
| --- | --- |
| unit (`installer/tests`) | `_install_cmd("arch")` → `-Syu --needed`; dry run `skipped` when `core.db` is absent; family fixtures for the derivatives; parity for the new keys |
| `test/install-sh.sh` | arch branch prints `-Syu --needed`, `python3`→`python`; artix refused |
| `distro-check` (CI) | add `archlinux:latest` to `installer-flow.sh`, `guest-install.sh` and `hyprland-verify.sh`; add `cachyos/cachyos:latest` **soft** to `packages.sh` |
| `e2e-check` | `arch` joins the matrix (§5); S3 raw asserts the arch failure signature (`database file … does not exist` / `target not found`) is gone |
| real machine | acceptance on a real Arch install, pending, like Parrot |

### 5. Faster, quieter E2E (all three families)

Measured on the 2026-10-01 Debian run (4 threads, 15 GB host): S1+S4 ≈ 6 min, S2 ≈ 4.5 min, S3 raw ≈ 0.5 min, S3 file ≈ 2.3 min, S3 pipe ≈ 1.5 min. All of it is sequential. Each of the five groups repeats the bootstrap (package-list refresh, python/git/curl/jq, chezmoi download). The log is 133 lines when everything passes, and a failure `cat`s the whole transcript.

Changes. Scenarios and assertions stay as they are:

1. **Cached base image per family.** S1, S2 and S4 need prerequisites, but do not test installing them; that is S3's job. A generated Dockerfile (`FROM <image>`, prep, chezmoi, `/etc/skel/.bashrc` → `/root`) is built once and tagged `rice-e2e-base:<family>-<sha256(image digest + prep)>`. It is rebuilt when the tag is missing, older than 3 days (Arch is rolling, and stale databases 404), or when `--rebuild` is given. `bootstrap()` then only copies the repo and runs `git init`. **S3 keeps the untouched image**, because a plain machine is the point of S3.
2. **No shared package-download cache.** This was considered and rejected. Cells of one family run at the same time. apt locks `/var/cache/apt/archives/lock` (a second container fails), dnf5 locks its cache, and two pacman processes can write the same `.part` file. With prerequisites baked into the base image, what is left to download per cell is small (one package in S1 and S2). S3 must download everything anyway, because a plain machine is the point. Old base tags of a family are removed when a new one is built, so disk use stays flat.
3. **Cells run in parallel.** Each `family × group` pair is a cell (5 groups × 3 families = 15 cells). They run under a `-j N` cap, default 3 on this 4-thread host. `-j 1` gives today's sequential behaviour if the pty timings turn flaky under load. Each cell writes `<cell>.out` and `<cell>.rc` and never prints to the console directly.
4. **Quiet by default, details on demand.** Results are one line per cell, `PASS arch S2  97s  31 checks`. A failed cell prints only its `E2E-CHECK FAIL` lines, the last 30 transcript lines and the transcript path. `-v` restores today's full proof output. Transcripts always go to `${XDG_CACHE_HOME:-~/.cache}/rice-e2e/last/` (overwritten per run), so `-k` is no longer needed. The final matrix and the exit code stay.
5. **`--failed`** re-runs only the cells that failed last time, read from `last/results`. In a fix loop you fix and then re-run one cell, not all fifteen.

Expected effect: about 10–15 min for all three families instead of about 45 sequential (the target, to be measured, not a promise). Console output is about 20 lines when everything passes, instead of about 400. A failure costs about 40 lines per failed cell instead of up to 1,600. When Claude runs it, it runs in the background and reads only the matrix, opening a transcript only for a failed cell.

The arch row of the matrix needs:

- prep `pacman -Syu --noconfirm --needed python git jq` (curl is in base);
- family command `pacman -Syu --needed --noconfirm`;
- loader `yes` (Arch's skel `.bashrc` does not read `~/.bashrc.d`).

## Out of scope

AUR or AUR helpers. Manjaro as a verified target. Artix. Arch Linux ARM. Installing chezmoi through pacman instead of get.chezmoi.io: chezmoi *is* in `extra`, and that would remove a `curl | sh`, but it changes S3's assertions and the Fedora/Debian symmetry, so it is a separate decision. Folding `installer-flow.sh` into the E2E (it is a subset of S1) waits until the E2E runs in CI.

## Acceptance

1. `make e2e-check` (all three families) passes every cell. The arch row covers S1–S4, and S3 starts from a stock `archlinux:latest`.
2. `make distro-check` is green with arch in installer-flow, guest-install and hyprland-verify; cachyos is reported (soft).
3. `make test` and the installer unit tests pass, including the new fixtures and the parity check.
4. The E2E's wall time and console line count are measured and written in the plan's final report. They are compared against this document's baseline (about 14 min for Debian alone, 133 lines).
5. README and `docs/dependencies.md` updated. Real-machine Arch acceptance is listed as pending.
