"""Weighted objective  U(m,t) = w_a·A + w_p·P + w_f·F − w_i·I − w_c·C  (maximise).

A attendance fraction, P mean utility, F fairness = min utility (debt-weighted),
I shortfall below each participant's acceptance threshold, C resource cost.
"""
from __future__ import annotations

from dataclasses import dataclass

from .constraints import attendance
from .model import Bid, Meeting, Problem, Slot


@dataclass(frozen=True)
class Weights:
    attendance: float = 1.0
    preference: float = 1.0
    fairness: float = 1.0
    idle: float = 0.5
    cost: float = 0.1
    hard_penalty: float = 100.0  # cost of a hard violation in local search


def score(problem: Problem, m: Meeting, slot: Slot, bids: dict[str, Bid], w: Weights = Weights()) -> float:
    present = attendance(m, slot.id, bids)
    n = max(len(m.participants), 1)
    a = len(present) / n
    utils = {p: bids[p].utility(slot.id) or 0.0 for p in present}
    p_mean = sum(utils.values()) / n
    # fairness: least-served participant, weighted by cumulative debt D_p
    fair = min(((u - 0.1 * problem.participants[p].debt) for p, u in utils.items()), default=0.0)
    shortfall = sum(max(0.0, bids[p].minimum_acceptance - u) for p, u in utils.items()) / n
    cost = 0.0
    if m.resource:
        r = problem.resources[m.resource]
        cost = r.cost_per_hour * m.duration_minutes / 60 * m.recurrence_weeks
    return w.attendance * a + w.preference * p_mean + w.fairness * fair - w.idle * shortfall - w.cost * cost
