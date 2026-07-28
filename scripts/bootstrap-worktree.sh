#!/usr/bin/env bash
# Bootstrap a fresh git worktree (Bash / Git-Bash on Windows). See the header of
# bootstrap-worktree.ps1 for the full rationale. In short: a worktree checks out
# only TRACKED files, so it lacks the gitignored .venv (deps); this junctions it
# from the MAIN checkout. Unlike InspiredTees, this repo TRACKS .env, so there is
# nothing to copy. Idempotent. Run from the worktree root:
#     bash scripts/bootstrap-worktree.sh
#
# `pyopenlab` is NOT installed into the venv (no .pth / .egg-link / editable
# finder), so `import pyopenlab` resolves via the CWD - running pytest from the
# worktree imports the worktree's code despite the shared venv. The verify step
# below asserts that, to catch a future `pip install -e .` breaking isolation.
set -euo pipefail

here="$(pwd)"
common_git="$(git -C "$here" rev-parse --git-common-dir)"
case "$common_git" in
  /*|[A-Za-z]:*) : ;;                    # already absolute
  *) common_git="$here/$common_git" ;;  # make absolute
esac
main_root="$(cd "$common_git/.." && pwd)"

if [ "$main_root" = "$here" ]; then
  echo "Already in the main checkout ($here) - nothing to bootstrap."
  exit 0
fi

echo "Worktree : $here"
echo "Main     : $main_root"

# --- .venv : junction to the main venv (Windows mklink /J, no admin needed) ---
if [ ! -e "$main_root/.venv" ]; then
  echo "WARN: no .venv in main ($main_root/.venv). Create it there first."
elif [ -e "$here/.venv" ]; then
  echo ".venv already present - leaving it."
else
  # Convert to Windows paths for cmd's mklink.
  win_link="$(cygpath -w "$here/.venv" 2>/dev/null || echo "$here\\.venv")"
  win_target="$(cygpath -w "$main_root/.venv" 2>/dev/null || echo "$main_root\\.venv")"
  cmd //c mklink //J "$win_link" "$win_target" >/dev/null
  echo ".venv -> junction to main venv (OK)"
fi

# --- .env : tracked in this repo, so it should already be here ----------------
if [ -e "$here/.env" ]; then
  echo ".env present (tracked in git - came with the worktree)."
else
  echo "WARN: .env missing. It is tracked here, so a clean worktree should have it."
fi

# --- verify : imports must resolve to THIS worktree, not main -----------------
py="$here/.venv/Scripts/python.exe"
if [ -x "$py" ]; then
  resolved="$(cd "$here" && "$py" -c "import pyopenlab, os; print(os.path.dirname(os.path.dirname(pyopenlab.__file__)))" 2>/dev/null | tail -1)"
  # Normalise both sides to forward slashes for comparison.
  resolved_n="$(echo "$resolved" | tr '\\' '/')"
  here_n="$(echo "$here" | tr '\\' '/')"
  if [ "$resolved_n" = "$here_n" ]; then
    echo "verify: 'import pyopenlab' resolves to this worktree (OK)"
  else
    echo "WARN: 'import pyopenlab' resolved to '$resolved', NOT this worktree."
    echo "WARN: the worktree is NOT isolated - something installed pyopenlab into the shared venv."
  fi
fi

echo
echo "Bootstrap done. Run tests FROM THIS DIRECTORY with:  .venv/Scripts/python -m pytest -q"
echo "NOTE: 8 test modules already fail collection on missing deps (PIL, matplotlib, past)"
echo "      in the main checkout too - that is pre-existing, not caused by the worktree."
