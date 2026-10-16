"""Human-facing output: JSONL artifacts in, tables out."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path

from .setdiff import SetDelta


def read_jsonl_dir(artifact_dir: Path, pattern: str = "*.jsonl") -> list[dict]:
    """Every row of every matching file under ``artifact_dir``, in file order."""
    rows = []
    for path in sorted(Path(artifact_dir).glob(pattern)):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, row: dict) -> None:
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def render_matrix_report(
    rows: Iterable[dict],
    *,
    group_by: tuple[str, ...] = ("prompt_key", "runtime", "model", "mode"),
    floor_of: Callable[[dict], float | None] | None = None,
    title: str = "Eval Report",
) -> str:
    """One table row per distinct ``group_by`` tuple: n, parsed, mean total, mean wall, floor.

    Rows carry ``parsed_ok``, ``score.total`` and ``wall_elapsed_s``; a missing
    field counts as absent rather than failing the report. ``floor_of`` maps
    a representative row to its floor, or None for a soft combination.
    """
    by_combo: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_combo[tuple(r.get(k, "unknown") for k in group_by)].append(r)

    head = [*group_by, "n", "parsed", "mean total", "mean wall", "hard threshold"]
    lines = [f"# {title}", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for key in sorted(by_combo, key=str):
        cells = by_combo[key]
        parsed = sum(1 for c in cells if c.get("parsed_ok"))
        totals = [c["score"]["total"] for c in cells if isinstance(c.get("score"), dict) and "total" in c["score"]]
        walls = [c["wall_elapsed_s"] for c in cells if isinstance(c.get("wall_elapsed_s"), (int, float))]
        floor = floor_of(cells[0]) if floor_of else None
        lines.append(
            "| " + " | ".join(str(k) for k in key) + f" | {len(cells)} | {parsed}/{len(cells)} | "
            f"{(statistics.mean(totals) if totals else 0):.2f} | "
            f"{(statistics.mean(walls) if walls else 0):.0f}s | {floor if floor is not None else 'soft'} |"
        )
    return "\n".join(lines) + "\n"


def write_matrix_report(artifact_dir: Path, **kwargs) -> Path | None:
    """``render_matrix_report`` over every ``*.jsonl`` in ``artifact_dir``, to ``REPORT.md``."""
    rows = read_jsonl_dir(artifact_dir)
    if not rows:
        return None
    path = Path(artifact_dir) / "REPORT.md"
    path.write_text(render_matrix_report(rows, **kwargs), encoding="utf-8")
    return path


def render_delta_table(
    *,
    step: str,
    subject: str,
    model: str,
    baseline_id: str,
    baseline_is_current: bool,
    full: bool,
    per_page: dict[int, list[str]],
    delta: SetDelta,
) -> str:
    """The stdout table for a candidate-vs-baseline run: refs per page, then the
    matched/added/dropped line, with a caveat when the baseline is the current
    production output (deltas are then changes, not verified regressions)."""
    mode = "full-document" if full else "page-scoped"
    cur = " (current)" if baseline_is_current else ""
    lines = [
        f"{step} · {subject} · {model} · vs baseline {baseline_id}{cur} · {mode}",
        " page  refs produced",
    ]
    for page in sorted(per_page):
        lines.append(f" p{page:<4} {', '.join(per_page[page]) or '(none)'}")
    lines.append(" " + "-" * 46)
    dropped = (
        f"dropped {delta.n_dropped}"
        if delta.dropped is not None
        else "dropped n/a (page-scoped — not-run pages excluded)"
    )
    added = sorted(delta.added)
    added_detail = f" ({', '.join(added)})" if added else ""
    lines.append(f" matched {delta.n_matched}   added {delta.n_added}{added_detail}   {dropped}")
    if baseline_is_current:
        lines.append(" baseline is the CURRENT set — deltas are CHANGES, not verified regressions.")
    return "\n".join(lines)
