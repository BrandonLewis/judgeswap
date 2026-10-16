from judgeswap.structured import extract_structured, mean_axes, parse_keyvalue

KV = {"DRAWING": "drawing_number", "SHEET": "sheet_number", "TITLE": "sheet_title"}


def test_bare_json():
    ok, out = extract_structured('{"page_type": "cover"}')
    assert ok and out == {"page_type": "cover"}


def test_fenced_json_with_think_block_and_prose():
    raw = '<think>hmm</think>\nSure! Here it is:\n```json\n{"a": 1}\n```\nDone.'
    assert extract_structured(raw) == (True, {"a": 1})


def test_json_sliced_out_of_a_preamble():
    assert extract_structured('The answer: {"a": [1, 2]} as requested.') == (True, {"a": [1, 2]})


def test_empty_object_is_a_failure_not_a_parse():
    ok, out = extract_structured("{}")
    assert not ok and out["error"] == "empty JSON object"


def test_empty_and_gibberish():
    assert extract_structured("")[1]["error"] == "empty response"
    ok, out = extract_structured("lorem ipsum")
    assert not ok and out["error"] == "no parseable structure found" and out["raw_head"] == "lorem ipsum"


def test_keyvalue_fallback_only_when_asked():
    raw = "DRAWING: C-101\nSHEET: 3\nTITLE: Plan"
    assert not extract_structured(raw)[0]
    ok, out = extract_structured(raw, keyvalue=KV)
    assert ok and out == {"drawing_number": "C-101", "sheet_number": "3", "sheet_title": "Plan"}


def test_keyvalue_needs_two_matches():
    assert parse_keyvalue("DRAWING: C-101\nFOO: bar", KV) is None
    assert parse_keyvalue("DRAWING: C-101\nSHEET: 2", KV) == {"drawing_number": "C-101", "sheet_number": "2"}


def test_mean_axes_excludes_notes_and_total():
    score = {"page_type": 1.0, "sections": 0.0, "notes": ["x"]}
    assert mean_axes(score)["total"] == 0.5
    assert mean_axes(score)["total"] == 0.5  # idempotent: total is not averaged into itself
    assert mean_axes({"notes": []})["total"] == 0.0
