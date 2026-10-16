"""Offline embedding-model A/B: rank a labelled corpus with each candidate
backend, score recall@k and domain separation, recommend.

A backend is any object with ``name`` and ``embed(texts, input_type) ->
list[list[float]]``; ``input_type`` is ``"document"`` or ``"query"`` so an
asymmetric model is encoded the way it was trained. Chunks are dicts with
``content`` and whatever ``label_of`` reads a label from.
"""

from __future__ import annotations

import json
import logging
import statistics
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)

LabelOf = Callable[[dict], str]


def default_label_of(chunk: dict) -> str:
    return str((chunk.get("metadata") or {}).get("label", ""))


@dataclass(frozen=True)
class EvalQuery:
    """A query with its ground truth: the labels a relevant chunk carries and
    the keywords the combined top-k content must contain."""

    name: str
    query: str
    expected_labels: set = field(default_factory=set)
    expected_keywords: list = field(default_factory=list)


class EmbeddingBackend(Protocol):
    name: str

    def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]: ...


def cosine_rank(query_vec, chunk_vecs) -> list[tuple[int, float]]:
    """``(chunk index, cosine similarity)`` best first."""
    q = np.asarray(query_vec, dtype=float)
    m = np.asarray(chunk_vecs, dtype=float)
    qn = q / (np.linalg.norm(q) or 1.0)
    mn = m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)
    sims = mn @ qn
    order = np.argsort(-sims)
    return [(int(i), float(sims[i])) for i in order]


def recall_pass(expected_labels, expected_keywords, top_chunks, *, label_of: LabelOf = default_label_of) -> bool:
    """At least one top chunk carries an expected label AND every keyword
    appears somewhere in the combined top content."""
    expected_labels = set(expected_labels)
    seen = {label_of(c) for c in top_chunks}
    if not (seen & expected_labels):
        return False
    combined = "\n".join(c.get("content", "") for c in top_chunks).lower()
    return all(kw.lower() in combined for kw in expected_keywords)


def domain_separation(expected_labels, top_chunks, *, label_of: LabelOf = default_label_of) -> float:
    """Mean similarity of on-topic top chunks minus mean of off-topic ones;
    0.0 when either group is empty. The discriminating metric once recall
    saturates."""
    expected_labels = set(expected_labels)
    on = [c["similarity"] for c in top_chunks if label_of(c) in expected_labels]
    off = [c["similarity"] for c in top_chunks if label_of(c) not in expected_labels]
    if not on or not off:
        return 0.0
    return sum(on) / len(on) - sum(off) / len(off)


def run_ab(
    backends: Iterable[EmbeddingBackend],
    chunks: list[dict],
    queries: list[EvalQuery],
    *,
    top_k: int = 5,
    label_of: LabelOf = default_label_of,
) -> dict:
    """``{backend.name: {dim, recall_passed, recall_total, per_query, mean_separation}}``.

    A backend that raises, or returns the wrong number of vectors, is logged
    and skipped: one bad endpoint must not sink the others, and a short
    result must not be zipped into corrupt metrics.
    """
    contents = [c["content"] for c in chunks]
    results = {}
    for backend in backends:
        try:
            chunk_vecs = backend.embed(contents, input_type="document")
            query_vecs = backend.embed([q.query for q in queries], input_type="query")
            if len(chunk_vecs) != len(contents) or len(query_vecs) != len(queries):
                raise ValueError(
                    f"shape mismatch: {len(chunk_vecs)}/{len(contents)} chunks, "
                    f"{len(query_vecs)}/{len(queries)} queries"
                )
            per_query, seps, passed = {}, [], 0
            for q, qv in zip(queries, query_vecs, strict=True):
                top = []
                for idx, sim in cosine_rank(qv, chunk_vecs)[:top_k]:
                    c = dict(chunks[idx])
                    c["similarity"] = sim
                    top.append(c)
                ok = recall_pass(q.expected_labels, q.expected_keywords, top, label_of=label_of)
                per_query[q.name] = ok
                passed += int(ok)
                seps.append(domain_separation(q.expected_labels, top, label_of=label_of))
        except Exception:
            logger.warning(
                "embedding A/B: backend %s failed, skipping", getattr(backend, "name", backend), exc_info=True
            )
            continue
        results[backend.name] = {
            "dim": len(chunk_vecs[0]) if chunk_vecs else None,
            "recall_passed": passed,
            "recall_total": len(queries),
            "per_query": per_query,
            "mean_separation": round(statistics.mean(seps), 4) if seps else 0.0,
        }
    return results


def recommendation(results: dict, *, baseline: str, separation_margin: float = 0.02) -> str:
    """Best by recall, tie-broken by separation; a candidate must beat the
    baseline by an extra passed query or by ``separation_margin`` to be
    recommended, because a migration costs more than a rounding error."""
    if not results:
        return "No backends ran — nothing to recommend."
    ranked = sorted(results.items(), key=lambda kv: (kv[1]["recall_passed"], kv[1]["mean_separation"]), reverse=True)
    best_name, best = ranked[0]
    base = results.get(baseline)
    if best_name == baseline or base is None:
        return f"Recommendation: keep {baseline} (no candidate clearly beat it)."
    beats = (
        best["recall_passed"] > base["recall_passed"]
        or best["mean_separation"] > base["mean_separation"] + separation_margin
    )
    if beats:
        return (
            f"Recommendation: {best_name} beats {baseline} "
            f"(recall {best['recall_passed']}/{best['recall_total']} vs "
            f"{base['recall_passed']}/{base['recall_total']}, separation "
            f"{best['mean_separation']} vs {base['mean_separation']}). "
            f"Worth a production-migration spike."
        )
    return f"Recommendation: keep {baseline} (no candidate beat it by a meaningful margin)."


def write_ab_report(results: dict, artifact_dir: Path, *, baseline: str, top_k: int = 5) -> Path:
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Embedding-Model A/B Report",
        "",
        f"| model | dim | recall@{top_k} | mean domain-separation |",
        "|---|---|---|---|",
    ]
    for name, r in sorted(results.items(), key=lambda kv: kv[1]["recall_passed"], reverse=True):
        lines.append(f"| {name} | {r['dim']} | {r['recall_passed']}/{r['recall_total']} | {r['mean_separation']} |")
    lines += ["", recommendation(results, baseline=baseline)]
    path = artifact_dir / "REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (artifact_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return path
