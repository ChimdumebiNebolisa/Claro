# Gate 3 verification record

- **Recorded:** 2026-09-04 CDT / 2026-09-05 UTC
- **Branch:** `codex/claros-v2-nerdy`
- **Accepted clean checkpoint:** `88cda664f55abf698a1d56567e814e024708ad0a`
- **Pull request:** `https://github.com/ChimdumebiNebolisa/Claros/pull/40`
- **Gate result:** Passed

Gate 3 is accepted without a local Docker Desktop dependency. The accepted
checkpoint re-baselines the complete Gate 0–3 tracked tree into one clean pull
request commit after replacing secret-like synthetic test fixtures. Its tree is
byte-identical to pre-scrub head `5235afca4a264a8dee00d02cbbe531f9930a352b`,
and GitGuardian passes without an exclusion or dashboard override. The checkpoint
contains the FastAPI service, filesystem and GCS adapters, signed
ownership, generated OpenAPI client, deterministic physical IR and placement,
immutable-source export, checksum-pinned corpus, remote build/deployment
assets, and the real typed browser integration. The untracked
`backend/semantic`, `backend/tests/semantic`, `backend/realtime`, and
`backend/tests/realtime` draft trees were excluded from every Gate 3 commit,
test list, source archive, and coverage result.

## Local acceptance replay

| Command or evidence                                                         | Result                                                                                                                                                             |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Node runtime                                                                | `v22.22.0`                                                                                                                                                         |
| `npm ci`                                                                    | 763 packages installed from the lockfile                                                                                                                           |
| `npm run ci`                                                                | Format, lint, typecheck, dependency/license checks, OpenAPI drift, 73/73 Vitest tests, Storybook build, all-story axe, production build, and bundle closure passed |
| `npm run test:e2e`                                                          | 22/22 fixture Chromium flows passed                                                                                                                                |
| `npm run test:e2e:gate3`                                                    | 1/1 real FastAPI Chromium flow passed; authenticated partial export survived service restart                                                                       |
| Tracked Gate 3 pytest files                                                 | 392 passed with 23 third-party deprecation warnings                                                                                                                |
| Gate 3 branch coverage                                                      | 92 percent after explicitly excluding the four untracked future-gate draft trees                                                                                   |
| Ruff format/lint                                                            | Passed for all tracked Python sources                                                                                                                              |
| `python scripts/generate-gold-corpus.py --check`                            | Passed for the checksum-pinned twelve-category corpus                                                                                                              |
| `python scripts/generate-gate3-pdf-evidence.py --check`                     | Passed after refreshing the deterministic placement hashes; PDF bytes were unchanged                                                                               |
| `npm audit --audit-level=high`                                              | 0 vulnerabilities                                                                                                                                                  |
| `pip-audit -r requirements-server.txt`                                      | No known vulnerabilities                                                                                                                                           |
| `terraform fmt -check -recursive deploy/terraform` and `terraform validate` | Passed with the pinned provider lock                                                                                                                               |
| `openspec validate claros-reconstruction --strict`                          | Passed                                                                                                                                                             |
| Authority SHA-256 checks                                                    | All three required hashes matched exactly                                                                                                                          |

The first final fixture replay hit three five-second cold-mount timeouts even
though its captured pages subsequently contained the expected states. The
affected readiness assertions now use the existing 60-second PDF/WASM cold-start
budget without changing product assertions. The three focused tests then passed
3/3, followed by the complete 22/22 replay.

The tracked server suite covers the twelve required PDF categories plus
encrypted, malformed, oversized, page/question-limit, stale-source,
unsupported-glyph, and changed-placement negatives. It also covers ownership,
logical expiry, authorized Range delivery, generation CAS, idempotent
confirmation/export, exact Unicode, source revalidation, and failed-publish
cleanup.

## Ubuntu production-container evidence

GitHub Actions run
[`33941739290`](https://github.com/ChimdumebiNebolisa/Claros/actions/runs/33941739290)
completed successfully for head SHA `88cda664f55abf698a1d56567e814e024708ad0a`.
Its Ubuntu `container-smoke` job checked out immutable pull-request merge SHA
`5bed4cfb8cc8e97caa843a628d511d37af7f9b63`, which contains that accepted
head, validated the container/deployment contracts, ran source/IaC/secret
scanning, built the production Dockerfile, started the non-root container,
waited for `/health`, exercised `/`, `/app`, authorized Range reads, uploaded
the checked-in gold worksheet, confirmed answers, exported PDFs, replaced the
real FastAPI container while retaining only its test volume, and reopened the
persisted exports with pikepdf.

The retained seven-day artifact is ID `9962065063`, named
`gate3-container-smoke-5bed4cfb8cc8e97caa843a628d511d37af7f9b63-1`,
and expires on 2026-09-12 UTC. It contains only privacy-checked logs, a safe
result summary, and the two synthetic completed PDFs:

| Artifact                                      | Evidence                                                                                                                                       |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `completed-inline.pdf`                        | 1 page; SHA-256 `8513FD0D8D391E827B4D9618069B03B5D259627F4504098153A8793C8DAF784A`                                                             |
| `completed-appendix.pdf`                      | 2 pages; SHA-256 `4A4ABC95D3514AD14CB389E380B105E17317C23020E7916E21B0533538743D00`                                                            |
| `first-container.log`, `second-container.log` | Both retained after worksheet, answer, cookie, and credential canary checks passed                                                             |
| `smoke-result.json`                           | Health, typed flow, restart persistence, ownership isolation, privacy logs, inline/appendix placement, UID 10001, and parser reopen all passed |

This is the authoritative production-container evidence. The Windows Docker
Desktop error 1920 remains only bypassed host diagnostics.

## Remote source build and deployed Cloud Run/GCS evidence

- Google Cloud project: `claro-490122` (project number `505797934944`), with
  billing enabled.
- Region and existing service: `us-central1`, `claros`.
- Private bucket: `claros-assignments-490122`, with public access prevention,
  uniform bucket access, object versioning, and seven-day soft delete enabled.
- Runtime identity:
  `claros-runtime@claro-490122.iam.gserviceaccount.com`.
- Deployment identity:
  `claros-github-deploy@claro-490122.iam.gserviceaccount.com`.
- Cloud Build ID: `8bcf24be-5be9-4e81-a8e5-fc2947d39754`; status `SUCCESS`.
- Production image:
  `us-central1-docker.pkg.dev/claro-490122/cloud-run-source-deploy/claros@sha256:b4058b7bb22210a82690db7859354dad4fdf354441d57ee46a79deea6d7d5b66`.
- The build used a clean `git archive` of runtime checkpoint
  `2afcdbb92fce3b1d055bc4bf3e4efbaec60c3ce7` and the
  repository's digest-pinned BuildKit Cloud Build configuration. No `.env`,
  credential, or future-gate draft file entered the upload.

Revision `claros-00074-kxl` received the seed phase. It created two assignments
in GCS, completed inline and appendix typed-answer flows, reopened both exports,
proved cross-owner denial, and proved forged `X-Forwarded-For` values did not
select fresh limiter keys. The same image digest was then forced into revision
`claros-00075-xtv`, which serves 100 percent of traffic. The verify phase loaded
and reopened both assignments and exports from GCS and repeated cross-owner
denial successfully. The service remained at 2 CPU, 2 GiB, concurrency 4,
300-second timeout, min 1/max 1, and the dedicated runtime identity.

A post-run Cloud Logging privacy scan examined 69 entries and found zero
worksheet, answer, session-cookie, review-token, or provider-credential canary
matches. The temporary signed-cookie smoke state was owner-restricted and
deleted immediately after verification.

## Live browser and PDF evidence

Chromium loaded the deployed product, created the public biology sample,
entered a typed answer, required exact review, accepted only **Use this exact
answer**, showed the appendix destination, and enabled a partial export with two
questions intentionally unanswered. The completed download was 33,728 bytes,
two pages, and SHA-256
`12E32D290973398A3DCF2A2787BB219366628758A62D86EAFA2246E9EAB517A0`.
Chromium's PDF viewer rendered both pages, and pikepdf independently reopened
the same downloaded bytes.

The repository inspection PDF remains
[`completed-inline-appendix.pdf`](./completed-inline-appendix.pdf), SHA-256
`099402F9999A7E232DB0F55A0CD9315BD8131E0FB313A02F2A70898E7354FE14`.
Its refreshed manifest is
[`completed-inline-appendix.manifest.json`](./completed-inline-appendix.manifest.json),
SHA-256
`BC5A4BA69D68F051D12224C1F14AA7381603F244D15FFB41C24D6AA7E406A491`.
The same PDF bytes reopen in Chrome and Adobe Acrobat 64-bit with the original
source page intact, exact inline content, and an untruncated attached answer
page.

## Infrastructure disposition

The existing Cloud Run service, bucket, Artifact Registry repository, runtime
identity, deployment identity, and Workload Identity pool/provider were
imported into dedicated remote Terraform state instead of duplicated. The
GitHub provider is active and restricts the immutable repository ID, immutable
owner ID, `main`, and the exact deployment workflow. Repository variables hold
only public identifiers and numeric secret versions; no credential value is a
GitHub secret or committed file.

The final full Terraform preview contains no resource creation or destruction.
It proposes one intentionally unapplied in-place assignment-bucket retention
change: add the one-day lifecycle rule and disable the adopted seven-day soft
delete window. Applying that data-affecting policy was not necessary for Gate 3
durability and was deferred rather than risking existing objects. Logical
24-hour access denial is already enforced by the service. The existing
deployment identity also retains legacy project-level grants; narrowing those
grants waits for the owner-gated Gate 6 deployment-workflow proof so access is
not removed speculatively.

## Gate disposition

OpenSpec tasks 3.1 through 3.10 are complete. Gate 3 passes on the accepted
clean checkpoint and the evidence above. Gates 4 and 5 remain separate work:
no semantic or Realtime provider implementation was integrated, committed, or
counted as Gate 3 progress.
