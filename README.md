# judgeswap

Evaluation harness pieces for LLM generation pipelines, lifted from a
product that spent five months measuring itself against a full-document
oracle. No framework, no network: a model is any object with
`complete(prompt) -> str`, and the only files written are in the artifact
directory you name.

```bash
pip install judgeswap
```

## What is in it

| module | what it does |
|---|---|
| `judgeswap.judging` | `Rubric` (prompt templates plus validation), `RubricJudge` (score and prefer through your client), `parse_judge_json` (every axis an in-range int, `true` refused, malformed extras coerced), `head_to_head` (position-swapped preference). |
| `judgeswap.parity` | `run_parity`: generate a candidate per section over a frozen context, score it against a reference, swap-judge it, write one JSONL row per section and a `REPORT.md`. `ungrounded_citations` counts footnotes no retrieved item carries, with your join rule. |
| `judgeswap.structured` | `extract_structured`: bare, fenced or prose-wrapped JSON, `<think>` blocks stripped, optional `KEY: VALUE` fallback, an error envelope instead of an exception. `mean_axes`. |
| `judgeswap.floors` | `Model(runtime, name)` and regression floors keyed on (model, task); a combination without a floor is soft, recorded and never failing. |
| `judgeswap.setdiff` | `diff_sets` (matched / added / dropped, with dropped suppressed on a partial run) and `normalize_ref`. |
| `judgeswap.report` | JSONL in, Markdown tables out: `write_matrix_report`, `render_delta_table`. |
| `judgeswap.embeddings` | Offline embedding-model A/B: `cosine_rank`, `recall_pass`, `domain_separation`, `run_ab` (a failing backend is skipped, a short result is refused), a recommendation with a migration bar. |

## Sixty seconds

```python
from judgeswap import Rubric, RubricJudge, Section, run_parity

class Client:                       # anything with complete(prompt) -> str
    def complete(self, prompt: str) -> str:
        return my_model(prompt)

judge = RubricJudge(Client(), Rubric())   # or Rubric(score_template=..., preference_template=...)

sections = {
    "risks": Section(context=frozen_context, reference=oracle_markdown,
                     structured_data=facts, retrieved_citations=cites),
}

def generate(section_id, section, overrides):
    prompt = render(section_id, section.context, override=overrides and overrides.get(section_id))
    return my_model(prompt), []       # (markdown, citations)

summary = run_parity(sections, generate=generate, judge=judge,
                     artifact_dir="out/", variants={"baseline": {}, "v2": {"risks": V2_TEMPLATE}})
# out/baseline.jsonl, out/v2.jsonl, out/REPORT.md
# summary["v2"] -> {"mean_total": 3.9, "wins": 1, "ties": 0, "losses": 0, "ceiling_flag_count": 4, ...}
```

The swap in one line:

```python
from judgeswap import head_to_head
head_to_head(lambda a, b: "A", candidate, reference)   # -> "tie": a judge that always says A proves nothing
```

## Why these pieces

- **Freeze the context.** The reference was written with the whole document;
  the candidate sees what retrieval returned, captured once. Prompt changes
  are then attributable to the prompt, and the judge's `ceiling_flags` name
  the facts no prompt could have used.
- **Swap the positions.** Judges prefer slot A. Judged in both slots, a
  candidate wins only when preferred in both, and a biased judge scores a tie.
- **Validate the judge.** A `true` is not a 1. A flags list returned as a
  string is not a list of flags. A truncated JSON is an error row, not a zero.
- **Key floors on the runtime.** The same weights behave differently per
  serving stack; a floor on a bare model name blames the wrong thing.
- **Count what prose cannot show.** A citation to a footnote that nothing
  retrieved reads fine and grounds nothing.

The experiments that shaped these are written up in [`docs/`](docs/README.md):
a retrieval branch that never ran, an embedding A/B that correctly returned
"no", a hybrid-retrieval flag that only moves exact-term queries, and a
regression guard whose first failure was in the grader.

## Not in it

Model clients, storage, a database, a CLI, or anything that knows your
domain. The default rubric is generic on purpose; pass your own templates.

## Development

```bash
pip install -e '.[test]' black ruff
pytest
```

See `CONTRIBUTING.md`. Security reports: `SECURITY.md`. Apache-2.0.
