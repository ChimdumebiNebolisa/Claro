## Purpose

Defines the owner-bound `/api/v2` lifecycle, durable storage, concurrency,
authorized source access, expiry, and privacy boundaries for assignments.

## ADDED Requirements

### Requirement: Versioned V2 API surface
Claros MUST expose assignment creation/status, authorized source streaming,
page context, candidate creation, rephrasing, review, confirmation, revision,
export creation/status/download, and Realtime client credentials under
`/api/v2`. FastAPI OpenAPI MUST be the transport authority and the generated
browser client MUST match it in CI.

#### Scenario: API schema changes
- **WHEN** a request, response, error, endpoint, or domain enum changes
- **THEN** OpenAPI regeneration produces no unreviewed drift and frontend contract tests use the generated shape

### Requirement: Stable errors and optimistic concurrency
Every error MUST use
`{ "error": { "code": string, "message": string, "recoverable": boolean } }`.
Every mutation MUST carry `assignment_version`; state responses MUST include the
current version and `ETag`. A stale version MUST fail without overwriting newer
state.

#### Scenario: Two clients mutate one assignment version
- **WHEN** the first mutation advances the version and the second submits the old version
- **THEN** the second returns a stable recoverable conflict with current version metadata and preserves the first result

### Requirement: Signed anonymous ownership
Claros MUST authorize assignments through a signed `HttpOnly`, `SameSite=Lax`
session bound to an owner hash in durable state; production HTTPS sessions MUST
also use `Secure`. Mutation routes MUST enforce same-origin and owner checks.
No bearer assignment secret may be placed in `localStorage`, `sessionStorage`,
URLs, logs, or public object paths.

#### Scenario: Same browser reloads an assignment URL
- **WHEN** its unexpired owner session and assignment still validate
- **THEN** the current durable assignment state is restored without another upload

#### Scenario: Different owner requests an assignment
- **WHEN** a valid session not bound to that assignment requests its status, source, mutation, export, or credential
- **THEN** Claros denies access without disclosing private state or object existence

### Requirement: Durable immutable storage
Production assignment truth MUST survive process and Cloud Run revision
replacement in private Google Cloud Storage. Source, physical IR, and exports
MUST use immutable object names and creation preconditions; assignment manifests
MUST use generation-aware compare-and-swap. No production truth may exist only
in memory.

#### Scenario: Source is uploaded
- **WHEN** a new assignment accepts source bytes
- **THEN** GCS stores them once with an immutable generation and later writes cannot replace that object

#### Scenario: Manifest writers race
- **WHEN** two updates use the same observed manifest generation
- **THEN** exactly one compare-and-swap succeeds and the other returns a recoverable version conflict

#### Scenario: Cloud Run revision is replaced
- **WHEN** a later instance receives an authorized assignment request
- **THEN** it reconstructs the same current state from durable objects and manifests

### Requirement: Development storage cannot leak into production
A local filesystem adapter MAY implement the same storage interface for tests
and development. Production startup MUST fail closed when storage is configured
as local, in-memory, public, or otherwise non-durable.

#### Scenario: Production selects local storage
- **WHEN** the service starts in production mode with a local or in-memory adapter
- **THEN** startup fails before serving assignments and reports a configuration code without secrets

### Requirement: Authorized Range-capable source access
The source route MUST authenticate assignment ownership, return the immutable
source generation, support valid HTTP byte ranges required by the viewer, and
deny invalid or cross-owner ranges without exposing GCS publicly.

#### Scenario: Viewer requests a byte range
- **WHEN** the owner requests a satisfiable source range
- **THEN** Claros returns the correct bytes and range headers from the immutable source object

### Requirement: Bounded synchronous operations and durable status
P0 upload analysis and export creation MUST complete within bounded synchronous
requests or return a stable timeout/failure while preserving durable state.
The UI MUST show a truthful indeterminate state while such a request is pending.
GET status endpoints MUST make reload and future asynchronous processing safe;
process-local background tasks MUST NOT be the only owner of work.

#### Scenario: Export request times out safely
- **WHEN** export cannot finish within its configured request budget
- **THEN** Claros records a durable recoverable state, preserves confirmed answers, and permits an idempotent retry

### Requirement: Anonymous expiry
Anonymous assignments MUST expire logically 24 hours after creation. Every
authorization check MUST deny access after that absolute expiry even if physical
GCS lifecycle deletion has not yet run.

#### Scenario: Assignment reaches expiry
- **WHEN** its absolute 24-hour TTL elapses
- **THEN** status, source, mutations, exports, and Realtime credentials are denied and later object cleanup remains best-effort

### Requirement: Privacy-safe operations
Operational logs MUST NOT contain PDF text, questions, answers, audio,
transcripts, raw provider payloads, API keys, cookies, session secrets, review
tokens, or signed object access. Raw audio MUST NOT be stored. Expensive upload,
analysis, and Realtime credential operations MUST be rate-limited and all
untrusted PDF/model data MUST be bounded and safely rendered.

#### Scenario: Provider or parser fails
- **WHEN** an internal exception includes worksheet or provider content
- **THEN** telemetry records only bounded identifiers, stage, timing, and stable error code while the student receives safe recovery copy
