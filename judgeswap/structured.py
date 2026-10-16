"""Robust parsing of structured model output, and the mean-of-axes finalizer.

Models emit JSON in several shapes: bare, inside a ``` fence, after a prose
preamble, or (when asked) as KEY: VALUE lines. Smaller models prepend
``<think>...</think>`` reasoning. All of those parse; gibberish and an empty
object are a parse failure, reported as an envelope the grader can score
uniformly instead of an exception.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_KV_LINE = re.compile(r"^\s*([A-Z_]+)\s*:\s*(.+?)\s*$")


def extract_structured(raw: str, *, keyvalue: Mapping[str, str] | None = None) -> tuple[bool, object]:
    """Parse a model response into a non-empty dict.

    Returns ``(ok, parsed_or_error_envelope)``; the envelope has ``error`` and
    ``raw_head``. ``keyvalue`` enables the ``KEY: VALUE`` fallback for prompts
    that ask for it: a map from the KEY the model writes to the field name the
    parsed dict should carry. At least two keys must match for the fallback to
    count as a parse.
    """
    if not raw:
        return False, {"error": "empty response", "raw_head": ""}
    cleaned = _THINK_BLOCK.sub("", raw).strip()

    m = _CODE_FENCE.search(cleaned)
    candidate = m.group(1).strip() if m else cleaned

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict) and parsed:
            return True, parsed
        if isinstance(parsed, dict):
            return False, {"error": "empty JSON object", "raw_head": raw[:300]}
    except json.JSONDecodeError:
        pass

    if "{" in candidate and "}" in candidate:
        sliced = candidate[candidate.index("{") : candidate.rindex("}") + 1]
        try:
            parsed = json.loads(sliced)
            if isinstance(parsed, dict) and parsed:
                return True, parsed
        except json.JSONDecodeError:
            pass

    if keyvalue:
        kv = parse_keyvalue(raw, keyvalue)
        if kv is not None:
            return True, kv

    return False, {"error": "no parseable structure found", "raw_head": raw[:300]}


def parse_keyvalue(raw: str, keys: Mapping[str, str], *, minimum: int = 2) -> dict | None:
    """``KEY: VALUE`` lines into ``{keys[KEY]: VALUE}``; None below ``minimum`` matches."""
    out: dict = {}
    for line in raw.splitlines():
        m = _KV_LINE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key in keys:
            out[keys[key]] = val
    return out if len(out) >= minimum else None


def mean_axes(score: dict, *, exclude: tuple[str, ...] = ("notes",)) -> dict:
    """Add ``total``: the unweighted mean of every numeric axis in ``score``."""
    axes = [v for k, v in score.items() if k not in exclude and k != "total"]
    score["total"] = sum(axes) / max(1, len(axes))
    return score
