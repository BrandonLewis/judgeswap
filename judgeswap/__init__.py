"""judgeswap: evaluation harness pieces for LLM generation pipelines.

Position-swapped LLM-as-judge preference (a judge that always answers "A"
scores a tie), rubric scoring with validated JSON, a parity loop over frozen
contexts, robust structured-output parsing, regression floors keyed on
(runtime, model), set-level candidate-vs-baseline diffs, matrix reports, and
an offline embedding-model A/B scorer. No framework, no network: every
network call goes through a one-method client the caller supplies.
"""

from .embeddings import EvalQuery, cosine_rank, domain_separation, recall_pass, run_ab, write_ab_report
from .floors import Model, check_floor, floor_for
from .judging import DEFAULT_AXES, Rubric, RubricJudge, head_to_head, parse_judge_json
from .parity import Section, run_parity, ungrounded_citations, write_parity_report
from .setdiff import SetDelta, diff_sets, normalize_ref
from .structured import extract_structured, mean_axes

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_AXES",
    "EvalQuery",
    "Model",
    "Rubric",
    "RubricJudge",
    "Section",
    "SetDelta",
    "__version__",
    "check_floor",
    "cosine_rank",
    "diff_sets",
    "domain_separation",
    "extract_structured",
    "floor_for",
    "head_to_head",
    "mean_axes",
    "normalize_ref",
    "parse_judge_json",
    "recall_pass",
    "run_ab",
    "run_parity",
    "ungrounded_citations",
    "write_ab_report",
    "write_parity_report",
]
