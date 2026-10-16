"""The parity loop over frozen contexts: artifacts, aggregates, ungrounded citations."""

import json

from judgeswap.parity import Section, footnote_key, run_parity, summarize, ungrounded_citations, write_parity_report


class _Judge:
    def __init__(self, scores, prefs):
        self.scores, self.prefs = scores, list(prefs)

    def score(self, section_id, *, candidate, reference, context, structured_data=None):
        return dict(self.scores)

    def prefer(self, section_id, *, a, b, context):
        return self.prefs.pop(0)


GOOD = {
    "grounding": 4,
    "coverage": 3,
    "specificity": 5,
    "citation_accuracy": 4,
    "ceiling_flags": ["x"],
    "rationale": "r",
}


def _sections():
    return {"triage": Section(context="CTX", reference="REF", retrieved_citations=[])}


def test_run_parity_writes_jsonl_and_report_and_aggregates(tmp_path):
    seen = []

    def generate(sid, section, overrides):
        seen.append((sid, overrides))
        return "CAND", [{"footnote": 1}]

    agg = run_parity(
        _sections(),
        generate=generate,
        judge=_Judge(GOOD, ["A", "B"]),
        artifact_dir=tmp_path,
        label={"project": "P-1"},
    )
    assert seen == [("triage", None)]
    assert agg["baseline"]["wins"] == 1
    assert abs(agg["baseline"]["mean_total"] - (4 + 3 + 5 + 4) / 4) < 1e-6
    rows = [json.loads(line) for line in (tmp_path / "baseline.jsonl").read_text().splitlines()]
    assert rows[0]["section_id"] == "triage" and rows[0]["h2h"] == "win" and rows[0]["project"] == "P-1"
    report = (tmp_path / "REPORT.md").read_text()
    assert "| baseline | triage | 4 | 3 | 5 | 4 | 4.00 | win | 1 | 1 | 1 |" in report


def test_run_parity_counts_ungrounded_citations(tmp_path):
    """A footnote with no bracketed context item behind it is the failure a
    prose judge cannot see: the frozen context retrieved nothing, so the one
    citation the candidate emits is ungrounded."""
    agg = run_parity(
        _sections(),
        generate=lambda sid, s, o: ("CAND", [{"footnote": 1}]),
        judge=_Judge(GOOD, ["A", "A"]),
        artifact_dir=tmp_path,
    )
    assert agg["baseline"]["citations"] == 1
    assert agg["baseline"]["ungrounded_citations"] == 1
    assert agg["baseline"]["ties"] == 1


def test_run_parity_runs_every_variant_and_passes_its_overrides(tmp_path):
    calls = []
    agg = run_parity(
        _sections(),
        generate=lambda sid, s, o: calls.append(o) or ("C", []),
        judge=_Judge(GOOD, ["A", "B", "B", "A"]),
        artifact_dir=tmp_path,
        variants={"baseline": {}, "v2": {"triage": "<template>"}},
    )
    assert calls == [{}, {"triage": "<template>"}]
    assert set(agg) == {"baseline", "v2"}
    assert (tmp_path / "v2.jsonl").exists()
    assert agg["v2"]["losses"] == 1


def test_a_judge_error_is_an_error_row_not_an_exception(tmp_path):
    agg = run_parity(
        _sections(),
        generate=lambda sid, s, o: ("C", []),
        judge=_Judge({"error": "judge call failed"}, []),
        artifact_dir=tmp_path,
    )
    assert agg["baseline"] == {
        "mean_total": 0.0,
        "wins": 0,
        "ties": 0,
        "losses": 0,
        "ceiling_flag_count": 0,
        "citations": 0,
        "ungrounded_citations": 0,
    }
    assert "| err | error |" in (tmp_path / "REPORT.md").read_text()


def test_sections_without_a_reference_are_skipped(tmp_path):
    sections = {"a": Section(context="C", reference=""), "b": Section(context="C", reference="R")}
    run_parity(sections, generate=lambda *a: ("C", []), judge=_Judge(GOOD, ["A", "B"]), artifact_dir=tmp_path)
    rows = (tmp_path / "baseline.jsonl").read_text().splitlines()
    assert len(rows) == 1 and json.loads(rows[0])["section_id"] == "b"


def test_explicit_axes_pin_the_report_columns(tmp_path):
    run_parity(
        _sections(),
        generate=lambda *a: ("C", []),
        judge=_Judge(GOOD, ["A", "B"]),
        artifact_dir=tmp_path,
        axes=("grounding", "coverage"),
    )
    report = (tmp_path / "REPORT.md").read_text()
    assert "| variant | section | grounding | coverage | total |" in report
    assert "| 3.50 |" in report  # mean over the two pinned axes only


def test_write_parity_report_returns_none_when_empty(tmp_path):
    assert write_parity_report(tmp_path) is None


def test_footnote_key_normalizes_the_shapes_models_emit():
    assert [footnote_key(v) for v in (3, "3", "[3]", "[^3]", " [3] ")] == [3] * 5
    assert footnote_key(None) is None and footnote_key("abc") is None


def test_ungrounded_citations_only_counts_footnotes_outside_the_context():
    retrieved = [{"footnote": 1}, {"footnote": 2}]
    cites = [{"footnote": 1}, {"footnote": "2"}, {"footnote": 3}, {"footnote": None}]
    assert ungrounded_citations(cites, retrieved) == 2


def test_ungrounded_citations_honours_a_custom_join_rule():
    retrieved = [{"footnote": "n1"}]
    cites = [{"footnote": "N1"}, {"footnote": "n2"}]
    assert ungrounded_citations(cites, retrieved, key=lambda v: str(v).lower()) == 1


def test_summarize_ignores_error_rows_in_the_mean():
    rows = [
        {
            "total": 4.0,
            "h2h": "win",
            "scores": {"ceiling_flags": ["a", "b"]},
            "citations": 2,
            "ungrounded_citations": 0,
        },
        {"total": None, "h2h": "error", "scores": {"error": "x"}, "citations": 0, "ungrounded_citations": 0},
    ]
    assert summarize(rows)["mean_total"] == 4.0 and summarize(rows)["ceiling_flag_count"] == 2
