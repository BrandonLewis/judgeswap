"""LLM-as-judge: rubric scoring, pairwise preference, and position-swapped head-to-head.

The judge is any object with ``complete(prompt: str) -> str``. The library
never opens a connection itself, so the same code runs against a hosted API,
a local server, or a stub in a test.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

DEFAULT_AXES: tuple[str, ...] = ("grounding", "coverage", "specificity", "citation_accuracy")

_DEFAULT_SCORE_TEMPLATE = """You are grading a CANDIDATE answer against a REFERENCE produced by a system
that read the full source documents. The candidate was allowed to use two inputs: the
CONTEXT (retrieved excerpts) and the STRUCTURED DATA (verified facts the candidate may
state without a citation).

Score the CANDIDATE on each axis, integer {lo}-{hi} ({hi} best):
- grounding: every claim is supported by CONTEXT or STRUCTURED DATA; no hallucination.
- coverage: captures the load-bearing facts the REFERENCE captures.
- specificity: concrete numbers, dates and identifiers rather than vague prose.
- citation_accuracy: cited identifiers actually support the adjacent claim.

Then list ceiling_flags: REFERENCE facts that are present in NEITHER the CONTEXT nor the
STRUCTURED DATA (these are retrieval limitations the candidate cannot fix; do not
penalize grounding for them).

Section: {section_id}

STRUCTURED DATA (verified, citation-free facts available to the candidate):
{structured_data}

CONTEXT:
{context}

REFERENCE:
{reference}

CANDIDATE:
{candidate}

Return JSON only:
{{"grounding":int,"coverage":int,"specificity":int,"citation_accuracy":int,
"ceiling_flags":[string,...],"rationale":string}}"""

_DEFAULT_PREFERENCE_TEMPLATE = """Two answers, A and B, for the same section "{section_id}". Using the CONTEXT
as the source of truth, which is the better answer for the reader (more grounded,
specific, and complete)?

CONTEXT:
{context}

A:
{a}

B:
{b}

Answer with exactly one token: A, B, or tie."""


class JudgeClient(Protocol):
    """The one call the library makes: a prompt in, the model's text out.

    Raise on transport or API failure; the caller turns that into an error
    row rather than a score.
    """

    def complete(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class Rubric:
    """What the judge is asked and how its answer is validated.

    ``axes`` are the integer-scored fields the score prompt must return;
    ``scale`` is their inclusive range. The templates take the named fields
    shown in the defaults. A product substitutes its own wording (the default
    text knows nothing about any domain) and keeps the validation.
    """

    axes: tuple[str, ...] = DEFAULT_AXES
    scale: tuple[int, int] = (1, 5)
    score_template: str = _DEFAULT_SCORE_TEMPLATE
    preference_template: str = _DEFAULT_PREFERENCE_TEMPLATE

    def score_prompt(self, section_id, candidate, reference, context, structured_data=None) -> str:
        return self.score_template.format(
            section_id=section_id,
            context=context,
            structured_data=format_structured(structured_data),
            reference=reference,
            candidate=candidate,
            lo=self.scale[0],
            hi=self.scale[1],
        )

    def preference_prompt(self, section_id, a, b, context) -> str:
        return self.preference_template.format(section_id=section_id, context=context, a=a, b=b)


def format_structured(structured_data) -> str:
    if not structured_data:
        return "(none for this section)"
    return json.dumps(structured_data, indent=2, default=str)


def parse_judge_json(raw, axes: tuple[str, ...] = DEFAULT_AXES, scale: tuple[int, int] = (1, 5)) -> dict | None:
    """The judge's JSON as a dict, or None when it is not a usable score.

    Tolerates a code fence and prose around the object. Every axis must be an
    int inside ``scale``; a bool is refused even though it is an int subclass,
    so a judge answering ``true`` cannot be read as a 1. ``ceiling_flags`` and
    ``rationale`` are coerced to a list and a string, because a judge that
    returns them as null or a bare string must not be miscounted downstream
    (``len("...")``).
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text.split("\n", 1)[-1]
        text = text.strip("`").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s == -1 or e <= s:
            return None
        try:
            data = json.loads(text[s : e + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    lo, hi = scale
    for axis in axes:
        v = data.get(axis)
        if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
            return None
    cf = data.get("ceiling_flags", [])
    data["ceiling_flags"] = cf if isinstance(cf, list) else []
    rat = data.get("rationale", "")
    data["rationale"] = rat if isinstance(rat, str) else ("" if rat is None else str(rat))
    return data


def parse_preference(raw) -> str:
    """``"A"``, ``"B"`` or ``"tie"`` from a one-token preference answer."""
    tok = (raw or "").strip().lower()[:4]
    if tok.startswith("a"):
        return "A"
    if tok.startswith("b"):
        return "B"
    return "tie"


def head_to_head(prefer: Callable[[str, str], str], candidate: str, reference: str) -> str:
    """Position-swapped preference: ``"win"``, ``"loss"`` or ``"tie"``.

    ``prefer(a, b)`` returns the POSITIONAL letter the judge chose. The
    candidate is shown in slot A and then in slot B. It wins only if it is
    preferred in both orderings and loses only if it is rejected in both;
    anything else is a tie. Swapping cancels position bias: a judge that
    always answers "A" (pure positional bias, no content discrimination)
    yields a tie, while a genuinely better candidate yields ["A", "B"] and a
    win.
    """
    as_a = prefer(candidate, reference)
    as_b = prefer(reference, candidate)
    cand_won = (as_a == "A") + (as_b == "B")
    cand_lost = (as_a == "B") + (as_b == "A")
    if cand_won == 2:
        return "win"
    if cand_lost == 2:
        return "loss"
    return "tie"


@dataclass
class RubricJudge:
    """A judge built from a client and a rubric.

    ``score`` returns the validated rubric dict or ``{"error": ...}``;
    ``prefer`` returns the positional letter, and a failed call is a ``"tie"``
    rather than a letter, because an error message that happens to start with
    "A" or "B" must not count as a preference.
    """

    client: JudgeClient
    rubric: Rubric = field(default_factory=Rubric)

    def score(self, section_id, *, candidate, reference, context, structured_data=None) -> dict:
        prompt = self.rubric.score_prompt(section_id, candidate, reference, context, structured_data)
        try:
            raw = self.client.complete(prompt)
        except Exception as exc:  # the client is the caller's; any failure is an error row
            return {"error": f"judge call failed: {exc}"}
        parsed = parse_judge_json(raw, self.rubric.axes, self.rubric.scale)
        if parsed is None:
            return {"error": "judge returned unparseable JSON", "raw": (raw or "")[:500]}
        return parsed

    def prefer(self, section_id, *, a, b, context) -> str:
        prompt = self.rubric.preference_prompt(section_id, a, b, context)
        try:
            raw = self.client.complete(prompt)
        except Exception:
            return "tie"
        return parse_preference(raw)

    def head_to_head(self, section_id, *, candidate, reference, context) -> str:
        return head_to_head(lambda a, b: self.prefer(section_id, a=a, b=b, context=context), candidate, reference)
