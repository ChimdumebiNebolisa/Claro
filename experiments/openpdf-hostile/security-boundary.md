# OpenPDF untrusted-PDF threat boundary

This is a deployment design, not an implementation. OpenPDF must not run in the Claros API process or inherit broad access to Claros infrastructure. Uploaded PDFs and every object reachable from them are attacker-controlled.

## Minimum boundary

```text
Claros API
  -> immutable source object + server-created job ID/placement manifest
  -> queue/broker
  -> one restricted OpenPDF worker process per job
       - untrusted bytes enter here
       - only allowlisted font bytes are readable
       - derivative is written to a per-job temporary directory
  -> independent qpdf + semantic validation gate
  -> derivative object storage
```

The placement manifest is server-owned and contains object identifiers, page number, exact approved answer, physical coordinates, and font ID. It contains no client-supplied filesystem path, URI, HTML, template, font, command-line argument, or Java class name. The worker receives PDF bytes through a bounded stream or a broker-provided opaque object handle; it receives no general object-store credentials.

## Required worker controls

- Run as a non-root identity in a dedicated container or equivalent sandbox, with no Linux capabilities, no host mounts, and a restrictive syscall profile.
- Deny all outbound and inbound network access. PDF links and actions are data to preserve, never URLs for the worker to resolve.
- Make the runtime image and font directory read-only. Mount only a newly created per-job temporary directory as writable, with a hard byte quota. Resolve that directory before use and never concatenate attacker-controlled path components.
- Bundle a fixed, checksum-pinned allowlist of licensed fonts. Reject unsupported code points; never load a font supplied by the PDF or request unless it is merely preserved as opaque source data.
- Permit no arbitrary HTML, JavaScript, external entity, attachment, media, shell, office-suite, or URL rendering path. Continuation pages use OpenPDF's document/layout API with plain approved text.
- Apply hard limits before parsing and while processing: upload bytes, claimed and discovered page count, output bytes, temporary storage, JVM heap/direct memory, worker CPU, wall-clock time, and process/thread count. Kill the entire worker process on deadline or limit violation; do not try to continue in a potentially corrupted JVM.
- Start with conservative product limits (for example 25 MiB input, 200 pages, 100 MiB output, 512 MiB memory, one CPU, and a 60-second wall deadline), then lower or raise them only from measured production-like fixtures. Compressed streams and object graphs require runtime resource enforcement because declared sizes are not trustworthy.
- Process one job per worker process. After success or failure, close handles, terminate the process, and delete the resolved per-job directory. Do not reuse writable caches across tenants.
- Pin the JRE, OpenPDF, FOP, Bouncy Castle, and transitive dependencies. Scan the built image and have an urgent patch/rebuild path. OpenPDF's own security policy says it is not a sandbox and does not protect against resource-exhaustion attacks.
- Emit only bounded diagnostic metadata: job ID, input/output hashes and sizes, duration, peak resource use, validator outcomes, and a categorized error. Do not log PDF content, approved answers, passwords, or parser stack dumps containing document data.

## Publication gate

The worker's derivative is untrusted output until a separate validation process accepts it. At minimum that gate must:

1. reopen with OpenPDF and an independent parser;
2. run `qpdf --check` in its own restricted process and deadline;
3. enforce output/page/resource limits;
4. compare source and derivative page boxes, rotations, annotations, forms, outlines, links, metadata, images, embedded source fonts, and source-page rendering outside approved overlay masks;
5. extract and match every non-RTL overlay exactly in PDFBox and PDF.js;
6. verify physical placement and continuation-page contents; and
7. fail closed on any timeout, parser disagreement, unsupported feature, missing evidence, or unexpected mutation.

Encryption passwords are short-lived job secrets, passed out of band rather than in filenames or logs, and destroyed with the worker. A malformed PDF that forces xref reconstruction is a separately classified full-rewrite operation; it must never silently fall back from the incremental preservation path.

## Threats contained by this boundary

The boundary limits the blast radius of parser/JVM vulnerabilities, decompression or object-graph bombs, infinite/expensive parsing, path traversal, unsafe external references, hostile embedded fonts, cross-tenant residue, and malformed derivatives. It does not make OpenPDF intrinsically safe, prove absence of parser vulnerabilities, or make a full rewrite semantically equivalent to incremental stamping. Independent validation and fail-closed publication remain mandatory.
