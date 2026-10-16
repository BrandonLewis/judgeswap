# Hybrid retrieval: strictly non-negative, and only where exact terms live

*Lever 2b of the parity roadmap. Dense embeddings dilute rare tokens; a
lexical signal recovers them. The question was whether that was worth a
flag.*

## The hypothesis

Retrieval was pure dense cosine over pgvector with metadata pre-filters.
Dense embeddings average a chunk's tokens into one vector, so the tokens that
make a chunk distinctive (a proprietary product name, a penalty term, a
dollar figure) are the ones that get diluted. A query that literally contains
those words can fail to rank the chunk that literally contains them above
semantically adjacent neighbours. The standard remedy is to run a sparse,
term-matching search in parallel and fuse.

## The design

Native Postgres full-text search, nothing new to operate: a generated
`tsvector` column over chunk content with a GIN index, maintained by the
database and never written by application code. The sparse branch ranks with
`ts_rank` using `websearch_to_tsquery`, which tolerates any user text. Dense
and sparse each return 30 candidates and are fused with Reciprocal Rank
Fusion at k = 60, which operates on ranks only, so the two score scales never
meet and nothing needs normalising. Fused results keep their true cosine
distance so the existing library relevance gate keeps working, and carry an
`rrf_score` the downstream merge ranks by when present.

Behind a setting, default off. Off is byte-identical to the previous path.
If the sparse branch returns nothing, fusing with an empty list reproduces
the dense order, so the worst case is the status quo.

## The measurement

Retrieval only, no model generation, so no provider confound. Toggled the
flag in-process against the live 6,370-chunk library and a 204-chunk project
corpus with the same embeddings.

| probe | dense | hybrid |
|---|---|---|
| library recall@5, 7 curated natural-language queries | 7/7 | 7/7 |
| library recall@1 / @3 | 6/7, 7/7 | 6/7, 7/7 |
| project corpus, paraphrased briefing queries | — | identical ranks on every marquee fact |
| project corpus, exact-term queries | — | 2 of 6 improved, 0 regressed |

The two improvements are the whole story. A proprietary product name went
from dense rank 8 to hybrid rank 1. A bare section number went from 2 to 1.
Dense had spread the rare token across the embedding; full-text matched it
exactly; RRF pulled it to the top.

Nothing else moved, and nothing regressed across any probe. The briefing
queries are natural-language paraphrases ("mandated product brand model
manufacturer price") that dense already handles, and the facts they target
were already at ranks 5 to 8, inside the window.

**Decision: flag on.** Safe everywhere, wins on exact terms, instant revert.

## The follow-on it implied

If hybrid only helps when the query contains the rare token, give the queries
rare tokens. A deterministic expander now injects the special provisions'
amended section numbers into the two detail sections' queries. The first
source tried, major bid-item descriptions, was invalidated before shipping:
the "major item" flag was 0% populated across 7,379 bid items, so the
expander fell back to the first N items by line number, which are the same
general-conditions boilerplate on every project, and those displaced fact
chunks (retention fell from 3 of 6 to 1 of 6 as the cap rose). Amended
section numbers are project-specific by construction and populated in 92% of
corpora; with five of them injected, the detail sections gained two to three
amended-section chunks each while keeping their fact chunks.

## In the library

The fusion and the ORM are the product's. What this write-up contributes to
the library is a measurement habit: the retrieval change was validated on a
deterministic retrieval probe with the flag toggled in-process, not on the
LLM-judged harness, because generation noise would have swamped a rank-8 to
rank-1 move on one query.
