# Five embedding models and a negative result

*Lever E of the parity roadmap. Before paying for a production re-embed, find
out whether a better embedding model exists for this corpus.*

## Why ask

Two observations suggested the embedding model was weak on specification
text. During a distance calibration an off-topic "drainage concrete" query
out-matched an on-topic "electrical" query against the standards library
(cosine 0.42 against 0.45). And after the special-provisions text became
retrievable, a mandated-product fact was in the corpus and still did not
rank into the top k.

Swapping the production model is not cheap: the embedding column is a fixed
`vector(1536)`, the service is pinned to one provider endpoint, and every
corpus would be re-embedded. So the question was asked offline first.

## The harness

Read-only. Load the library corpus (6,370 chunks, each labelled with its
division), embed every chunk and every query with each candidate, rank by
cosine, score. Two metrics:

- **recall@5**: at least one top-5 chunk carries an expected division AND
  every expected keyword appears in the combined top-5 text. This is the
  product's existing deterministic retrieval check, reused unchanged.
- **domain separation**: mean similarity of on-topic top-5 chunks minus mean
  similarity of off-topic ones. Higher means the model pushes the right
  division away from the wrong ones.

Eleven queries: seven curated retrieval checks and four targeting the facts
the parity harness had flagged. Queries were encoded as queries and chunks as
documents, because one candidate is asymmetric and would otherwise be
understated. A backend that fails or returns the wrong number of vectors is
logged and skipped so one dead endpoint cannot sink the comparison.

Candidates: the production `text-embedding-3-small` (1536 dims), its larger
sibling (3072), two Voyage models including a legal-domain one (1024), and a
local nomic model served by a llama.cpp-based runtime.

## The result

| model | dim | recall@5 | domain separation |
|---|---|---|---|
| text-embedding-3-small (baseline) | 1536 | 11/11 | 0.0218 |
| voyage-law-2 | 1024 | 11/11 | 0.0257 |
| text-embedding-3-large | 3072 | 11/11 | 0.0160 |
| voyage-3 | 1024 | 10/11 | 0.0065 |
| nomic-embed-text-v2-moe (local) | — | unmeasured | — |

Recall saturated at 11/11 and said nothing. Domain separation did the
discriminating. The legal-domain model was best, by 0.004. The decision bar
had been set before the run at one extra passed query or +0.02 separation,
because the alternative is a paid dependency and a dimension migration. The
margin was a fifth of the bar.

**Decision: keep the baseline.** The result was recorded as a no-go and the
migration never built.

Two details are worth more than the headline:

- Correcting the query encoding for the asymmetric model *lowered* its
  separation, from 0.032 to 0.026. A correction that moves a result toward
  the no-go confirms the no-go rather than casting doubt on it.
- The 3072-dimension model was worse than the 1536-dimension one on
  separation, at twice the cost. Bigger was not better on this text.

The local model could not be measured: its embedding server capped input at
512 tokens and library chunks run about 2,000, so every batch returned HTTP
500 and the backend was isolated and skipped. Pre-truncating the inputs would
have muddied the comparison, and the API models already outranked it.

## Caveat, and what the harness is for

The query set is too easy for recall@5. A harder set (recall@1, off-topic
distractor pairs) would separate the models more sharply; the finding is that
none of them separated enough to justify a migration, which is the question
that was asked. The scorer, the A/B runner, the backend isolation and the
recommendation rule with its margin are `judgeswap.embeddings`. The backends
and the corpus loader stayed in the product.
