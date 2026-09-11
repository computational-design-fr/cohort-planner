import json
import sys
from pathlib import Path

import pytest

from dcop.io import load_problem, result_to_dict
from dcop.negotiation import Coordinator
from dcop.solvers import SOLVERS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))
from generate import generate  # noqa: E402

EXAMPLES = ["cohort_small", "cohort_week", "cohort_graph", "cohort_conflict", "cohort_large"]


@pytest.mark.parametrize("name", EXAMPLES)
@pytest.mark.parametrize("solver", sorted(SOLVERS))
def test_examples_solve_without_hard_violations(name, solver):
    problem = load_problem(ROOT / "examples" / f"{name}.json")
    res = Coordinator(problem, solver=solver, seed=1, max_rounds=80).schedule()
    assert res.violations == []
    assert res.rounds <= 80
    assert {s.status for s in res.sessions} <= {"confirmed", "asynchronous", "escalated"}
    out = result_to_dict(res)
    json.dumps(out)  # serialisable
    assert out["horizon"] and out["participants"]


def test_conflict_dataset_exercises_relaxation():
    res = Coordinator(load_problem(ROOT / "examples" / "cohort_conflict.json"), seed=1).schedule()
    kinds = {s.relaxation.kind for s in res.sessions if s.relaxation}
    assert kinds & {"split", "partial", "asynchronous", "shortened"}
    assert any(s.status == "asynchronous" for s in res.sessions)  # the impossible pair


def test_generator_is_deterministic():
    a, b = generate(3, 5, 1, 4), generate(3, 5, 1, 4)
    assert a == b
    assert generate(4, 5, 1, 4) != a
    assert any(m["id"] == "pair-impossible" for m in a["meetings"])
