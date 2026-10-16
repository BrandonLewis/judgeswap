"""Set-level candidate-vs-baseline diff on normalized identifiers.

Surfaces deltas; it does not rule better or worse, because the baseline may
itself be the suspect older extraction. ``dropped`` is None when only some
pages were run (absence is not a miss) and the baseline-minus-candidate set
when the whole document was.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class SetDelta:
    matched: set[str]
    added: set[str]
    dropped: set[str] | None  # None: suppressed (partial run)

    @property
    def n_matched(self) -> int:
        return len(self.matched)

    @property
    def n_added(self) -> int:
        return len(self.added)

    @property
    def n_dropped(self) -> int:
        return len(self.dropped or ())


def diff_sets(*, candidate: set[str], baseline: set[str], full: bool) -> SetDelta:
    return SetDelta(
        matched=candidate & baseline,
        added=candidate - baseline,
        dropped=(baseline - candidate) if full else None,
    )


def normalize_ref(ref: str | None, *, strip_prefixes: tuple[str, ...] = ("section",)) -> str:
    """Canonical form of an identifier for set comparison: a leading word from
    ``strip_prefixes`` removed, whitespace collapsed, upper-cased.

    Within one numbering system only. Two spellings of the same reference
    compare equal; equivalence across systems is not attempted.
    """
    if not ref:
        return ""
    s = ref
    for prefix in strip_prefixes:
        s = re.sub(rf"^\s*{re.escape(prefix)}\s+", "", s, flags=re.IGNORECASE)
    return _WS.sub(" ", s).strip().upper()
