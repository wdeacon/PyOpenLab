# Bootstrap a fresh git worktree so it can run tests like the main checkout.
#
# A `git worktree` only checks out TRACKED files. This repo keeps `.venv/`
# (installed dependencies) gitignored, so a new worktree starts without it and
# `python -m pytest` would fail. This script wires it up from the MAIN checkout:
#
#   * `.venv`  -> a directory JUNCTION to the main venv (no reinstall; instant,
#                 shares the same packages). Junctions need no admin rights.
#
# Unlike InspiredTees, this repo TRACKS `.env`, so a worktree already has it and
# there is nothing to copy. The script checks and reports rather than assuming.
#
# IMPORT RESOLUTION (the thing to understand before trusting a shared venv):
# `pyopenlab` is NOT installed into the venv - there is no .pth, no .egg-link and
# no editable-install finder in site-packages (verified 2026-07-28). The stale
# `pyopenlab.egg-info/` at the repo root is a leftover artifact from an old
# `pip install -e .`, not a live install. `import pyopenlab` therefore resolves
# purely via sys.path[0] - i.e. the CURRENT WORKING DIRECTORY. Running pytest
# from inside a worktree imports THAT worktree's code, even though the venv is
# shared with main. That is why the junction is safe here.
#   -> Corollary: always run tests FROM the worktree root. If someone ever does
#      `pip install -e .` into the shared venv, that would pin imports to
#      whichever checkout was installed and break this isolation. The verify step
#      at the end of this script exists to catch exactly that regression.
#
# Idempotent: safe to re-run. Run it from inside the new worktree:
#     powershell -File scripts\bootstrap-worktree.ps1
#
# NOTE: paths are built with inline [IO.Path]::Combine, NOT Join-Path and NOT via
# a helper function. Under Windows PowerShell 5.1 in this environment, both
# `Join-Path` and a one-line wrapper function were observed returning an empty
# string from inside a script file (silently nulling the paths); only the inline
# .NET call is reliable here.
$ErrorActionPreference = "Stop"

# Resolve THIS worktree's root, and the MAIN checkout. `--show-toplevel` is the
# current worktree; `--git-common-dir` points at the SHARED .git dir, which lives
# inside the main checkout, so its parent is the main worktree root.
$here = (git rev-parse --show-toplevel).Trim()
$commonGit = (git rev-parse --git-common-dir).Trim()
if (-not [System.IO.Path]::IsPathRooted($commonGit)) {
    $commonGit = [System.IO.Path]::Combine($here, $commonGit)
}
$here = (Resolve-Path $here).Path
$mainRoot = (Resolve-Path ([System.IO.Path]::Combine($commonGit, '..'))).Path

if ($mainRoot -eq $here) {
    Write-Host "Already in the main checkout ($here) - nothing to bootstrap."
    exit 0
}

Write-Host "Worktree : $here"
Write-Host "Main     : $mainRoot"

# --- .venv : junction to the main venv -------------------------------------
$mainVenv = [System.IO.Path]::Combine($mainRoot, '.venv')
$wtVenv   = [System.IO.Path]::Combine($here, '.venv')
if (-not (Test-Path $mainVenv)) {
    Write-Warning "No .venv in main checkout ($mainVenv). Create it there first:"
    Write-Warning "  python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt"
} elseif (Test-Path $wtVenv) {
    Write-Host ".venv already present - leaving it."
} else {
    New-Item -ItemType Junction -Path $wtVenv -Target $mainVenv | Out-Null
    Write-Host ".venv -> junction to main venv (OK)"
}

# --- .env : tracked in this repo, so it should already be here --------------
$wtEnv = [System.IO.Path]::Combine($here, '.env')
if (Test-Path $wtEnv) {
    Write-Host ".env present (tracked in git - came with the worktree)."
} else {
    Write-Warning ".env missing. It is tracked in this repo, so a clean worktree should have it."
    Write-Warning "Check 'git status' - it may have been deleted locally."
}

# --- verify : imports must resolve to THIS worktree, not main ---------------
# This is the isolation guarantee. If it fails, the shared venv has an editable
# install pinning imports elsewhere and the worktree is NOT isolated.
$py = [System.IO.Path]::Combine($here, '.venv', 'Scripts', 'python.exe')
if (Test-Path $py) {
    Push-Location $here
    try {
        $resolved = (& $py -c "import pyopenlab, os; print(os.path.dirname(os.path.dirname(pyopenlab.__file__)))" 2>&1 | Select-Object -Last 1)
        if ($resolved -eq $here) {
            Write-Host "verify: 'import pyopenlab' resolves to this worktree (OK)"
        } else {
            Write-Warning "verify: 'import pyopenlab' resolved to '$resolved', NOT this worktree."
            Write-Warning "The worktree is NOT isolated - something installed pyopenlab into the shared venv."
            Write-Warning "Fix: pip uninstall pyopenlab from the shared venv, or give this worktree its own venv."
        }
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Bootstrap done. Run tests FROM THIS DIRECTORY with:  .venv\Scripts\python -m pytest -q"
Write-Host "NOTE: 8 test modules already fail collection on missing deps (PIL, matplotlib, past)"
Write-Host "      in the main checkout too - that is pre-existing, not caused by the worktree."
