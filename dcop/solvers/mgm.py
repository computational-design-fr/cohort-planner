"""MGM (Maximum Gain Message): agents exchange their potential gain with
neighbours; only the neighbourhood-maximal gainer moves. Monotone, no
simultaneous oscillation between neighbours."""
from __future__ import annotations

from .base import GainMessage, Solver, VariableAgent


class MGM(Solver):
    name = "mgm"

    def step(self, agents: dict[str, VariableAgent]) -> tuple[bool, int]:
        proposals: dict[str, tuple[str | None, float]] = {}
        inbox: dict[str, list[GainMessage]] = {m: [] for m in agents}
        msgs = 0
        for a in agents.values():
            new, new_cost = a.best_value(self.rng)
            gain = a.local_cost(a.value) - new_cost
            proposals[a.mid] = (new, gain)
            for nb in a.neighbours:
                inbox[nb].append(GainMessage(a.mid, gain))
                msgs += 1
        changed = False
        for a in agents.values():
            new, gain = proposals[a.mid]
            if gain <= 1e-9 or new == a.value:
                continue
            # strict max in neighbourhood; ties broken by agent id (deterministic)
            if all(gain > g.gain or (gain == g.gain and a.mid < g.sender) for g in inbox[a.mid]):
                a.value = new
                changed = True
        return changed, msgs
