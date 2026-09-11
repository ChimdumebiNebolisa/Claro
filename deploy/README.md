# Claros V2 Cloud Run delivery

Claros currently runs as the adopted public Cloud Run service `claros` in
`us-central1`. FastAPI serves the Vite build and `/api/v2`; a private GCS bucket
is the only assignment truth. The deployment pipeline builds once, scans the
image, deploys its immutable Artifact Registry digest for staging validation,
proves assignment persistence across a new Cloud Run revision, and can then
owner-approve that exact digest for production. Both environment variables
target the one authorized service until the owner deliberately provisions a
separate service. Source checkout and container builds run remotely; no
developer workstation Docker daemon is part of the acceptance path.

The owner-only values and console actions are reduced to
[`OWNER_PROVISIONING_CHECKLIST.md`](./OWNER_PROVISIONING_CHECKLIST.md).

## Security and persistence boundary

- The adopted private bucket has public access prevention, uniform bucket-level
  access, object versioning, and a seven-day soft-delete window. Logical access
  expires at 24 hours in the app independently of physical cleanup. Terraform's
  proposed one-day lifecycle/soft-delete change remains unapplied because it is
  data-affecting and requires a separate retention decision; cleanup must never
  be described as instantaneous.
- The runtime service account receives `roles/storage.objectUser` on only this
  bucket and `roles/secretmanager.secretAccessor` on only the three Claros
  secrets. It receives no deploy or registry-write permissions.
- Terraform grants the GitHub deploy account repository-scoped Artifact
  Registry write, act-as on only the Claros runtime account, and a named-service
  Cloud Run condition. The adopted account still has legacy project-level
  grants; Gate 6 removes them only after the owner-gated WIF deployment path is
  proven, avoiding speculative loss of deployment access.
- GitHub authenticates with Workload Identity Federation. Its provider accepts
  only the immutable repository and owner IDs, the configured branch, and the
  exact `.github/workflows/deploy.yml` workflow. Service-account JSON keys are
  neither created nor accepted by this delivery path.
- `CLAROS_COOKIE_SECRET`, `CLAROS_REVIEW_TOKEN_SECRET`, and the server-only
  `CLAROS_OPENAI_API_KEY` come from Secret Manager. The Cloud Run renderer
  rejects `latest`; every deployment selects numeric versions.
- GCS has no browser CORS policy and no public objects. Source and export bytes
  are available only through the owner-cookie-authorized FastAPI routes.

The service is intentionally public because P0 uses anonymous, signed owner
sessions. The Cloud Run Invoker IAM check is disabled in the rendered service;
authorization remains at the assignment boundary rather than the platform
request boundary.

## One-time infrastructure bootstrap

Use a dedicated, access-controlled Terraform state bucket that is not the
24-hour assignment bucket. Copy `terraform.tfvars.example` to an ignored
`terraform.tfvars`, replace every placeholder, then run:

```text
terraform -chdir=deploy/terraform init \
  -backend-config="bucket=ADMIN_MANAGED_TERRAFORM_STATE_BUCKET" \
  -backend-config="prefix=claros-v2"
terraform -chdir=deploy/terraform plan -out=claros.tfplan
terraform -chdir=deploy/terraform apply claros.tfplan
```

The Terraform identity is an administrative bootstrap identity, not the CI
deployer. Review the plan before applying it. The configuration protects the
assignment bucket and secrets from `terraform destroy`; an intentional teardown
requires a separately reviewed state/configuration change.

Terraform creates or adopts empty Secret Manager resources but never accepts
secret data. Add values through a secure administrative terminal or an approved
secret bootstrap system, then record each returned numeric version. Do not pass
values as command-line flags or Terraform variables. For example:

```text
gcloud secrets versions add claros-cookie-secret --data-file=-
gcloud secrets versions add claros-review-token-secret --data-file=-
gcloud secrets versions add claros-openai-api-key --data-file=-
```

Each command reads the value from standard input. Ensure terminal history,
transcripts, and CI logs never capture the input.

## Remote source and container builds

`deploy/cloudbuild.yaml` is the supported Google-hosted source-build path. It
uses a digest-pinned Docker builder with BuildKit enabled, so Docker Desktop is
not required. Submit a clean archive of a committed revision rather than the
working directory; untracked drafts and ignored credentials cannot enter the
build context:

```text
git archive --format=tar.gz --output=claros-source.tgz ACCEPTED_COMMIT_SHA
gcloud builds submit claros-source.tgz \
  --project=GCP_PROJECT_ID \
  --region=GCP_REGION \
  --config=deploy/cloudbuild.yaml \
  --substitutions=_IMAGE_URI=REGION-docker.pkg.dev/PROJECT/REPOSITORY/claros:gate3-ACCEPTED_COMMIT_SHA,_VCS_REF=ACCEPTED_COMMIT_SHA,_BUILD_DATE=RFC3339_COMMIT_TIME,_SOURCE_URL=https://github.com/ChimdumebiNebolisa/Claros
```

Cloud Build publishes the image to Artifact Registry and reports its immutable
digest. Cloud Run manifests and promotions use that digest, never the mutable
tag. The GitHub-hosted Ubuntu container-smoke job independently builds the same
production Dockerfile and retains privacy-checked logs plus reopened synthetic
PDFs as workflow artifacts.

## GitHub environment configuration

Configure these repository or environment variables (they are identifiers and
numeric versions, not secret values):

```text
GCP_PROJECT_ID
GCP_REGION
GCP_WORKLOAD_IDENTITY_PROVIDER
GCP_DEPLOY_SERVICE_ACCOUNT
CLAROS_GCS_BUCKET
CLAROS_STAGING_SERVICE
CLAROS_PRODUCTION_SERVICE
CLAROS_COOKIE_SECRET_VERSION
CLAROS_REVIEW_TOKEN_SECRET_VERSION
CLAROS_OPENAI_API_KEY_VERSION
```

Make the `production` GitHub environment require an approving reviewer. A push
to the configured deployment branch builds and tests staging. Production runs
only from a manual dispatch with `promote_to_production` selected, after the
staging job from that same run passes.

All third-party actions are pinned to full commit SHAs. The pipeline performs a
source/IaC/secret scan, publishes BuildKit provenance and SBOM attestations,
scans the pushed digest for HIGH/CRITICAL findings, uploads a CycloneDX SBOM,
and uses only the digest in Cloud Run manifests. The build tag is unique and
immutable; it is discovery metadata, never the promoted identity.

## Cloud Run runtime envelope

`cloud-run.service.template.yaml` freezes the P0 envelope: 2 CPU, 2 GiB memory,
concurrency 4, 300-second timeout, min 1/max 1 instance, second-generation
execution, and `/health` startup and liveness probes. The renderer validates
project, region, service, bucket, HTTPS origin, 40-character release SHA,
Artifact Registry digest, and numeric secret versions before producing YAML.

The one-instance maximum is a demo-stage constraint, not the target scaling
model. The current limiter is process-local and intentionally treats forwarded
headers as untrusted. Keep one instance until a shared or edge limiter exists;
the deployed staging smoke proves that client-supplied `X-Forwarded-For` values
cannot select a fresh local rate-limit key.

The container defaults to production with GCS storage, uses digest-pinned Node
and Python base images, installs both ecosystems from hash/lock files, and runs
as UID/GID 10001. It contains no credentials. Production startup fails if GCS,
the public HTTPS origin, or application signing secrets are absent.

## Verification commands

Static and unit verification does not require cloud credentials:

```text
python -m ruff check scripts/gate3-container-*.py backend/tests/container
python -m pytest backend/tests/container -q
terraform fmt -check -recursive deploy/terraform
terraform -chdir=deploy/terraform init -backend=false
terraform -chdir=deploy/terraform validate
```

The authoritative container smoke runs on GitHub's Ubuntu runner through the
dispatchable **Gate 3 container** workflow. It builds the production
`Dockerfile`, waits for `/health`, exercises upload/confirmation/export,
replaces the container while retaining only its test volume, reopens the
persisted exports with pikepdf, scans container logs for privacy canaries, and
uploads the safe logs plus completed synthetic PDFs as a seven-day workflow
artifact.

Local Docker is an optional convenience only:

```text
python scripts/gate3-container-smoke.py
```

It first proves production rejects local storage. It then runs the test-mode
image with a read-only root, dropped capabilities, `no-new-privileges`, bounded
CPU/memory/PIDs, and a dedicated Docker volume. Through HTTP it checks
`/health`, `/app`, the signed owner cookie, authorized source Range reads,
candidate/review/confirmation, partial inline and appendix exports, status and
authenticated download. It replaces the container and proves all assignment,
source, and export state survives from the mounted store.

Failure of a developer's local Docker Desktop does not block container
acceptance when the remote Ubuntu workflow passes for the same commit.

The deployed GCS/Cloud Run smoke is intentionally two-phase:

```text
python scripts/gate3-container-staging-smoke.py seed \
  --base-url https://STAGING_SERVICE_HOST --state-file SECURE_TEMP_FILE \
  --verify-proxy-identity
python scripts/gate3-container-staging-smoke.py verify \
  --base-url https://STAGING_SERVICE_HOST --state-file SECURE_TEMP_FILE
```

Run `seed`, replace the Cloud Run revision with the same image digest, then run
`verify`. The staging-only proxy probe deliberately reaches the configured
process-local upload limit using invalid sample names and different forged
forwarded headers; the final request must still receive `rate_limit_exceeded`.
Both phases also prove cross-owner denial. The state file contains a short-lived
signed owner cookie: create it with owner-only permissions, keep it off
artifacts and logs, and delete it even on failure. The GitHub workflow performs
these steps in one job and redacts all application bodies, answer text, review
tokens, cookies, and provider data.

Gate 4 and Gate 5 cannot be integrated until the remote container workflow and
the deployed staging workflow both pass, including live GCS persistence, Cloud
Run revision persistence, ownership isolation, and proxy-identity behavior.
Cloud Run, Artifact Registry, and private GCS remain the only production
deployment architecture.
