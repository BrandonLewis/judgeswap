from judgeswap.embeddings import (
    EvalQuery,
    cosine_rank,
    domain_separation,
    recall_pass,
    recommendation,
    run_ab,
    write_ab_report,
)

LABEL = {"label_of": lambda c: (c.get("metadata") or {}).get("division_number", "")}


def test_cosine_rank_orders_by_similarity():
    ranked = cosine_rank([1.0, 0.0], [[0.0, 1.0], [1.0, 0.0], [0.7, 0.7]])
    assert [i for i, _ in ranked] == [1, 2, 0]
    assert ranked[0][1] > ranked[1][1] > ranked[2][1]


def test_recall_pass_requires_label_and_keywords():
    top = [
        {"content": "concrete mix design", "metadata": {"division_number": "90"}},
        {"content": "other", "metadata": {"division_number": "12"}},
    ]
    assert recall_pass({"90"}, ["concrete"], top, **LABEL) is True
    assert recall_pass({"90"}, ["asphalt"], top, **LABEL) is False
    assert recall_pass({"39"}, ["concrete"], top, **LABEL) is False


def test_domain_separation():
    top = [
        {"metadata": {"division_number": "12"}, "similarity": 0.8},
        {"metadata": {"division_number": "90"}, "similarity": 0.4},
    ]
    assert domain_separation({"12"}, top, **LABEL) == 0.8 - 0.4
    assert domain_separation({"12"}, [top[0]], **LABEL) == 0.0


class _Stub:
    def __init__(self, name):
        self.name, self.input_types = name, []

    def embed(self, texts, input_type="document"):
        self.input_types.append(input_type)
        return [[1.0, 0.0] if "DIV12" in t else [0.0, 1.0] for t in texts]


CHUNKS = [
    {"content": "DIV12 lane closure chart", "metadata": {"division_number": "12"}},
    {"content": "concrete mix", "metadata": {"division_number": "90"}},
]
QUERIES = [EvalQuery("q", "DIV12 lane closure", {"12"}, ["closure"])]


def test_run_ab_scores_recall_and_separation_with_asymmetric_encoding():
    stub = _Stub("stub")
    out = run_ab([stub], CHUNKS, QUERIES, top_k=2, **LABEL)
    assert out["stub"]["recall_passed"] == 1 and out["stub"]["recall_total"] == 1
    assert out["stub"]["per_query"]["q"] is True and out["stub"]["mean_separation"] > 0
    assert stub.input_types == ["document", "query"]


def test_run_ab_isolates_a_failing_backend():
    class _Bad:
        name = "bad"

        def embed(self, texts, input_type="document"):
            raise RuntimeError("endpoint down")

    out = run_ab([_Bad(), _Stub("good")], CHUNKS, QUERIES, top_k=1, **LABEL)
    assert "good" in out and "bad" not in out


def test_run_ab_skips_a_backend_returning_the_wrong_count():
    class _Ragged:
        name = "ragged"

        def embed(self, texts, input_type="document"):
            return [[1.0, 0.0]]

    assert "ragged" not in run_ab([_Ragged()], CHUNKS, QUERIES, top_k=1, **LABEL)


def _results(base_sep=0.10, cand_sep=0.18, cand_recall=8):
    return {
        "base": {"dim": 1536, "recall_passed": 5, "recall_total": 11, "per_query": {}, "mean_separation": base_sep},
        "cand": {
            "dim": 1024,
            "recall_passed": cand_recall,
            "recall_total": 11,
            "per_query": {},
            "mean_separation": cand_sep,
        },
    }


def test_recommendation_requires_a_meaningful_margin():
    assert "cand beats base" in recommendation(_results(), baseline="base")
    tiny = recommendation(_results(cand_recall=5, cand_sep=0.104), baseline="base")
    assert tiny.startswith("Recommendation: keep base")
    assert "no candidate clearly beat it" in recommendation({"base": _results()["base"]}, baseline="base")
    assert recommendation({}, baseline="base").startswith("No backends ran")


def test_write_ab_report(tmp_path):
    path = write_ab_report(_results(), tmp_path, baseline="base")
    text = path.read_text()
    assert "| cand | 1024 | 8/11 | 0.18 |" in text and "recall@5" in text and "Recommendation" in text
    assert (tmp_path / "results.json").exists()
