# Write-ups

Four experiments from the evaluation work this library was lifted out of,
written as prose: what was measured, what the numbers said, and what was
decided. The method they share is described first.

| Doc | One line |
|---|---|
| [briefing-parity-method.md](briefing-parity-method.md) | Frozen context, LLM judge, position-swapped head-to-head, ceiling flags: how a retrieval gap is told apart from a prompt gap. |
| [briefing-retrieval-blend.md](briefing-retrieval-blend.md) | A library that was never queried, an additive blend that fixed it, and the finding that more context made generation worse. |
| [embedding-model-ab.md](embedding-model-ab.md) | Five embedding models, recall saturated, a +0.004 margin against a +0.02 bar: a negative result, kept. |
| [hybrid-retrieval.md](hybrid-retrieval.md) | Dense plus Postgres full-text fused by RRF: zero regressions, and a win that only shows on exact terms. |
| [routed-vision-eval.md](routed-vision-eval.md) | A regression guard for a prompt router, and the grader bug it found on its first run. |

Numbers come from a construction-document product evaluated against public
Caltrans contract documents. The product's own code is private; the pieces
that needed neither its database nor its models are this package.
