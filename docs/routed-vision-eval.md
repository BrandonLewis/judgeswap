# A regression guard for a prompt router, and the grader bug it found

*The vision-model matrix measured prompts fed straight to a model. A fix
that lived in the code between the PDF and the prompt was invisible to it.*

## The fix that could not be tested

One open-weights vision model confabulated whole paragraphs on an addendum
page of a specification. The page said "Replace section 5-1.13E with:"; the
general spec-page prompt treated it as spec content and invented the
replacement. An addendum-specific prompt extracted it cleanly. Production
gained a deterministic router: read the page's text layer, and if it carries a
modification verb, send the addendum prompt instead.

The eval matrix parametrised over (model, prompt, mode, page) and sent each
prompt directly. Re-running it on the branch produced the same numbers as
before, because the router never ran. A fix with no test that fails without
it is a fix that will be undone by accident.

## The cell

A new eval cell per page mirrors production end to end: extract the text
layer, run the router, send the chosen prompt against the rendered image,
then normalise both prompts' outputs into the one shape the existing grader
understands. The addendum prompt returns `operations[].target`; the spec
prompt returns `sections_on_page[].section_ref`; the normaliser maps both to
section references and implies the page type from the presence of operations.
Ground truth is per page and identical for both routes: the truth about a page
does not depend on which prompt read it. The router's decision is logged in
the artifact row but not graded; its unit tests cover that. The cell grades
the answer.

The regression floor was set from evidence before the run: the model's mean
on these five pages had been 0.60 with the addendum page at 0.00, the prompt
swap had lifted that page to about 1.0, so the expected mean was about 0.80.
A floor of 0.70 leaves one page of ground-truth noise and is still a
meaningful 0.20 above the general prompt's floor of 0.50. Floors are keyed on
(runtime, model, task): the same weights behave differently per serving stack,
and a floor on the bare model name would blame the wrong thing.

## First run

| page | routed to | score | note |
|---|---|---|---|
| 4 | spec page | 1.00 | |
| 8 | spec page | 1.00 | |
| 10 | spec page | 1.00 | |
| 12 | addendum | 0.50 | missing expected section ref `1-1.01`; got `section 1-1.01` |
| 18 | addendum | 1.00 | |

Page 12 tripped the floor. The routing was right and the extraction was
right. The model wrote `section 1-1.01` where the ground truth listed the
prefix `1-1.01`, and the grader's prefix check did not strip the leading
word. The fix went into the grader: normalise a leading "section" before the
comparison. Every cell then scored 1.00, mean 1.00, 0.30 of headroom over
the floor, and the floor stayed where the evidence had put it.

The same grader later gave up a second false negative. A bid-item list page
has a titled table and no section number; every model answered correctly
with a block whose section reference was null, and the scorer counted the
null as an extra reference, costing every model half a cell. Only a claimed,
non-blank reference now counts against a page that has no numbered section.

## What the guard catches

Someone weakens the router and the addendum page falls back to the general
prompt. Someone breaks the text-layer extraction that feeds the router. The
addendum prompt itself regresses. Any of those drops the addendum pages and
the mean crosses the floor.

What it does not catch, stated rather than hidden: a router false positive.
None of the five pages contains modification-verb phrasing that should *not*
route to the addendum prompt, so a page that merely says "see section 5-1.13"
is not in the sample. Adding one is the next cell.

## In the library

`extract_structured` is the parser that accepted three output shapes (bare
JSON, fenced, and KEY: VALUE), reasoning blocks and prose preambles, and
returned an error envelope the grader could score instead of raising.
`mean_axes` is the finaliser. `Model`, `floor_for` and `check_floor` are the
floors. `normalize_ref` is the "section" strip. The scorers that know what a
spec page or a title block looks like stayed in the product.
