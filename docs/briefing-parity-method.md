# Measuring a RAG briefing against a full-document oracle

*The method behind `judgeswap.parity`. The product generated per-section
briefings over retrieved chunks of a bid package; the question was how far
those sat from what a system reading the whole documents would write, and
which half of the gap the prompt could close.*

## The setup

Each briefing type is a list of sections. A section is a small RAG pipeline:
structured facts from the agency listing, top-k retrieved chunks, a prompt
template, one model call, JSON out with markdown and citations. Three things
could be wrong with a weak section and they need different fixes: the
retrieval did not return the fact, the prompt did not make the model use it,
or the model made something up. A single score cannot tell them apart.

## The oracle

NotebookLM was given the full Special Provisions and the conformed plans for
one Caltrans contract and the same per-section instructions the product's
model receives, minus the JSON output contract. Its answers were saved as a
fixture. Its only advantage over the candidate is the whole document, which is
exactly the ceiling worth measuring against. The oracle was captured once, so
the reference is frozen and the run is reproducible; re-capturing is a
deliberate, versioned act.

## Freezing retrieval

The candidate's context (structured data, context string, retrieved citations)
was captured once per section from production and committed. Every prompt
variant then generates over the same snapshot. A change in score is a change
in the prompt, not in what retrieval happened to return that day.

## The judge

A model from a different family than the candidate generator scores each
section on four integer axes, 1 to 5: grounding, coverage, specificity,
citation accuracy. It also returns `ceiling_flags`: facts in the reference
that appear in neither the context nor the structured data. Those are
retrieval-bound; the judge is told not to penalise grounding for them.

The judge's JSON is validated, not trusted. Every axis must be an int in
range; a `true` is refused rather than read as a 1; `ceiling_flags` returned
as a string or null becomes an empty list so that `len()` downstream counts
facts, not characters.

Two judge-side defects were found by looking at rows that made no sense:

- The judge first saw only the retrieved context, so it flagged legitimate
  structured-data facts (bid date, engineer's estimate, participation goal) as
  hallucinations and inflated the ceiling count. Giving it the structured data
  dropped baseline ceiling flags from 56 to 44.
- The judge's output budget was 1,500 tokens. Sections with many ceiling
  facts produced arrays that truncated mid-JSON, which parsed as "unparseable"
  and scored as a section error that looked like a candidate failure. Raised
  to 4,000.

## Position-swapped head-to-head

Pairwise preference is cheap and intuitive and judges prefer slot A. The
candidate is therefore judged twice, once in each slot. It wins only if
preferred in both orderings and loses only if rejected in both. A judge with
pure position bias and no content discrimination answers "A" both times and
scores a tie, which is the point of swapping. The original formula got this
wrong and was corrected; a test now asserts that a judge that always answers
"A" produces a tie.

## What a prose judge cannot see

A citation that points at a footnote no retrieved chunk carries reads fine
and grounds nothing. The harness counts those directly, with the same join
rule production uses to drop them. One variant left 15.6% of its citations
unable to join any chunk and no prose score moved.

## What it measured

Baseline to one round of prompt iteration, six sections, one contract:

| metric | baseline | v1 |
|---|---|---|
| mean total (of 5) | 2.50 | 3.71 |
| head-to-head W/T/L vs oracle | 4/0/2 | 5/1/0 |

The three tuned sections moved by 1.75 to 2.0 points; untuned sections moved
within the regeneration-noise band (about 1.25). The gains were structural
(grounding and citation 2 to 5; an empty section became a correct one), not
judge noise. Coverage barely moved, and the ceiling flags said why: 44
reference facts were not in the retrieved context for any prompt to use. The
gap was retrieval-dominated, which is what the next three write-ups are about.

## What ported to the library

`Rubric` holds the templates and validation; `RubricJudge` turns any
`complete(prompt) -> str` client into a scorer and a preference judge;
`head_to_head` is the swap; `run_parity` is the loop, writing one JSONL row
per section and a report; `ungrounded_citations` takes the caller's join rule.
The rubric wording that names the domain stayed in the product.
