"""The parity loop: generate a candidate per section over a frozen context, score
it against a reference with the judge, run the swapped head-to-head, write one
JSONL row per section and a REPORT.md.

Freezing the context is the point. The reference was produced with the full
documents; the candidate sees only what retrieval actually returned, captured
once. Iterating prompts over that snapshot attributes every change in score to
the prompt, and the judge's ``ceiling_flags`` name the reference facts that
were never in the context at all, so a retrieval gap is not mistaken for a
prompt gap.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Section:
    """One unit of comparison: what the candidate may see, and what it is judged against."""

    context: str
    reference: str
    structured_data: Any = None
    retrieved_citations: list = field(default_factory=list)


class Judge(Protocol):
    def score(self, section_id, *, candidate, reference, context, structured_data=None) -> dict: ...

    def prefer(self, section_id, *, a, b, context) -> str: ...


# generate(section_id, section, variant_overrides) -> (markdown, citations)
Generate = Callable[[str, Section, Any], tuple[str, list]]


def footnote_key(value):
    """The int a footnote points at, or None.

    ``3``, ``"3"``, ``"[3]"`` and ``"[^3]"`` all name the context item numbered
    ``[3]``; anything else has no bracketed counterpart and cannot join.
    """
    try:
        return int(str(value).strip().strip("[]").lstrip("^"))
    except (TypeError, ValueError):
        return None


def ungrounded_citations(citations: list, retrieved: list, *, key: Callable = footnote_key) -> int:
    """How many citations name a footnote no retrieved item carries.

    A prose judge cannot see this failure: the markdown reads fine while the
    citation points at nothing. ``key`` is the join rule; pass the production
    one so the harness counts exactly what production would drop.
    """
    keyed = {key(c.get("footnote")) for c in retrieved} - {None}
    return sum(1 for c in citations if key(c.get("footnote")) not in keyed)


def run_parity(
    sections: Mapping[str, Section],
    *,
    generate: Generate,
    judge: Judge,
    artifact_dir: Path,
    variants: Mapping[str, Any] | None = None,
    axes: tuple[str, ...] | None = None,
    citation_key: Callable = footnote_key,
    label: Mapping[str, Any] | None = None,
) -> dict:
    """Run every (variant x section), write ``<variant>.jsonl`` and ``REPORT.md``.

    ``variants`` maps a name to whatever ``generate`` understands as overrides;
    ``{"baseline": None}`` when there is nothing to vary. ``axes`` defaults to
    the keys the judge's first successful score returns, minus the non-axis
    fields; pass the rubric's axes explicitly to pin the report columns.
    ``label`` is copied onto every row (a project id, a briefing type).

    Returns ``{variant: {mean_total, wins, ties, losses, ceiling_flag_count,
    citations, ungrounded_citations}}``.
    """
    variants = variants or {"baseline": None}
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    label = dict(label or {})

    aggregate = {}
    for variant_name, overrides in variants.items():
        rows = []
        for sid, section in sections.items():
            if not section.reference:
                continue
            cand_md, cand_citations = generate(sid, section, overrides)
            scores = judge.score(
                sid,
                candidate=cand_md,
                reference=section.reference,
                context=section.context,
                structured_data=section.structured_data,
            )
            if "error" not in scores:
                row_axes = axes or _axes_of(scores)
                total = statistics.mean(scores[a] for a in row_axes)
                h2h = _head_to_head(judge, sid, cand_md, section.reference, section.context)
            else:
                total, h2h = None, "error"
            rows.append(
                {
                    **label,
                    "variant": variant_name,
                    "section_id": sid,
                    "scores": scores,
                    "total": total,
                    "h2h": h2h,
                    "citations": len(cand_citations),
                    "ungrounded_citations": ungrounded_citations(
                        cand_citations, section.retrieved_citations, key=citation_key
                    ),
                    "candidate_md": cand_md,
                }
            )
        (artifact_dir / f"{variant_name}.jsonl").write_text(
            "".join(json.dumps(r, default=str) + "\n" for r in rows), encoding="utf-8"
        )
        aggregate[variant_name] = summarize(rows)

    write_parity_report(artifact_dir, axes=axes)
    return aggregate


def _head_to_head(judge, sid, candidate, reference, context) -> str:
    from .judging import head_to_head

    return head_to_head(lambda a, b: judge.prefer(sid, a=a, b=b, context=context), candidate, reference)


def _axes_of(scores: dict) -> tuple[str, ...]:
    return tuple(k for k, v in scores.items() if isinstance(v, int) and not isinstance(v, bool))


def summarize(rows: list[dict]) -> dict:
    totals = [r["total"] for r in rows if isinstance(r["total"], (int, float))]
    return {
        "mean_total": round(statistics.mean(totals), 3) if totals else 0.0,
        "wins": sum(1 for r in rows if r["h2h"] == "win"),
        "ties": sum(1 for r in rows if r["h2h"] == "tie"),
        "losses": sum(1 for r in rows if r["h2h"] == "loss"),
        "ceiling_flag_count": sum(
            len(r["scores"].get("ceiling_flags", [])) for r in rows if "error" not in r["scores"]
        ),
        "citations": sum(r["citations"] for r in rows),
        "ungrounded_citations": sum(r["ungrounded_citations"] for r in rows),
    }


def write_parity_report(
    artifact_dir: Path, *, axes: tuple[str, ...] | None = None, title="Parity Report"
) -> Path | None:
    """Aggregate every ``*.jsonl`` under ``artifact_dir`` into ``REPORT.md``."""
    from .report import read_jsonl_dir

    artifact_dir = Path(artifact_dir)
    rows = read_jsonl_dir(artifact_dir)
    if not rows:
        return None
    if axes is None:
        scored = next((r["scores"] for r in rows if "error" not in r["scores"]), None)
        axes = _axes_of(scored) if scored else ()
    head = ["variant", "section", *axes, "total", "h2h", "ceiling flags", "cites", "ungrounded"]
    lines = [f"# {title}", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        s = r["scores"]
        cites = r.get("citations", "—")
        ungrounded = r.get("ungrounded_citations", "—")
        if "error" in s:
            cells = [r["variant"], r["section_id"], *(["—"] * len(axes)), "err", r["h2h"], "—", cites, ungrounded]
        else:
            total = r["total"]
            cells = [
                r["variant"],
                r["section_id"],
                *(s.get(a, "—") for a in axes),
                f"{total:.2f}" if total is not None else "—",
                r["h2h"],
                len(s.get("ceiling_flags", [])),
                cites,
                ungrounded,
            ]
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    path = artifact_dir / "REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
