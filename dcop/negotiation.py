"""Coordinator: the 8-stage negotiation protocol on top of a DCOP solver.

1 create session requests   5 score alternatives (DCOP local search)
2 generate local candidates  6 provisional reservation with TTL
3 exchange ranked bids       7 confirm or repair (next best / relaxation ladder)
4 find common candidates     8 publish

The coordinator never reads a private calendar: it only holds bids.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .agents import ParticipantAgent, ResourceAgent
from .constraints import feasible, slot_of, violations
from .model import Bid, Meeting, Problem, Reservation, Slot
from .objective import Weights, score
from .relaxation import RelaxationOutcome, relax
from .solvers import SOLVERS, Solver


@dataclass
class ScheduledSession:
    meeting: Meeting
    slot: Slot | None
    status: str  # confirmed | asynchronous | escalated
    score: float = 0.0
    utilities: dict[str, float] = field(default_factory=dict)
    relaxation: RelaxationOutcome | None = None
    trace: list[str] = field(default_factory=list)


@dataclass
class ScheduleResult:
    sessions: list[ScheduledSession]
    reservations: list[Reservation]
    solver: str
    rounds: int
    messages: int
    violations: list[str]
    history: list[float]
    participants: list[dict] = field(default_factory=list)  # {id, role, debt} after commit
    horizon: tuple[datetime, datetime] | None = None

    @property
    def confirmed(self) -> list[ScheduledSession]:
        return [s for s in self.sessions if s.status == "confirmed"]


class Coordinator:
    def __init__(self, problem: Problem, solver: str | Solver = "mgm", weights: Weights = Weights(),
                 seed: int | None = None, reservation_ttl_minutes: int = 30, max_rounds: int = 50):
        self.problem = problem
        self.w = weights
        self.solver = SOLVERS[solver](weights=weights, seed=seed) if isinstance(solver, str) else solver
        self.agents = {p.id: ParticipantAgent(p) for p in problem.participants.values()}
        self.resources = {r.id: ResourceAgent(r) for r in problem.resources.values()}
        self.ttl = timedelta(minutes=reservation_ttl_minutes)
        self.max_rounds = max_rounds
        self.reservations: list[Reservation] = []

    # stage 2-3 ---------------------------------------------------------------
    def collect_bids(self, meetings: dict[str, Meeting]) -> dict[str, dict[str, Bid]]:
        """Stage 3: limited ranked bids first; if no common candidate (stage 4),
        ask the same agents for *extended* bids before touching any constraint."""
        out: dict[str, dict[str, Bid]] = {}
        for m in meetings.values():
            bids = {p: self.agents[p].bid(m) for p in m.participants if p in self.agents}
            if not any(feasible(self.problem, m, s, bids) for s in m.candidate_slots):
                bids = {p: self.agents[p].bid(m, extended=True) for p in m.participants if p in self.agents}
            out[m.id] = bids
        return out

    # stage 6 -----------------------------------------------------------------
    def reserve(self, m: Meeting, slot: Slot, now: datetime) -> list[Reservation]:
        out = []
        for occ in m.occurrences(slot):
            for p in m.participants:
                out.append(Reservation("participant", p, occ, m.id, "provisional", now + self.ttl))
            if m.resource:
                out.append(Reservation("resource", m.resource, occ, m.id, "provisional", now + self.ttl))
        self.reservations += out
        return out

    def confirm(self, m: Meeting, slot: Slot, bids: dict[str, Bid]) -> None:
        for r in self.reservations:
            if r.session_id == m.id:
                r.status = "confirmed"
        for occ in m.occurrences(slot):
            for p in m.participants:
                if p in self.agents and bids[p].utility(slot.id) is not None:
                    self.agents[p].commit(occ, 1.0 - (bids[p].utility(slot.id) or 0.0))
        # resource bookings live in ``self.reservations`` (confirmed); the Resource's
        # own busy list is left untouched so feasibility checks stay stable.

    def release(self, session_id: str) -> None:
        for r in self.reservations:
            if r.session_id == session_id and r.status == "provisional":
                r.status = "released"

    # stage 6-7 for one meeting ----------------------------------------------
    def _place(self, sub: Problem, m: Meeting, bids: dict[str, Bid], preferred: str | None,
               now: datetime, trace: list[str]) -> ScheduledSession | None:
        candidates = [slot_of(sub, m.id, preferred)] if preferred else []
        candidates += sorted((s for s in m.candidate_slots if s.id != preferred and feasible(sub, m, s, bids)),
                             key=lambda s: -score(sub, m, s, bids, self.w))
        for s in candidates:
            self.reserve(m, s, now)
            conflict = [r for r in self.reservations
                        if r.status == "confirmed" and r.session_id != m.id
                        and any(o.interval[0] < r.slot.interval[1] and r.slot.interval[0] < o.interval[1]
                                and ((r.resource_type == "participant" and r.resource_id in m.participants)
                                     or (r.resource_type == "resource" and r.resource_id == m.resource))
                                for o in m.occurrences(s))]
            rejected = [p for p in m.mandatory if p in self.agents and not self.agents[p].accepts(bids[p], s.id)]
            if conflict or rejected:
                self.release(m.id)
                trace.append(f"repair: {s.id} rejected ({'conflict' if conflict else 'mandatory ' + ','.join(rejected)})")
                continue
            self.confirm(m, s, bids)
            utils = {p: bids[p].utility(s.id) for p in m.participants if p in bids}
            return ScheduledSession(m, s, "confirmed", round(score(sub, m, s, bids, self.w), 3),
                                    {p: u for p, u in utils.items() if u is not None}, None, trace + [f"published {s.id}"])
        return None

    @staticmethod
    def _unplaced(m: Meeting, outcome: RelaxationOutcome) -> ScheduledSession:
        status = "asynchronous" if outcome.kind == "asynchronous" else "escalated"
        return ScheduledSession(m, None, status, relaxation=outcome, trace=outcome.trace)

    # whole protocol ----------------------------------------------------------
    def schedule(self, now: datetime | None = None) -> ScheduleResult:
        now = now or datetime.now(timezone.utc)
        bids = self.collect_bids(self.problem.meetings)  # stage 2-3 (+ extended bids)
        sessions: list[ScheduledSession] = []

        # stage 4: meetings with no common candidate go through the relaxation ladder first
        solvable: dict[str, Meeting] = {}
        relaxed: dict[str, RelaxationOutcome] = {}
        for m in self.problem.meetings.values():
            if any(feasible(self.problem, m, s, bids[m.id]) for s in m.candidate_slots):
                solvable[m.id] = m
                continue
            outcome = relax(self.problem, m, self.agents)
            if not outcome.meetings:
                sessions.append(self._unplaced(m, outcome))
                continue
            for mm in outcome.meetings:
                solvable[mm.id] = mm
                bids[mm.id] = outcome.bids[mm.id]
                relaxed[mm.id] = outcome

        # stage 5: DCOP local search over the solvable meetings
        sub = Problem(self.problem.participants, self.problem.resources, solvable)
        result = self.solver.run(sub, bids, self.max_rounds)
        assignment = dict(result.assignment)

        # stage 6-8: reserve → confirm or repair → publish, highest priority first
        for m in sorted(solvable.values(), key=lambda x: -x.priority):
            rel = relaxed.get(m.id)
            trace = list(rel.trace) if rel else []
            placed = self._place(sub, m, bids[m.id], assignment.get(m.id), now, trace)
            if placed:
                placed.relaxation = rel
                sessions.append(placed)
                assignment[m.id] = placed.slot.id
                continue
            assignment[m.id] = None
            if rel is None:  # every candidate was rejected at confirmation: relax now
                outcome = relax(self.problem, m, self.agents)
                outcome.trace = trace + outcome.trace
                for mm in outcome.meetings:
                    sub.meetings[mm.id] = mm
                    bids[mm.id] = outcome.bids[mm.id]
                    p2 = self._place(sub, mm, bids[mm.id], None, now, list(outcome.trace))
                    if p2:
                        p2.relaxation = outcome
                        sessions.append(p2)
                        assignment[mm.id] = p2.slot.id
                    else:
                        assignment[mm.id] = None
                        sessions.append(self._unplaced(mm, RelaxationOutcome(7, "escalate", trace=outcome.trace + ["no acceptable slot after relaxation"])))
                if not outcome.meetings:
                    sessions.append(self._unplaced(m, outcome))
            else:
                sessions.append(self._unplaced(m, RelaxationOutcome(7, "escalate", trace=trace + ["no acceptable slot after repair"])))

        viol = violations(sub, {k: v for k, v in assignment.items() if k in sub.meetings}, bids)
        slots = [s for m in self.problem.meetings.values() for s in m.candidate_slots]
        horizon = (min(s.start for s in slots), max(s.end for s in slots)) if slots else None
        people = [{"id": p.id, "role": p.role, "debt": round(p.debt, 3), "preferred_hours": list(p.preferred_hours)}
                  for p in self.problem.participants.values()]
        return ScheduleResult(sessions, self.reservations, self.solver.name, result.rounds, result.messages, viol, result.history,
                              people, horizon)
