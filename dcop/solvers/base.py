"""Synchronous round-based simulation of local-search DCOP algorithms.

Each meeting is a *variable agent*. It only knows: its own domain and costs,
and the current values of its neighbours (received as ``ValueMessage``).
Cost to minimise = hard_penalty·#conflicts − U(m,t)·priority/50.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..constraints import feasible, pairwise_conflict
from ..model import Assignment, Bid, Problem
from ..objective import Weights, score


@dataclass(frozen=True)
class ValueMessage:
    sender: str
    value: str | None


@dataclass(frozen=True)
class GainMessage:
    sender: str
    gain: float


@dataclass
class SolveResult:
    assignment: Assignment
    cost: float
    rounds: int
    messages: int
    history: list[float] = field(default_factory=list)


class VariableAgent:
    def __init__(self, problem: Problem, meeting_id: str, bids: dict[str, Bid], w: Weights):
        self.problem, self.mid, self.bids, self.w = problem, meeting_id, bids, w
        m = problem.meetings[meeting_id]
        self.domain = [s for s in m.candidate_slots if feasible(problem, m, s, bids)]
        self.neighbours = problem.neighbours(meeting_id)
        self.view: dict[str, str | None] = {n: None for n in self.neighbours}
        self.value: str | None = None
        self._unary = {s.id: -score(problem, m, s, bids, w) * m.priority / 50 for s in self.domain}

    def local_cost(self, value: str | None) -> float:
        if value is None:
            return self.w.hard_penalty * 0.5  # unassigned is bad, but less than a conflict
        c = self._unary[value]
        for n, v in self.view.items():
            if pairwise_conflict(self.problem, self.mid, value, n, v):
                c += self.w.hard_penalty
        return c

    def best_value(self, rng: random.Random) -> tuple[str | None, float]:
        if not self.domain:
            return None, self.local_cost(None)
        order = list(self.domain)
        rng.shuffle(order)  # random tie-breaking, symmetric agents must differ
        best = min(order, key=lambda s: self.local_cost(s.id))
        return best.id, self.local_cost(best.id)

    def receive(self, msg: ValueMessage) -> None:
        self.view[msg.sender] = msg.value


class Solver(ABC):
    name = "base"

    def __init__(self, weights: Weights = Weights(), seed: int | None = None):
        self.w, self.rng = weights, random.Random(seed)

    def run(self, problem: Problem, bids: dict[str, dict[str, Bid]], max_rounds: int = 50) -> SolveResult:
        agents = {mid: VariableAgent(problem, mid, bids.get(mid, {}), self.w) for mid in problem.meetings}
        messages = 0
        for a in agents.values():  # random initial assignment
            a.value = self.rng.choice(a.domain).id if a.domain else None
        messages += self._broadcast(agents)
        history: list[float] = []
        stable = 0
        rounds = 0
        for rounds in range(1, max_rounds + 1):
            changed, msgs = self.step(agents)
            messages += msgs + self._broadcast(agents)
            history.append(self._global_cost(agents))
            stable = stable + 1 if not changed else 0
            if stable >= 3:
                break
        return SolveResult({m: a.value for m, a in agents.items()}, history[-1] if history else 0.0, rounds, messages, history)

    @abstractmethod
    def step(self, agents: dict[str, VariableAgent]) -> tuple[bool, int]:
        """One round; return (any value changed, messages sent inside the step)."""

    @staticmethod
    def _broadcast(agents: dict[str, VariableAgent]) -> int:
        n = 0
        for a in agents.values():
            for nb in a.neighbours:
                agents[nb].receive(ValueMessage(a.mid, a.value))
                n += 1
        return n

    @staticmethod
    def _global_cost(agents: dict[str, VariableAgent]) -> float:
        # each binary conflict is counted twice (once per side); halve that part
        total = sum(a.local_cost(a.value) for a in agents.values())
        return round(total, 4)
