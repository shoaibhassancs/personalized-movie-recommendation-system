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
Python 3.12 uv project: `pmrs.data` (download, loaders, validation), `pmrs.split` (per-user
holdout, ID maps, sparse matrix, evaluation groups, feasibility tables), `pmrs.recommender`
(baselines, content-based, item-kNN, SVD; the hybrid cold-start ladder; fixed-sentence
explanations; one `Recommender` class; joblib artifacts with metadata; a small CLI; Phase 2,
Steps 6-12), `pmrs.metrics` and `pmrs.evaluation` (Phase 3 Steps 13-14: metrics, bootstrap
intervals, and a harness that compares all methods on the validation period), tests, and an EDA
notebook; MovieLens data in `data/raw/` (git-ignored). Gates 1 and 2 are approved. Phase 3 is in
progress: Step 15 (validation-only tuning, `pmrs.evaluation.tuning`, MLflow via `mlflow-skinny`) has
run and its proposed frozen settings await owner approval (D-029; D-030 sets pure popularity
for 1-10 ratings and the cold-start simulation, 10+ hybrid for warm users); Step 16 (the single test read, `pmrs.evaluation.final`, D-032) has run and awaits owner review; the test period must not be read again or used to tune; Step 17 (D-033: `evaluated_step16` and all-data `serving_all_data` artifacts, `MODEL_CARD.md` draft) is built and awaits the owner's Gate 3 review; the Step 16 metrics apply only to the evaluated artifact. Gate 3 is approved (D-034): the ML core is frozen for V1 (configuration, artifacts, Step 16 results and limits; do not change models or the evaluation protocol on these results). Phase 4 chunk 4A (D-035: `pmrs.db`, Alembic, seed, `compose.yaml`) is built and verified (D-036: migrations, seed twice, 610 users, 9,742 movies, 100,836 ratings; `postgres:17-alpine` on loopback port 5433); chunk 4B (Steps 20-22, D-037: `pmrs.api` accounts, public catalogue, interactions, `DELETE /me`) is built and verified on the test database, for local use only (no rate limiting or HTTPS: do not expose it publicly); chunk 4C (Steps 23-24, D-039: recommendations from the verified serving artifact, seven-panel dashboard, login-only analytics, served/acted events, CORS for one origin) is built and verified; Gate 4 is approved (D-040); the serving artifact has no quality metric of its own. Phase 5, chunk 5A (Steps 25-27, D-041: `frontend/`, React + TypeScript + Vite, plain CSS, token in `sessionStorage`, catalogue/detail/account pages) is built and accepted (the owner reported the browser walkthrough and the redesign as complete); D-042: a view records `viewed` only, never `acted`. Phase 5, chunk 5B (Steps 28-30, D-043: recommendations page, seven-panel dashboard, login-only analytics with hand-built charts and text tables; one serving request per page visit via `frontend/src/served.ts`; logged-in people land on the dashboard; no new dependency) is built, automated checks and a real-API walkthrough on the throwaway `pmrs_test` pass, and the owner's browser review passed (owner-reported). Gate 5 is approved (D-044), so Phase 5 is complete. The genre analytics breakdown is deferred. Phase 6 local work is approved (D-045; strict $0 budget): Steps 31 (Docker: `Dockerfile`, `frontend/Dockerfile`, `compose.app.yaml`, separate from the dev `compose.yaml`), 32 (`.github/workflows/ci.yml`, first GitHub run failed at setup on placeholder SHAs, now pinned locally (D-046) and awaiting the owner's push and rerun) and 34 (README, `docs/hosting-gate.md`, model card edits) are written but images are NOT built or run; downloads await approval. Cloud deployment (Step 33), uploads, pushing and 6B hardening are NOT approved; Render's free plan is a gated possibility only. Step 35 is not started. The frontend is local only. Strict mypy passes; scikit-learn is untyped, so
its values are `Any` via one approved override (D-025). The code defaults are still the provisional
untuned values (D-026); the tuned values exist only in the proposed config file until the owner
freezes them. A `.joblib` artifact is a pickle: load only
artifacts this project built. Check `project-notes/BUILD_LOG.md` for what is actually built;
never assume a step is done unless the log says it was run and verified.

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
- **Resources:** machine facts are in the guide §10 (8 GB RAM; about 17.6 GiB free disk measured 2026-11-12, volume ~92% full). Re-check
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
- Evaluation uses the owner-approved **per-user temporal holdout** (D-021): each user's latest
  ceil(10%) ratings are test and the preceding ceil(10%) are validation; ties stay together. The
  shared global split was infeasible on this data (D-020). **Claim limit:** results support only
  "methods compared under the same per-user holdout protocol". Never call them globally
  leakage-safe or predictive of future behaviour: models are fitted once and so still see other
  users' later ratings and tags.
- Within the protocol: a user's own pre-cutoff data only for their history; a tag is usable only
  if earlier than its author's own cutoff; validation is for tuning only; test is read once,
  after refit on train + validation. A fixed-seed 20% of users stays out of every fit (cold-start
  simulation, reported as a simulation, not real new-user evidence).
- Candidate set, warm users: excludes the user's known pre-cutoff items; held-out items stay
  eligible. Cold-start simulation users: excludes **only the ratings actually revealed** for that
  history size (0, 3, 5, 10); hidden train, validation and test ratings never filter candidates
  (D-023).
- The evaluation harness refuses `target="test"` unless `allow_test=True`, which only the final
  evaluation (Step 16) may pass, once, after the configuration is frozen. Tuning code never passes
  it. Report validation and test results separately, with intervals, and say that intervals
  cover sampling noise between users only.
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
uv run ruff format    # format code (add --check to only check)
uv run python -m pmrs.data.download   # fetch MovieLens into data/raw/ (already done once)
uv run python -m pmrs.split           # build the split, print and save feasibility tables (Step 5)
uv run python -m pmrs.recommender.smoke   # fit each model + the hybrid on validation data: time, memory, sample lists (Steps 6-12)
uv run python -m pmrs.recommender.cli build --target validation   # save an artifact (never overwrites)
uv run python -m pmrs.recommender.cli recommend --artifact data/processed/artifacts/validation --ratings 318:5,296:4.5 -k 10
uv run python -m pmrs.evaluation   # compare all methods on the VALIDATION period; writes data/processed/evaluation/ (Step 14)
uv run python -m pmrs.evaluation.tuning   # Step 15: 36 validation-only trials; writes data/processed/tuning/ and mlruns/ (~1 min)
uv run python -m pmrs.evaluation.final --target validation   # Step 16 dry run (the test read, already done once, needs --read-test-once and refuses a repeat)
uv run python -m pmrs.evaluation.serving verify   # Step 17: check both artifacts (build refuses to overwrite; they already exist)
docker compose up -d db   # Step 18: this project's Postgres on loopback port 5433 (not the other project's 5432)
uv run alembic upgrade head   # create the tables (needs the database up and .env)
uv run uvicorn pmrs.api.app:create_app --factory   # Step 20-22: the API on localhost (needs .env with JWT_SECRET and the database up)
uv run python -m pmrs.db.seed   # Step 19: load MovieLens, then verify against the CSVs; safe to run twice
uv run python -m pmrs.evaluation.selection   # Step 15: apply the owner's choices (D-030), write the proposed config, run the routing checks
cd frontend && npm install --no-audit   # Step 25: frontend packages (never run npm audit without approval)
cd frontend && npm run dev   # the app on http://localhost:5173 (use localhost, not 127.0.0.1; needs the API running)
cd frontend && npm run typecheck && npm run lint && npm test && npm run build   # Step 25-27 checks
docker compose -f compose.app.yaml config --quiet   # Step 31: validate the full-stack file only (images not yet built)
```
Add new commands here only once they work.
