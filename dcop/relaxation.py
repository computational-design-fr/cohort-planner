"""Ordered constraint relaxation for over-constrained meetings.

Ladder (a level is tried only when every level above it failed; nothing is
violated silently — the outcome carries the level and a trace):
 1. safety / resource constraints and mandatory attendance    (never relaxed)
 2. relax optional preferences   (acceptance thresholds → 0)
 3. shorten the session
 4. split the optional attendees into smaller groups
 5. partial attendance           (optional attendees may be absent)
 6. asynchronous fallback
 7. escalate to a human coordinator
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .agents import ParticipantAgent
from .constraints import feasible
from .model import Bid, Meeting, Problem, Slot

LEVELS = {2: "preferences", 3: "shortened", 4: "split", 5: "partial", 6: "asynchronous", 7: "escalate"}


@dataclass
class RelaxationOutcome:
    level: int
    kind: str  # see LEVELS
    meetings: list[Meeting] = field(default_factory=list)  # replacement meeting(s), if any
    bids: dict[str, dict[str, Bid]] = field(default_factory=dict)
    trace: list[str] = field(default_factory=list)
    fallback: dict = field(default_factory=dict)


def _bids_for(m: Meeting, agents: dict[str, ParticipantAgent]) -> dict[str, Bid]:
    return {p: agents[p].bid(m, relax_threshold=True, extended=True) for p in m.participants if p in agents}


def _feasible_slots(problem: Problem, m: Meeting, bids: dict[str, Bid]) -> list[Slot]:
    return [s for s in m.candidate_slots if feasible(problem, m, s, bids)]


def relax(problem: Problem, m: Meeting, agents: dict[str, ParticipantAgent]) -> RelaxationOutcome:
    trace = [f"{m.id}: no acceptable slot with current constraints"]

    # 2. preferences: same attendance, thresholds to 0
    m2 = replace(m, candidate_slots=list(m.candidate_slots), fallback=dict(m.fallback))
    b2 = _bids_for(m2, agents)
    if _feasible_slots(problem, m2, b2):
        trace.append("level 2: relaxed acceptance thresholds (optional preferences)")
        return RelaxationOutcome(2, LEVELS[2], [m2], {m2.id: b2}, trace)

    # 3. shorten
    short = max(30, m.duration_minutes // 2)
    if short < m.duration_minutes:
        m3 = replace(m2, duration_minutes=short, candidate_slots=[s.shortened(short) for s in m.candidate_slots])
        b3 = _bids_for(m3, agents)
        if _feasible_slots(problem, m3, b3):
            trace.append(f"level 3: shortened to {short} min")
            return RelaxationOutcome(3, LEVELS[3], [m3], {m3.id: b3}, trace)

    # 4. split: mandatory + each half of the optional attendees
    optional = [p for p in m.participants if p not in m.mandatory]
    if len(optional) >= 2:
        half = len(optional) // 2
        parts, bids = [], {}
        for i, g in enumerate((optional[:half], optional[half:]), 1):
            mi = replace(m2, id=f"{m.id}-part{i}", title=f"{m.title} (group {i})",
                         participants=list(m.mandatory) + g, mandatory=list(m.mandatory), min_attendance=len(m.mandatory) + len(g))
            bi = _bids_for(mi, agents)
            if not _feasible_slots(problem, mi, bi):
                parts = []
                break
            parts.append(mi)
            bids[mi.id] = bi
        if parts:
            trace.append(f"level 4: split into {len(parts)} groups")
            return RelaxationOutcome(4, LEVELS[4], parts, bids, trace)

    # 5. partial attendance: mandatory attendees only are required
    if optional:
        m5 = replace(m2, min_attendance=max(len(m.mandatory), 1))
        b5 = _bids_for(m5, agents)
        if _feasible_slots(problem, m5, b5):
            trace.append("level 5: partial attendance (optional attendees may be absent)")
            return RelaxationOutcome(5, LEVELS[5], [m5], {m5.id: b5}, trace)

    # 6. asynchronous fallback
    if m.fallback:
        trace.append("level 6: asynchronous fallback")
        return RelaxationOutcome(6, LEVELS[6], [], {}, trace, {"fallback_type": "asynchronous", **m.fallback})

    trace.append("level 7: escalate to human coordinator")
    return RelaxationOutcome(7, LEVELS[7], [], {}, trace)
