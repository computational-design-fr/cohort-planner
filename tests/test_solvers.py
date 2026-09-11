import pytest

from dcop.agents import ParticipantAgent
from dcop.constraints import violations
from dcop.model import Problem
from dcop.solvers import DSA, MGM, SOLVERS


def _bids(problem):
    return {mid: {p: ParticipantAgent(problem.participants[p]).bid(m, extended=True) for p in m.participants}
            for mid, m in problem.meetings.items()}


@pytest.mark.parametrize("name", sorted(SOLVERS))
@pytest.mark.parametrize("seed", [0, 1, 7])
def test_local_search_finds_conflict_free_assignment(problem, name, seed):
    sub = Problem(problem.participants, problem.resources, {k: v for k, v in problem.meetings.items() if k != "pair"})
    bids = _bids(sub)
    res = SOLVERS[name](seed=seed).run(sub, bids, max_rounds=60)
    assert all(v is not None for v in res.assignment.values())
    assert violations(sub, res.assignment, bids) == []
    assert res.messages > 0 and 1 <= res.rounds <= 60


def test_mgm_is_monotone(problem):
    sub = Problem(problem.participants, problem.resources, {k: v for k, v in problem.meetings.items() if k != "pair"})
    res = MGM(seed=2).run(sub, _bids(sub), max_rounds=40)
    for a, b in zip(res.history, res.history[1:]):
        assert b <= a + 1e-9


def test_dsa_probability_zero_never_moves(problem):
    sub = Problem(problem.participants, problem.resources, {k: v for k, v in problem.meetings.items() if k != "pair"})
    res = DSA(p=0.0, seed=2).run(sub, _bids(sub), max_rounds=10)
    assert res.rounds == 3  # stable from the first round → stops after 3 quiet rounds


def test_agent_with_empty_domain_stays_unassigned(problem):
    bids = _bids(problem)
    res = MGM(seed=0).run(problem, bids, max_rounds=20)
    assert res.assignment["pair"] is None
