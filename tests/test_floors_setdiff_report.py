from judgeswap.floors import Model, check_floor, floor_for, skip_reason
from judgeswap.report import read_jsonl_dir, render_delta_table, render_matrix_report, write_matrix_report
from judgeswap.setdiff import diff_sets, normalize_ref

SCOUT = Model("ollama", "llama4:scout")
FLOORS = {(SCOUT, "spec.page"): 0.5, (SCOUT, "spec.routed"): 0.7}


def test_model_is_keyed_on_runtime_and_name():
    assert Model("ollama", "x") != Model("lemonade", "x")
    assert str(SCOUT) == "ollama:llama4:scout"
    assert floor_for(FLOORS, SCOUT, "spec.routed") == 0.7
    assert floor_for(FLOORS, Model("lemonade", "llama4:scout"), "spec.routed") is None


def test_check_floor_is_tristate():
    assert check_floor(0.8, 0.7) is True
    assert check_floor(0.6, 0.7) is False
    assert check_floor(0.0, None) is None  # soft: recorded, never failing


def test_skip_reason():
    dead = {(SCOUT, "format-json"): "generic JSON grammar breaks scout"}
    assert skip_reason(dead, SCOUT, "format-json").startswith("generic")
    assert skip_reason(dead, SCOUT, "text") is None


# ---- setdiff --------------------------------------------------------------------


def test_diff_full_reports_dropped():
    d = diff_sets(candidate={"5-1.13E", "5-1.20"}, baseline={"5-1.13E", "90-1.02C"}, full=True)
    assert (d.matched, d.added, d.dropped) == ({"5-1.13E"}, {"5-1.20"}, {"90-1.02C"})
    assert (d.n_matched, d.n_added, d.n_dropped) == (1, 1, 1)


def test_diff_partial_suppresses_dropped():
    d = diff_sets(candidate={"a"}, baseline={"a", "b"}, full=False)
    assert d.dropped is None and d.n_dropped == 0


def test_normalize_ref():
    assert normalize_ref("Section 5-1.13e") == "5-1.13E"
    assert normalize_ref("  section  5-1.13E ") == "5-1.13E"
    assert normalize_ref("  03  30  00 ") == "03 30 00"
    assert normalize_ref("") == "" and normalize_ref(None) == ""
    assert normalize_ref("Art. 7", strip_prefixes=("art.",)) == "7"


# ---- report ---------------------------------------------------------------------


def _row(prompt_key, model, total, parsed=True, wall=10):
    return {
        "prompt_key": prompt_key,
        "runtime": "ollama",
        "model": model,
        "mode": "text",
        "parsed_ok": parsed,
        "score": {"total": total},
        "wall_elapsed_s": wall,
    }


def test_matrix_report_groups_and_looks_up_floors(tmp_path):
    rows = [_row("spec.page", "llama4:scout", 1.0), _row("spec.page", "llama4:scout", 0.0, parsed=False, wall=30)]
    rows.append(_row("plan_sheet", "gemma3:27b", 0.5))
    (tmp_path / "a.jsonl").write_text("".join(__import__("json").dumps(r) + "\n" for r in rows))
    assert len(read_jsonl_dir(tmp_path)) == 3

    def floor_of(r):
        return FLOORS.get((Model(r["runtime"], r["model"]), r["prompt_key"]))

    path = write_matrix_report(tmp_path, floor_of=floor_of, title="Vision-Model Eval Report")
    text = path.read_text()
    assert text.startswith("# Vision-Model Eval Report")
    assert "| spec.page | ollama | llama4:scout | text | 2 | 1/2 | 0.50 | 20s | 0.5 |" in text
    assert "| plan_sheet | ollama | gemma3:27b | text | 1 | 1/1 | 0.50 | 10s | soft |" in text


def test_matrix_report_tolerates_missing_fields():
    text = render_matrix_report([{"prompt_key": "p"}])
    assert "| p | unknown | unknown | unknown | 1 | 0/1 | 0.00 | 0s | soft |" in text


def test_write_matrix_report_returns_none_when_empty(tmp_path):
    assert write_matrix_report(tmp_path) is None


def test_delta_table_caveat_and_dropped_suppression():
    d = diff_sets(
        candidate={"5-1.13E", "5-1.20", "5-1.36", "90-1.02C"}, baseline={"5-1.13E", "5-1.36", "90-1.02C"}, full=False
    )
    out = render_delta_table(
        step="spec.page",
        subject="P-1",
        model="ollama:x",
        baseline_id="21a73a6b",
        baseline_is_current=True,
        full=False,
        per_page={12: ["5-1.13E", "5-1.20", "5-1.36"], 18: ["90-1.02C"]},
        delta=d,
    )
    assert "matched 3" in out and "added 1 (5-1.20)" in out
    assert "deltas are CHANGES" in out and "dropped n/a" in out


def test_delta_table_full_named_baseline():
    d = diff_sets(candidate={"a"}, baseline={"a", "b"}, full=True)
    out = render_delta_table(
        step="s",
        subject="p",
        model="m",
        baseline_id="b1",
        baseline_is_current=False,
        full=True,
        per_page={1: []},
        delta=d,
    )
    assert "dropped 1" in out and "deltas are CHANGES" not in out and "(none)" in out
