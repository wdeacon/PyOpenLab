# PyOpenLab — Claude instructions

Repo: `C:\Users\willi\OneDrive\Documents\Codebase\PyOpenLab`. Project notes live in the Obsidian
vault at `Project Notes/PyOpenLab/` — check there for context before starting work.

## Work in a git worktree — always

**Before your first edit to any tracked file, move into an isolated git worktree.** Never edit the
main checkout directly. Multiple Claude sessions run against this repo at once, and editing the live
checkout is how they collide.

Use the **`EnterWorktree` tool** (this instruction is the authorisation it requires). It creates the
worktree under `.claude/worktrees/`, branched fresh off `origin/master`, and moves the session into it.

- **Applies to:** any session that will *modify* tracked files — code, tests, docs, config.
- **Does not apply to:** read-only work (reading, searching, explaining, reviewing). No worktree
  needed if you write nothing.
- **The default branch here is `master`, not `main`.** Worktrees branch off `origin/master`.
- If you need to continue an existing feature branch rather than start fresh off `master`, say so and
  branch from that instead.

### Bootstrap first, every time
A worktree only checks out **tracked** files, and `.venv/` is gitignored. So the first command inside
a new worktree is:

```powershell
powershell -File scripts\bootstrap-worktree.ps1     # or: bash scripts/bootstrap-worktree.sh
```

It junctions `.venv` from the main checkout (instant, shared packages) and verifies that
`import pyopenlab` resolves to *this worktree*. `.env` is tracked here, so it arrives with the
checkout — nothing to copy.

### Why a shared venv is safe here
`pyopenlab` is **not** installed into the venv — there is no `.pth`, no `.egg-link` and no editable
finder in `site-packages` (verified 2026-07-28). The `pyopenlab.egg-info/` at the repo root is a
stale artifact of an old `pip install -e .`, not a live install. So `import pyopenlab` resolves via
`sys.path[0]` — the **current working directory** — and running pytest from the worktree imports the
worktree's code even though the venv is shared.

> **Always run tests from the worktree root.** And never `pip install -e .` into the shared venv: it
> would pin imports to one checkout and silently break isolation for every worktree. The bootstrap
> script's verify step exists to catch exactly that.

### Long paths are required
This repo vendors the Thorlabs SDK under deeply nested paths that sit just under Windows `MAX_PATH`
in the main checkout. The extra `.claude/worktrees/<name>/` prefix tips them over, and
`git worktree add` fails partway with `Filename too long`. Already configured locally:

```bash
git config core.longpaths true
```

If you clone this repo fresh, set it again before creating a worktree.

## Tests
```powershell
.venv\Scripts\python -m pytest -q
```

**Known-failing baseline (pre-existing, not yours):** 8 test modules fail *collection* on missing
deps — `PIL`, `matplotlib`, `past` — and 4 tests fail. This is identical in the main checkout, so
treat `4 failed, 8 errors` as the clean baseline and compare against it rather than assuming you
broke something. Use `--continue-on-collection-errors` to see past the collection stage.

## Landing the work
When the work is done and tests match the baseline, **offer Will the merge and wait for an explicit
yes.** Do not merge to `master`, push, or delete the worktree on your own initiative — a choice of
approach is never consent to merge. After he approves and the merge lands, tear the worktree down:

```bash
rm -rf ".claude/worktrees/<name>"     # the checkout
rm -rf ".git/worktrees/<name>"        # the registry entry
git branch -d <branch>
```

Use `rm -rf`, not `git worktree remove` — git's cleanup half-fails on Windows and leaves husks. Full
rationale in the vault: `Virtual Personel Assistant/VPA Wiki/Worktree Convention.md`.

## Vault conventions still apply
Write a session note to `Project Notes/PyOpenLab/Claude Sessions/` every working session, keep the
Kanban board current, and follow the global rules in `~/.claude/CLAUDE.md`.
