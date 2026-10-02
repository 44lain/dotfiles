#!/usr/bin/env bash
# The guided installer, END TO END, from a stranger's first keystroke to the last
# screen, inside throw-away containers (nothing touches the host's HOME).
#   S1  real install in PlainUI: one real package (fzf) is installed, a second run resumes
#   S2  the real CursesUI in a 30x100 xterm pty: whole walk with key presses, back, Ctrl-C, ESC
#   S3  install.sh the way a stranger runs it (no git/curl/python3/chezmoi yet), through a tty
#   S4  robustness: closed stdin, `rice` without a tty, `rice tui`, onboard re-run, uninstall
# Usage: installer-e2e.sh [-s S1,S2,S3,S4] [-d debian,fedora] [-k]   (-k keeps the transcripts)
# Needs docker + network (apt/dnf downloads, get.chezmoi.io); slow (minutes), so it is NOT part of
# `make test` or `make distro-check`: run it with `make e2e-check`.
# The pty driver (e2e_driver.py) has its own VT100 emulator and uses only the Python stdlib.
set -uo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
want_s=S1,S2,S3,S4 want_d=debian,fedora keep=0
while getopts 's:d:k' o; do
	case $o in s) want_s=$OPTARG ;; d) want_d=$OPTARG ;; k) keep=1 ;; *) exit 2 ;; esac
done
if ! command -v docker >/dev/null 2>&1; then
	echo "docker not found — skipped"
	[ "${CI:-}" = true ] && { echo "FAIL: CI must not skip the installer e2e test"; exit 1; }
	exit 0
fi

tmp=$(mktemp -d)
# shellcheck disable=SC2329 # invoked by the EXIT trap
cleanup() {
	docker ps -aq --filter "name=rice-e2e-$$-" | xargs -r docker rm -f >/dev/null 2>&1
	if [ "$keep" -eq 1 ]; then echo "transcripts kept in $tmp"; else rm -rf "${tmp:?}"; fi
}
trap cleanup EXIT
cp "$(dirname "$0")/e2e_driver.py" "$tmp/"

# ---- what runs INSIDE the container -------------------------------------------------
# lib.sh: helpers and the stranger's bootstrap (prerequisites, chezmoi, the repo where chezmoi expects it)
cat > "$tmp/lib.sh" <<'LIB'
set -u
check() { if [ "$1" = ok ]; then printf 'E2E-CHECK ok %s\n' "$2"; else printf 'E2E-CHECK FAIL %s\n' "$2"; fi; }
ck() { local name=$1; shift; if "$@"; then check ok "$name"; else check FAIL "$name"; fi; }
bootstrap() {
	eval "$PREP" || { check FAIL "prerequisites installed"; exit 1; }
	sh -c "$(curl -fsLS get.chezmoi.io)" -- -b ~/.local/bin >/dev/null || { check FAIL "chezmoi installed (network?)"; exit 1; }
	export PATH="$HOME/.local/bin:$PATH"
	# cp -r (not -a): files must belong to root or git refuses; .git is recreated
	# because a worktree's .git is a pointer to a host path
	mkdir -p ~/.local/share
	cp -r /repo ~/.local/share/chezmoi
	cd ~/.local/share/chezmoi || exit 1
	rm -rf .git; git init -q; git add -A
	git -c user.name=ci -c user.email=ci@example.com commit -qm source
	cd / || exit 1
	echo "machine: $(. /etc/os-release; echo "$PRETTY_NAME") | $(python3 --version 2>&1) | $(chezmoi --version | head -1)"
	ck "python3 has curses and tomllib" python3 -c 'import curses, tomllib'
}
LIB

# s1s4.sh: S1 (real install in PlainUI, twice) then S4 on the machine S1 left behind
cat > "$tmp/s1s4.sh" <<'S1'
. /rice/lib.sh
bootstrap
export PATH="$HOME/.local/bin:$PATH"
SRC=~/.local/share/chezmoi

feed() {  # feed <answers file> <transcript>: each "prompt|answer" is sent once that prompt (nth time) is on the transcript
	declare -A seen=()
	while IFS='|' read -r prompt answer; do
		[ -n "$prompt" ] || continue
		seen[$prompt]=$(( ${seen[$prompt]:-0} + 1 ))
		for _ in $(seq 1 900); do
			[ "$(grep -cF -- "$prompt" "$2")" -ge "${seen[$prompt]}" ] && break
			sleep 0.1
		done
		[ "$(grep -cF -- "$prompt" "$2")" -ge "${seen[$prompt]}" ] || return 0
		sleep 0.3
		if [ "$answer" = @pick ]; then   # the checklist number of the package, read from the transcript
			answer=$(grep -E "^  [0-9]+\) \[ \] $PKG — " "$2" | tail -1 | sed -E 's/^  ([0-9]+)\).*/\1/')
		fi
		printf '%s\n' "$answer"
	done < "$1"
}
run_flow() {  # run_flow <answers> <transcript>
	: > "$2"
	( cd "$SRC" && feed "$1" "$2" | python3 -u -m installer --plain --lang en > "$2" 2>&1 )  # status = python's
}
line_of() { grep -nE -- "$1" "$2" | head -1 | cut -d: -f1; }

echo "=== S4a: python3 -m installer --plain with stdin closed / empty"
for how in devnull closed; do
	if [ "$how" = devnull ]; then ( cd "$SRC" && python3 -m installer --plain --lang en < /dev/null > /tmp/a-$how 2>&1 ); rc=$?
	else ( cd "$SRC" && python3 -m installer --plain --lang en <&- > /tmp/a-$how 2>&1 ); rc=$?; fi
	sed 's/^/    | /' /tmp/a-$how | tail -8
	ck "S4a ($how): exit code 1" test "$rc" -eq 1
	ck "S4a ($how): says Stopped" grep -q 'Stopped' /tmp/a-$how
	ck "S4a ($how): no traceback" bash -c "! grep -q Traceback /tmp/a-$how"
done

echo "=== S4b: rice with no args and no tty"
# rice is not installed yet (first apply is later): run it from the source tree
bash "$SRC/dot_local/bin/executable_rice" < /dev/null > /tmp/b.out 2>&1; rc=$?
head -3 /tmp/b.out | sed 's/^/    | /'
ck "S4b: usage printed, exit 2" bash -c "test $rc -eq 2 && grep -q '^usage: rice' /tmp/b.out"

echo "=== S1: real install of $PKG in PlainUI"
command -v "$PKG" >/dev/null && check FAIL "S1: $PKG is absent before the flow" || check ok "S1: $PKG is absent before the flow"
if [ "$LOADER" = yes ]; then loader='Add the loader?|y
'; else loader=''; fi
cat > /tmp/answers1 <<EOF
What now?|1
(recommended)|1
Name for this machine|ci-box
Git name for this machine|CI Bot
Git e-mail for this machine|ci@example.com
Wallpaper folder (empty|
Lock-screen image|2
numbers toggle|n
numbers toggle|@pick
numbers toggle|
Run this plan now?|y
${loader}Apply the configuration now?|y
apply? [y/N]|y
EOF
t0=$SECONDS
run_flow /tmp/answers1 /tmp/t1; rc=$?
echo "--- run 1 transcript (plan..verify excerpts)"
sed -n '/· 4\/8 ·/,$p' /tmp/t1 | grep -vE '^\s+[0-9]+\) \[ \] ' | head -90 | sed 's/^/    | /'
ck "S1: flow exit code 0" test "$rc" -eq 0
ck "S1: scan listed $PKG as missing / distro package" grep -qE "^  $PKG \| missing \| distro package" /tmp/t1
cmdl=$(line_of "$FAMILY_CMD $PKG" /tmp/t1); dry=$(line_of 'Dry run passed' /tmp/t1); conf=$(line_of 'Run this plan now\?' /tmp/t1)
ck "S1: plan screen showed '$FAMILY_CMD $PKG' before the confirmation" test -n "$cmdl" -a -n "$conf" -a "${cmdl:-9999}" -lt "${conf:-0}"
ck "S1: the dry run result was shown before the confirmation" test -n "$dry" -a "${dry:-9999}" -lt "${conf:-0}"
ck "S1: exactly one package step was planned" grep -q 'Install 1 package(s)' /tmp/t1
ck "S1: installer reported the step done" grep -qF 'Done: Install 1 package(s)' /tmp/t1
ck "S1: $PKG now exists (command -v)" command -v "$PKG"
ck "S1: reached screen 8/8" grep -q '8/8' /tmp/t1
ck "S1: the doctor ran on screen 8 (its findings are listed)" bash -c "sed -n '/· 8\\/8 ·/,\$p' /tmp/t1 | grep -cE '^  (ok|WARN|FAIL) ' | grep -qv '^0$'"
ck "S1: the final screen has the doctor verdict" grep -qE 'Everything checks out|check\(s\) failed' /tmp/t1
ck "S1: doctor no longer lists $PKG as missing" bash -c "! sed -n '/· 8\/8 ·/,\$p' /tmp/t1 | grep -q 'missing: $PKG'"
ck "S1: chezmoi.toml has host ci-box" grep -q 'host    = "ci-box"' ~/.config/chezmoi/chezmoi.toml
ck "S1: chezmoi.toml has profile guest" grep -q 'profile = "guest"' ~/.config/chezmoi/chezmoi.toml
ck "S1: ~/.local/bin/rice exists" test -x ~/.local/bin/rice
ck "S1: no traceback" bash -c '! grep -q Traceback /tmp/t1'
echo "S1 run 1 took $((SECONDS - t0))s"

echo "=== S1 second run (same container): only what is missing is offered"
cat > /tmp/answers2 <<EOF
What now?|1
(recommended)|1
keep the current host|1
Git name for this machine|CI Bot
Git e-mail for this machine|ci@example.com
Wallpaper folder (empty|
Lock-screen image|2
numbers toggle|n
numbers toggle|
Apply the configuration now?|y
apply? [y/N]|y
EOF
run_flow /tmp/answers2 /tmp/t2; rc=$?
sed -n '/· 4\/8 ·/,/· 6\/8 ·/p' /tmp/t2 | head -30 | cut -c1-110 | sed 's/^/    | /'
ck "S1 run 2: exit code 0" test "$rc" -eq 0
ck "S1 run 2: the scan table now lists $PKG as ok, not missing" bash -c "grep -qE '^  $PKG \\| ok ' /tmp/t2 && ! grep -qE '^  $PKG \\| missing' /tmp/t2"
ck "S1 run 2: the plan checklist does not offer $PKG" bash -c "! grep -qE '\\) \\[.\\] $PKG — ' /tmp/t2"
ck "S1 run 2: still offers what is missing (checklist shown)" grep -q 'Choose what to install' /tmp/t2
ck "S1 run 2: reached 8/8" grep -q '8/8' /tmp/t2
ck "S1 run 2: host unchanged (ci-box)" grep -q 'host    = "ci-box"' ~/.config/chezmoi/chezmoi.toml

echo "=== S4e: onboard flags with a NEW host name after the TUI pinned profile/host"
rice-onboard --profile guest --host new-box --git-name "CI Bot" --git-email ci@example.com --accept-detected --bashrc-loader no < /dev/null > /tmp/e.out 2>&1; rc=$?
tail -4 /tmp/e.out | sed 's/^/    | /'
grep -E '^\s*(profile|host)\s*=' ~/.config/chezmoi/chezmoi.toml | sed 's/^/    | /'
ck "S4e: chezmoi.toml host is now new-box" grep -q 'host    = "new-box"' ~/.config/chezmoi/chezmoi.toml
ck "S4e: a [data.hosts.new-box] block was written" grep -q 'data.hosts.new-box' ~/.config/chezmoi/chezmoi.toml
ck "S4e: only one host line in chezmoi.toml" test "$(grep -cE '^\s*host\s*=' ~/.config/chezmoi/chezmoi.toml)" -eq 1

echo "=== S4c: rice tui after the first apply (finds the installer via chezmoi source-path)"
printf 'q\n' | rice tui --plain --lang en > /tmp/c.out 2>&1; rc=$?
head -6 /tmp/c.out | sed 's/^/    | /'
ck "S4c: rice tui opened the installer (welcome screen) and q stopped it" bash -c "grep -q '1/8' /tmp/c.out && grep -q Stopped /tmp/c.out && test $rc -eq 1"
ck "S4c: no traceback" bash -c '! grep -q Traceback /tmp/c.out'
( cd / && printf 'q\n' | rice tui --plain --lang en > /tmp/c2.out 2>&1 )
ck "S4c: also works from another directory" grep -q '1/8' /tmp/c2.out

echo "=== S4d: rice uninstall --yes after the flow"
ls ~/.config/kitty >/dev/null 2>&1 && check ok "S4d: a managed file exists before (kitty.conf)" || check FAIL "S4d: a managed file exists before (kitty.conf)"
if [ "$LOADER" = yes ]; then ck "S4d: the marked ~/.bashrc loader is there before" grep -q '^# >>> rice bashrc.d loader >>>$' ~/.bashrc; fi
rice uninstall --yes > /tmp/d.out 2>&1; rc=$?
tail -8 /tmp/d.out | sed 's/^/    | /'
ck "S4d: uninstall exit code 0" test "$rc" -eq 0
ck "S4d: the managed config was removed (kitty.conf)" test ! -e ~/.config/kitty/kitty.conf
ck "S4d: the marked loader was removed from ~/.bashrc" bash -c "! grep -q 'rice bashrc.d loader' ~/.bashrc"
ck "S4d: the installed package is still there ($PKG)" command -v "$PKG"
ck "S4d: ~/.bashrc itself is still there" test -f ~/.bashrc
exit 0
S1

# s2.sh: S2 (curses via the pty driver, inside this container): Ctrl-C, ESC, then the full walk
cat > "$tmp/s2.sh" <<'S2'
. /rice/lib.sh
bootstrap
export PATH="$HOME/.local/bin:$PATH"
cmd='cd ~/.local/share/chezmoi && exec python3 -m installer --lang en'
untouched() {
	ck "$1: $PKG was NOT installed" bash -c "! command -v $PKG"
	ck "$1: no ~/.config/chezmoi was written" test ! -e ~/.config/chezmoi
	ck "$1: ~/.local/bin/rice was not created" test ! -e ~/.local/bin/rice
}
echo "=== S2 Ctrl-C mid-flow (expected: exit 130, no traceback, terminal restored)"
python3 /rice/e2e_driver.py ctrlc --cmd "$cmd" --pkg "$PKG"
untouched "S2 Ctrl-C"
echo "=== S2 ESC at the plan confirmation (expected: documented cancel, exit 1, system untouched)"
python3 /rice/e2e_driver.py cancel --cmd "$cmd" --pkg "$PKG"
untouched "S2 ESC"
echo "=== S2 full curses walk, one real package"
t0=$SECONDS
python3 /rice/e2e_driver.py walk --cmd "$cmd" --pkg "$PKG"
echo "S2 walk took $((SECONDS - t0))s"
ck "S2: $PKG now exists (command -v)" command -v "$PKG"
ck "S2: chezmoi.toml has host e2e-box" grep -q 'host    = "e2e-box"' ~/.config/chezmoi/chezmoi.toml
ck "S2: ~/.local/bin/rice exists" test -x ~/.local/bin/rice
ck "S2: git identity written to ~/.config/git/local" grep -q 'E2E Bot' ~/.config/git/local
exit 0
S2

# s3.sh: S3 inside the container, started from a PLAIN image: only install.sh and a local clone exist
cat > "$tmp/s3.sh" <<'S3'
. /rice/lib.sh
stty rows 30 cols 100 2>/dev/null
export TERM=xterm LANG=C.UTF-8
export RICE_REPO_URL=file:///work/dotfiles
# the clone is owned by the host user, git in the container runs as root
printf '[safe]\n\tdirectory = *\n' > /tmp/gitconfig-e2e; export GIT_CONFIG_GLOBAL=/tmp/gitconfig-e2e
for t in python3 git curl chezmoi; do command -v "$t" >/dev/null && echo "E2E-NOTE $t is already installed"; done
if [ "$S3_MODE" = pipe ]; then cat /work/dotfiles/install.sh | sh -s -- --lang en
else sh /work/dotfiles/install.sh --lang en; fi
rc=$?
echo "E2E-NOTE install.sh finished with exit code $rc"
ck "S3: install.sh/TUI exit code is $S3_RC" test "$rc" -eq "$S3_RC"
export PATH="$HOME/.local/bin:$PATH"
echo "E2E-NOTE $(python3 --version 2>&1) | chezmoi $(chezmoi --version 2>&1 | head -1) | git $(git --version)"
if [ "$S3_EXPECT" = installed ]; then
	ck "S3: $PKG now exists (command -v)" command -v "$PKG"
	ck "S3: chezmoi installed by the official script in ~/.local/bin" test -x ~/.local/bin/chezmoi
	ck "S3: the repo was cloned to ~/.local/share/chezmoi" test -d ~/.local/share/chezmoi/.git
	ck "S3: chezmoi.toml has host e2e-box" grep -q 'host    = "e2e-box"' ~/.config/chezmoi/chezmoi.toml
	ck "S3: ~/.local/bin/rice exists" test -x ~/.local/bin/rice
else
	ck "S3: cancelled: $PKG was NOT installed" bash -c "! command -v $PKG"
	ck "S3: cancelled: no ~/.config/chezmoi was written" test ! -e ~/.config/chezmoi
fi
exit 0
S3

# ---- orchestration (host) -------------------------------------------------------------
declare -A prep=(
	[fedora]="dnf install -y -q python3 git curl jq >/dev/null"
	[debian]="DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 git curl jq ca-certificates >/dev/null"
)
declare -A image=([fedora]=fedora:43 [debian]=debian:trixie)
declare -A fcmd=([fedora]="dnf install -y" [debian]="apt-get install -y")
declare -A loader=([fedora]=no [debian]=yes)
pkg=${E2E_PKG:-fzf}
fail=0 checked=0 total=0 results=()
has() { case ",$2," in *",$1,"*) return 0 ;; esac; return 1; }

summarize() {  # summarize <label> <output file>: print the proofs, count failures
	local label=$1 out=$2 bad
	bad=$(grep -c '^E2E-CHECK FAIL' "$out")
	grep -E '^E2E-CHECK|^S[0-9].*took|^machine:|^E2E-NOTE|^screens seen' "$out" | sed 's/^/  /'
	if [ "$bad" -eq 0 ] && grep -q '^E2E-CHECK ok' "$out"; then results+=("PASS $label"); echo "  => PASS $label"
	else
		results+=("FAIL $label"); echo "  => FAIL $label ($bad failed checks; full transcript below)"
		cat "$out"; fail=1
	fi
}
run_in() {  # run_in <distro> <name> <script> <outfile> [docker -e args...]
	local d=$1 name=$2 script=$3 out=$4; shift 4
	docker run --rm --name "rice-e2e-$$-$name" -v "$repo:/repo:ro" -v "$tmp:/rice:ro" \
		-e PREP="${prep[$d]}" -e PKG="$pkg" -e FAMILY_CMD="${fcmd[$d]}" -e LOADER="${loader[$d]}" \
		"$@" "${image[$d]}" bash "/rice/$script" > "$out" 2>&1
}

for d in debian fedora; do
	has "$d" "$want_d" || continue
	echo "################ ${image[$d]}"
	docker image inspect "${image[$d]}" >/dev/null 2>&1 || docker pull -q "${image[$d]}" >/dev/null 2>&1 || { echo "  cannot pull ${image[$d]} — skipped"; continue; }
	checked=$((checked + 1))
	if has S1 "$want_s" || has S4 "$want_s"; then
		total=$((total + 1)); echo "== S1+S4 (plain flow, real install, robustness) on ${image[$d]}"
		run_in "$d" s1s4 s1s4.sh "$tmp/$d-s1s4.out"; summarize "S1+S4 ${image[$d]}" "$tmp/$d-s1s4.out"
	fi
	if has S2 "$want_s"; then
		total=$((total + 1)); echo "== S2 (curses via pty, inside the container) on ${image[$d]}"
		run_in "$d" s2 s2.sh "$tmp/$d-s2.out"; summarize "S2 ${image[$d]}" "$tmp/$d-s2.out"
	fi
	if has S3 "$want_s"; then
		rm -rf "$tmp/dotfiles"; git clone -q --no-hardlinks "$repo" "$tmp/dotfiles"
		if [ "$d" = debian ]; then   # the stock image has no apt lists: what does a stranger on a fresh machine see?
			total=$((total + 1)); echo "== S3 raw (no tty needed: RICE_TTY test hook) on ${image[$d]}: install.sh on the untouched image"
			docker run --rm --name "rice-e2e-$$-s3raw" -v "$tmp/dotfiles:/work/dotfiles:ro" -e RICE_REPO_URL=file:///work/dotfiles \
				"${image[$d]}" bash -c 'echo y > /tmp/y; RICE_TTY=/tmp/y sh /work/dotfiles/install.sh --lang en > /tmp/o 2>&1; rc=$?; cat /tmp/o
				if [ $rc -eq 0 ] || ! grep -q "Unable to locate package" /tmp/o; then echo "E2E-CHECK ok S3 raw: install.sh got past the prerequisites on the stock image"
				else echo "E2E-CHECK FAIL S3 raw: install.sh dies with apt Unable to locate package on the stock image (exit $rc): it never runs apt-get update"; fi' > "$tmp/$d-s3raw.out" 2>&1
			summarize "S3 raw ${image[$d]}" "$tmp/$d-s3raw.out"
		fi
		for mode in file pipe; do
			total=$((total + 1)); echo "== S3 one-liner path ($mode) on ${image[$d]}: plain image, real install.sh through a tty"
			if [ "$mode" = file ]; then scen=walk; expect=installed; rc=0; else scen=cancel; expect=cancelled; rc=1; fi
			dcmd="docker run -it --rm --name rice-e2e-$$-s3$mode -v $tmp:/rice:ro -v $tmp/dotfiles:/work/dotfiles:ro -e TERM=xterm -e LANG=C.UTF-8 -e PREP=x -e PKG=$pkg -e S3_MODE=$mode -e S3_EXPECT=$expect -e S3_RC=$rc ${image[$d]} bash /rice/s3.sh"
			python3 "$tmp/e2e_driver.py" "$scen" --prelude --pkg "$pkg" --expect-exit 0 --cmd "$dcmd" > "$tmp/$d-s3$mode.out" 2>&1
			summarize "S3 $mode ${image[$d]}" "$tmp/$d-s3$mode.out"
		done
	fi
done

echo "================ matrix"
printf '  %s\n' "${results[@]}"
echo "$checked images checked, $total scenario groups"
if [ "$checked" -eq 0 ] && [ "${CI:-}" = true ]; then echo "FAIL: images were skipped in CI"; fail=1; fi
exit $fail
