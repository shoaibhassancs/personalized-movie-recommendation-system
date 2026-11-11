# CLAUDE.md

Rulebook for Claude Code on this project: short, stable, read every session. Edit in place; keep
history in `DECISIONS.md` (repo root), not here. `project-notes/` is git-ignored (local only).

# Personalized Movie Recommendation System (PMRS)

## What this is
A web app (React + FastAPI + PostgreSQL) giving users ranked, explained movie recommendations
from content-based, collaborative and hybrid algorithms fitted on MovieLens `ml-latest-small`
and evaluated offline against baselines. Solo portfolio project for entry-level AI/ML roles.
Details: `project-notes/PROJECT_GUIDE.md` (why/what), `SCOPE.md` (boundaries),
`project-notes/BUILD_PLAN.md` (ordered steps), `project-notes/ARCHITECTURE.md` (design).
These four are approved as **working documents**; their recommendations are **provisional
defaults** until the step or gate that decides them. Do not copy them into this file.

## Current state
Python 3.12 uv project with dev tools and an empty `pmrs` package. Check
`project-notes/BUILD_LOG.md` for what is actually built; never assume a step is done unless the
log says it was run and verified.

## Working process
- **Owner drives.** Work phase by phase, in practical chunks of related steps. Pause only for a
  real decision, a new dependency set, an external action, or a phase gate; do not stop after
  every step when no input is needed. One phase at a time. At the start of a phase: purpose, numbered steps,
  recommended approach/tools, expected result, dependencies, verification, decisions needed.
  Wait for explicit approval; approval of one phase never covers the next. Silence or a general
  "okay" is not approval.
- **Open decisions** (evaluation cutoffs, MLflow install, TMDB, React, deploy
  platform, `ml-1m`) are decided at the step/gate listed in `PROJECT_GUIDE.md` §11. Present
  evidence and a recommendation, then wait. Do not treat a default as approved.
- **Changes to scope, versions, commitments or the remaining plan:** propose with evidence and
  trade-offs, get approval, then edit. Routine factual updates reflecting completed work may be
  made and reported.
- **No silent scope changes,** skipped dependencies, or "done" marks on unrun work. Deferrals
  need an explicit owner decision and are logged as *deferred (owner-approved)*.
- **After each completed step or work chunk:** add a note to `BUILD_LOG.md` (see "Build log
  style") and update any other affected document. After each phase: append to `DECISIONS.md` (numbered, dated; never delete entries;
  mark superseded ones). Add an ADR in `docs/adr/` only for a meaningful checkpoint decision.
- Do not create future packages or files just to reserve a place.

## Build log style (`project-notes/BUILD_LOG.md`)
It is the owner's readable record of progress, written like the reference
`each_step_notes.md` files (Desktop `references/`): plain language that explains, not a checklist.
- Top: a short **current status** (what exists, what is incomplete, next planned action).
- Below: **chronological notes**, one per completed step or meaningful work chunk. Each says what
  was done and how, why it mattered, files changed, important choices and reasons, and any
  problems hit. Mark owner decisions as such and keep them distinct from recommendations.
- **Verification** lists the actual commands with **PASS / FAIL / NOT RUN**, and what each result
  means in ordinary words; do not paste raw output as a substitute.
- Say what is **not verified** and what remains incomplete.
- No bare status tables standing in for explanation, and no empty entries for unstarted work.
  Keep history; correct mistakes by adding a note, not by erasing.

## Constraints (must follow)
- **No Git actions** (init, commit, push, remotes, visibility) unless the owner asks. Read-only
  inspection is fine.
- **Dependencies:** explain why and wait for approval before each new set. Declare every package
  the code imports in `pyproject.toml`.
- **Resources:** machine facts are in the guide §10 (8 GB RAM, about 12 GiB free disk). Re-check
  memory/disk before clearly heavy work (Docker builds, MLflow install, `node_modules`, full
  evaluation, large downloads) and recommend a smaller option if it may not fit.
- **No uploading or contacting outside services** and no exposing data, secrets, tokens or model
  files without approval of exactly what is sent. Secrets live only in environment variables.
- **Licences:** check primary sources; do not assume; no legal conclusions. MovieLens is
  non-commercial and needs citation. TMDB content is out of V1 unless the owner decides
  otherwise (its terms restrict use with ML applications).
- **Compatibility:** Linux and macOS; provide a fallback for platform-specific commands.
- **Quality:** after code changes run the project's lint and tests and report actual commands and
  results, including failures. Do not claim tests cover a failure mode they do not.
- **One implementation** for shared behaviour: the recommender package has no web dependency and
  is used by both the evaluation harness and the API.

## ML rules
- Evaluation uses a shared chronological split for all users. Nothing at or after the applicable
  cutoff (ratings or timestamped tags) may fit an evaluated model or content feature. Validation
  is for tuning only; test is read once, after refit on train + validation.
- Candidate set excludes the user's pre-cutoff items; held-out items stay eligible.
- If the split is infeasible, use only an owner-approved fallback with a narrowed claim; never
  call a per-user holdout globally leakage-safe.
- Fixed seeds wherever randomness affects results. Report uncertainty; claims stay proportionate
  to the evidence (offline, small dataset, development-grade data).

## Communication
Plain English; briefly define technical terms when first needed. Concise updates: what changed,
what ran, actual results, what could not be verified, what is needed from the owner. Label claims
as verified (and how), assumed, recommended, or unverified. Results the owner reports are
"owner-reported". Recommend one approach; list alternatives only when the choice is the owner's.
Report mistakes plainly.

## Commands
Verified in Step 1 (2026-11-12):
```bash
uv sync               # install pinned versions from uv.lock into .venv
uv run pytest         # run tests in tests/
uv run ruff check     # lint
uv run mypy           # type-check src/
```
Add new commands here only once they work.
