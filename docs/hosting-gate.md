# Deferred hosting notes (Step 33 is deferred for V1, owner decision D-048)

**Status: V1 has no public deployment.** Step 33 and the public-hosting hardening are deferred
(owner-approved, D-048). Nothing has been uploaded, no account or service exists, and no payment
method is used. The budget is a hard $0. Render's free plan stays a possible *future* option; it was
never tested. This file is kept as the checklist for judging any future hosting decision, apart from
the local Docker work. Everything below was written before the deferral and still describes what
would have to be true first.

## Verdict on the current records: NO-GO until every gate below passes
1. **Security** (not built; would reopen the frozen Gate 4 API and needs its own approval):
   login/registration throttling, a cap on simultaneous password hashing, a password required to
   delete an account, `/docs` off, exact CORS origin, a stable secret held by the host, HTTPS.
2. **Licensing:** whether a job-seeking portfolio demo is "non-commercial" under the MovieLens
   terms is the owner's judgement (or GroupLens's answer), not mine. A public host holding the
   dataset and models fitted on it is redistribution and needs the citation shown and no
   endorsement claim.
3. **Privacy:** public registration collects real emails and passwords; the project assumed no
   real personal data.
4. **$0:** if any step needs a card, an upgrade or a paid fallback, stop.
5. **Measurements below** all pass against the host's *documented* limits.
6. The owner's separate explicit approval of deployment and of exactly what is uploaded.

## Temporary demo versus persistent data
- *Technically possible for a temporary demo* only if the measurements fit.
- *Not suitable for persistent user data* on a free database that expires: the accounts,
  ratings, interactions and events would be deleted at expiry, and analytics would restart.
- A free web service that sleeps when idle makes the first visit slow, loses anything held in
  process memory (including any in-memory login throttle), and has a temporary filesystem, so it
  must write nothing it needs later (this project writes only to the database).

## Measurements required before any upload (all local; none has been run)
Image size and runtime memory are separate limits; do not confuse them.

| # | Measurement | How (after the owner approves the build) | Compare with |
|---|---|---|---|
| 1 | Image size, uncompressed and **compressed** | `docker image ls`; compressed size from a saved/exported image or a manifest | the host's documented compressed-image limit |
| 2 | **Peak runtime RAM** of the API container | run it capped at 512 MB with swap off and about 0.1 CPU; read peak from `docker stats` at idle after start-up, after one recommendation, and during several simultaneous logins/registrations; any out-of-memory kill is a FAIL | the host's RAM limit (docs) |
| 3 | Cold-start time | container start to first successful response, same limits | acceptable wait after idle sleep |
| 4 | Latency | login, dashboard and recommendations at the same limits | owner's tolerance |
| 5 | **Database size** | `pg_database_size` on a throwaway `pmrs_test`-style database (never the development database): after seeding (about 88 MB seen locally), growth per registered user and per 1,000 ratings, and the dump size if one would be uploaded | the free database's storage limit and its expiry (docs) |
| 6 | Frontend bundle | already measured: about 301 kB JavaScript and 11.9 kB CSS | the static-hosting limits |
| 7 | Secret scan | search image layers and logs for the JWT secret and database password | must find none |

The docker-stats memory number includes a VM overhead on a Mac, so it approximates the host
rather than proving it.

## Facts to re-check in the host's official documentation before implementing
Free web service RAM, CPU, idle-sleep window and cold-start behaviour; monthly instance hours,
build minutes and bandwidth and what happens at the limit; the free database's storage, exact
expiry and grace period, connection limits and one-per-workspace rules; whether sign-up or deploy
needs a payment method; the compressed image-size limit and how images from a public or private
registry can be used for free; free static-site terms and pointing it at another API origin;
default HTTPS and redirects; running a one-off migrate and seed; build memory/time limits; GitHub
Actions free terms for the repository's visibility; and the MovieLens terms in the primary
GroupLens README.

## What uploading would mean (each item needs separate approval)
The code (a push, with a repository visibility decision), the model artifact (MovieLens-derived),
the MovieLens data or a dump of the seeded database, and any container image. Rebuilding the
artifact on the host is not an option: it would not match the frozen manifest and Step 16.

## Results so far (local, 2026-11-12; one Mac, Docker Desktop, arm64; estimates only)
Measured with `compose.app.yaml` after the owner approved the local build (D-047). Nothing was
uploaded and no host was contacted. **None of this proves a free host will work**: the host's real
limits are still unread, and a Mac VM is not the host's hardware.

| # | Measurement | Result |
|---|---|---|
| 1 | Image size | API 636 MB on disk, about 131 MB compressed (`docker save` through gzip: 130 MB). Web 92.6 MB on disk, about 26 MB compressed. The compressed figures include the shared base layers. Compare with the host's documented compressed-image limit: **not done** (limit not read). |
| 2 | API peak RAM, 512 MB limit, swap off, 0.1 CPU | Start-up about 190 MiB. After one register, one login, 11 ratings, one recommendation and one dashboard: about 250 MiB. 2 / 3 / 4 simultaneous register+login: 318 / 382 / 447 MiB peak. **8 simultaneous register+login: the container was OOM-killed (exit 137)**: each Argon2id hash uses 64 MiB (the library default). Result: **FAIL for an unthrottled public API**; it needs a cap of about 3-4 concurrent hashes (Phase 6B work, not built). |
| 3 | Cold start at 0.1 CPU | About 3.7-4 minutes from container start to the first HTTP 200 (two runs). Unthrottled: about 10-15 seconds. If a host also has a short start-up or port-check timeout, this could fail it (**recheck in its docs**). |
| 4 | Latency at 0.1 CPU | Single register 11.6 s, single login 6.1 s, recommendation 1.2 s, dashboard 0.6 s (one run each). |
| 5 | Database size | `pg_database_size` 18.4 MB after seeding; the Docker volume holds 92.5 MB on disk. Compare with the free database's limit: **not done** (limit not read). Growth per user was not measured. The expiry still rules out persistent data. |
| 6 | Frontend bundle | About 301 kB JavaScript and 11.9 kB CSS (earlier build). |
| 7 | Secret scan | The JWT secret and database password were searched for in both images' history and metadata and in all container logs: 0 occurrences. The files inside image layers were not scanned, but `.env` and `data/` are not in the API image (listed). Runtime environment variables are visible to `docker inspect` on this machine, as expected. |

Not measured: behaviour on the host's CPU and memory, many users, long runs, a real browser
against the containers.
