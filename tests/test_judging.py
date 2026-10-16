"""The judge contract: validated rubric JSON, positional preference, and the swap."""

from judgeswap.judging import DEFAULT_AXES, Rubric, RubricJudge, head_to_head, parse_judge_json, parse_preference


def _scores(**over):
    base = {
        "grounding": 4,
        "coverage": 3,
        "specificity": 5,
        "citation_accuracy": 2,
        "ceiling_flags": [],
        "rationale": "",
    }
    base.update(over)
    return base


# ---- head_to_head -------------------------------------------------------------


def test_win_requires_the_candidate_to_be_preferred_in_both_orderings():
    answers = iter(["A", "B"])  # candidate shown as A, then as B
    assert head_to_head(lambda a, b: next(answers), "C", "R") == "win"


def test_loss_requires_the_candidate_to_be_rejected_in_both_orderings():
    answers = iter(["B", "A"])
    assert head_to_head(lambda a, b: next(answers), "C", "R") == "loss"


def test_a_judge_that_always_answers_a_scores_a_tie():
    """Pure position bias, no content discrimination: the swap cancels it."""
    assert head_to_head(lambda a, b: "A", "C", "R") == "tie"
    assert head_to_head(lambda a, b: "B", "C", "R") == "tie"


def test_the_candidate_is_passed_in_both_slots():
    seen = []
    head_to_head(lambda a, b: seen.append((a, b)) or "tie", "C", "R")
    assert seen == [("C", "R"), ("R", "C")]


def test_one_tie_answer_is_a_tie_whatever_the_other_says():
    answers = iter(["A", "tie"])
    assert head_to_head(lambda a, b: next(answers), "C", "R") == "tie"


# ---- parse_judge_json -----------------------------------------------------------


def test_parses_a_fenced_json_block():
    import json

    raw = "```json\n" + json.dumps(_scores(ceiling_flags=["ref cites a fact absent from context"])) + "\n```"
    out = parse_judge_json(raw)
    assert out["coverage"] == 3 and out["ceiling_flags"]


def test_parses_json_embedded_in_prose():
    import json

    raw = "Here is my grading:\n" + json.dumps(_scores()) + "\nHope that helps."
    assert parse_judge_json(raw)["grounding"] == 4


def test_rejects_a_missing_axis():
    assert parse_judge_json('{"grounding": 4}') is None


def test_rejects_out_of_range_and_non_integer_axes():
    import json

    assert parse_judge_json(json.dumps(_scores(grounding=9))) is None
    assert parse_judge_json(json.dumps(_scores(coverage=0))) is None
    assert parse_judge_json(json.dumps(_scores(specificity="4"))) is None


def test_rejects_a_bool_axis():
    """bool is an int subclass; a `true` axis must not slip through as 1."""
    import json

    assert parse_judge_json(json.dumps(_scores(grounding=True))) is None


def test_coerces_malformed_non_axis_fields():
    import json

    out = parse_judge_json(json.dumps(_scores(ceiling_flags="not a list", rationale=None)))
    assert out["ceiling_flags"] == [] and out["rationale"] == ""


def test_custom_axes_and_scale():
    import json

    raw = json.dumps({"accuracy": 7, "tone": 9})
    assert parse_judge_json(raw, axes=("accuracy", "tone"), scale=(0, 10))["tone"] == 9
    assert parse_judge_json(raw, axes=("accuracy", "tone"), scale=(1, 5)) is None


def test_garbage_is_none():
    assert parse_judge_json("") is None
    assert parse_judge_json("no json here") is None
    assert parse_judge_json("[1, 2, 3]") is None


# ---- parse_preference -----------------------------------------------------------


def test_preference_tokens():
    assert parse_preference("A") == "A"
    assert parse_preference(" b.") == "B"
    assert parse_preference("tie") == "tie"
    assert parse_preference("") == "tie"
    assert parse_preference("Both are equally good") == "B"  # a leading letter is read; the rubric asks for one token


# ---- Rubric / RubricJudge -------------------------------------------------------


def test_default_rubric_prompt_carries_every_part():
    p = Rubric().score_prompt("s1", "CAND", "REF", "CTX", structured_data={"estimate_usd": 1200000})
    for axis in DEFAULT_AXES:
        assert axis in p
    assert "CAND" in p and "REF" in p and "CTX" in p and "1200000" in p and "ceiling_flags" in p


def test_default_rubric_without_structured_data_says_so():
    assert "(none for this section)" in Rubric().score_prompt("s1", "C", "R", "X")


def test_custom_templates_are_used_verbatim():
    r = Rubric(score_template="S {section_id} {candidate}", preference_template="P {a} {b}")
    assert r.score_prompt("id", "c", "r", "x") == "S id c"
    assert r.preference_prompt("id", "a", "b", "x") == "P a b"


class _Client:
    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def test_rubric_judge_scores_and_prefers():
    import json

    client = _Client([json.dumps(_scores()), "B"])
    judge = RubricJudge(client)
    assert judge.score("s", candidate="C", reference="R", context="X")["specificity"] == 5
    assert judge.prefer("s", a="C", b="R", context="X") == "B"


def test_rubric_judge_turns_failures_into_error_rows_not_scores():

    client = _Client([RuntimeError("timeout"), "not json", RuntimeError("Ambiguous: A or B")])
    judge = RubricJudge(client)
    assert "error" in judge.score("s", candidate="C", reference="R", context="X")
    out = judge.score("s", candidate="C", reference="R", context="X")
    assert out["error"].startswith("judge returned unparseable") and out["raw"] == "not json"
    # a failed preference call is a tie, never a letter read off the error text
    assert judge.prefer("s", a="C", b="R", context="X") == "tie"


def test_rubric_judge_head_to_head_swaps():
    import json

    client = _Client([json.dumps(_scores()), "A", "B"])
    judge = RubricJudge(client)
    judge.score("s", candidate="C", reference="R", context="X")
    assert judge.head_to_head("s", candidate="C", reference="R", context="X") == "win"
    assert "A:\nC" in client.prompts[1] and "A:\nR" in client.prompts[2]
