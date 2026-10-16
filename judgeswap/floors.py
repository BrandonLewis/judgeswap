"""Regression floors keyed on (runtime, model, task).

A model is a ``(runtime, name)`` pair, not a bare name: the same weights
behave differently per serving stack (one runtime returns 400 in tools mode
where another does not; two stacks serve different quantizations), so a
floor or a known-dead entry on the name alone would blame the wrong thing.

A combination with a floor FAILS when it scores below it; a combination
without one is soft, recorded and reported but never failing. Production
winners get floors; everything else is iteration data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Model:
    """A specific model on a specific runtime; the quantization belongs in ``name``
    when the runtime does not fix it."""

    runtime: str
    name: str

    def __str__(self) -> str:
        return f"{self.runtime}:{self.name}"


def floor_for(floors: Mapping[tuple[Model, str], float], model: Model, task: str) -> float | None:
    """The floor for ``(model, task)``, or None when the combination is soft."""
    return floors.get((model, task))


def check_floor(total: float, floor: float | None) -> bool | None:
    """True/False against a floor; None when there is no floor (soft)."""
    if floor is None:
        return None
    return total >= floor


def skip_reason(dead: Mapping[tuple[Model, str], str], model: Model, mode: str) -> str | None:
    """Why ``(model, mode)`` is known not to run, or None. Entries come from
    observed failures, never speculation."""
    return dead.get((model, mode))
