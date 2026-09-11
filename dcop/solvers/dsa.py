"""DSA-B: each agent computes its best response; if it strictly improves
(or ties with a conflict, variant B) it switches with probability p."""
from __future__ import annotations

from .base import Solver, VariableAgent


class DSA(Solver):
    name = "dsa"

    def __init__(self, p: float = 0.7, **kw):
        super().__init__(**kw)
        self.p = p

    def step(self, agents: dict[str, VariableAgent]) -> tuple[bool, int]:
        changed = False
        decisions = {}
        for a in agents.values():
            cur = a.local_cost(a.value)
            new, new_cost = a.best_value(self.rng)
            improves = new_cost < cur - 1e-9
            in_conflict = cur >= self.w.hard_penalty
            if new != a.value and (improves or (in_conflict and new_cost <= cur)) and self.rng.random() < self.p:
                decisions[a.mid] = new
        for mid, v in decisions.items():  # simultaneous update
            agents[mid].value = v
            changed = True
        return changed, 0
