# Claros V2 working agreements

Claros helps students who find typing difficult answer a short-answer
worksheet directly or talk through a difficult question, review the exact
final wording, and place only the approved answer into a completed PDF. The
active work remains `openspec/changes/claros-reconstruction/`.

When project sources conflict, use this order:

1. `CLAROS_V2_SOL_ULTRA_EXECUTION_PRD.md`.
2. `CLAROS_V2_PRODUCT_CONTRACT.md` for product behavior.
3. `CLAROS_V2_DESIGN.md` for visual and interaction behavior.
4. Accepted V2 tests and evaluation thresholds.
5. Current implementation.
6. Git history as implementation reference only.

## Engineering

Before non-trivial code, architecture, schema, integration, or refactoring,
read `docs/agents/engineering.md`.

- Keep exact-answer review, deterministic server-owned placement, immutable
  source objects, and derivative-only export intact.
- Treat missing or unreadable inline space as an attached-answer-page outcome;
  reject only when the question or required context cannot be grounded safely.
- Keep both answer paths usable with typed input. Voice may trigger confirmation
  only in exact review with the exact phrase `Use this exact answer`; it never
  owns geometry or export.
- Use the active OpenSpec design for substantive requirement, architecture,
  schema, and surface-authority changes.
- Use Untitled UI React and EmbedPDF for V2. Radix, `react-pdf`, the Node API,
  and legacy styles may exist only behind `/legacy` until the cutover gate.
