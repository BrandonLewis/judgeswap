# Un-starving the library: additive retrieval, multi-query, and the cost of more context

*Lever A of the parity roadmap. The oracle knew standard-specification facts
the candidate never saw, and the reason was a branch that never ran.*

## The bug

Project briefings retrieved from two corpora: the project's own special
provisions and an agency library of standard specifications. The library was
consulted as a fallback, only when the project corpus returned fewer than
`top_k` chunks. The project corpus had 62 chunks and `top_k` was 10 to 30.
The condition was never true. The library held the sections the oracle was
citing (one of them with over fifty chunks) and none of it ever reached a
briefing.

Context was not the constraint. The largest section used about 10k tokens of
a 131k window, under 8%. Selection was.

## The change

Three things, behind one method:

- **Additive blend.** Project results are kept whole and surviving library
  results are appended, instead of the library filling a remainder that was
  always zero. Two existing suppressions still apply to the library side: a
  standard section the special provisions amend is dropped (the project copy
  wins), and sections the provisions explicitly modify are excluded.
- **Focused multi-query.** One broad query per section collapses to one
  average meaning. Each detail section now issues several focused queries
  (penalties, mandated products, schedule milestones, testing thresholds),
  unioned, deduplicated by chunk id keeping the best distance, and ranked.
- **A seam.** The query list comes from a one-method expander so an LLM
  expander can replace the hand-written lists later without touching callers.

## What the harness said

Prompts held at v1 throughout; same contract, same oracle.

| config | mean | W/T/L | ceiling flags | note |
|---|---|---|---|---|
| old retrieval | 3.71 | 5/1/0 | 44 | library never reached |
| additive blend, every section | 3.50 | 5/0/1 | 43 | one section generated empty; broad sections noisy |
| additive blend, detail sections only (shipped) | 3.71 | 3/2/1 | 42 | |

Per section under the shipped configuration: key specifications 3.50 to 4.00,
risks 3.50 to 3.75, both at grounding and citation 5 of 5, with standard-spec
facts now present in the generated text. The broad scope-of-work section
recovered fully once the library was taken away from it again.

## The finding worth keeping

More context made generation worse, in two different ways.

The scope section's context grew to about 50k characters across 60 chunks
and the model returned nothing. Caps fixed it: 35 chunks per section, a
library cap of 10, and a cosine-distance gate on library hits (0.6) so weak
matches do not fill the window.

Fixed fact-type queries pulled off-topic but well-matching library content
onto broad sections (a drainage-concrete standard onto a signs project). So
the library is applied selectively, to the detail sections where facts live,
and not to the sections that summarise.

Coverage stayed capped at 2 even with the facts present. That pointed at the
prompt, so a prompt re-tune was measured next and rejected: it surfaced one
extra in-context fact, dragged in peripheral language, and dropped
specificity from 4 to 2. The prompt lever was exhausted. The remaining gap
was ingestion: the structured parser captured only the 62 amendment blocks
of the special provisions and the oracle's marquee facts lived in the text
between them. Windowing that uncaptured text and embedding it alongside the
structured chunks moved the mean from 3.71 to 3.96 and the risks section's
ceiling flags from 7 to 4. The same "more is worse" rule applied there too:
windows that re-covered already-captured sections diluted a broad section
from 3.25 to 2.25 until they were dropped.

## In the library

Nothing in this write-up is library code; the retrieval is the product's ORM.
What the library carries is what made the measurement possible: the frozen
context, the judge, the swap, the ceiling flags, and the ungrounded-citation
count that caught a footnote contract no prose score showed.
