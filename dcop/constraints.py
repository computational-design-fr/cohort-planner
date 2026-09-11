"""Hard constraints (return violation lists) and soft-constraint helpers."""
from __future__ import annotations

from .model import Assignment, Bid, Meeting, Problem, Slot, overlaps


def slot_of(problem: Problem, meeting_id: str, slot_id: str | None) -> Slot | None:
    if slot_id is None:
        return None
    for s in problem.meetings[meeting_id].candidate_slots:
        if s.id == slot_id:
            return s
    raise KeyError(f"{slot_id} is not a candidate slot of {meeting_id}")


def resource_available(problem: Problem, m: Meeting, slot: Slot) -> bool:
    if not m.resource:
        return True
    r = problem.resources[m.resource]
    if r.capacity < len(m.participants):
        return False
    return not any(overlaps(occ.interval, b) for occ in m.occurrences(slot) for b in r.busy)


def attendance(m: Meeting, slot_id: str, bids: dict[str, Bid]) -> list[str]:
    """Participants whose bid lists ``slot_id`` (i.e. feasible for them)."""
    return [p for p in m.participants if p in bids and bids[p].utility(slot_id) is not None]


def feasible(problem: Problem, m: Meeting, slot: Slot, bids: dict[str, Bid]) -> bool:
    """Feasible(m,t) = all mandatory available ∧ attendance ≥ min ∧ resource ok."""
    present = attendance(m, slot.id, bids)
    if any(p not in present for p in m.mandatory):
        return False
    if len(present) < (m.min_attendance or 0):
        return False
    return resource_available(problem, m, slot)


def pairwise_conflict(problem: Problem, a: str, sa: str | None, b: str, sb: str | None) -> bool:
    """Two meetings sharing a participant or resource overlap in time (any occurrence)."""
    if sa is None or sb is None or a == b:
        return False
    ma, mb = problem.meetings[a], problem.meetings[b]
    if not (set(ma.participants) & set(mb.participants)) and not (ma.resource and ma.resource == mb.resource):
        return False
    xa, xb = slot_of(problem, a, sa), slot_of(problem, b, sb)
    assert xa and xb
    return any(overlaps(u.interval, v.interval) for u in ma.occurrences(xa) for v in mb.occurrences(xb))


def violations(problem: Problem, assignment: Assignment, bids: dict[str, dict[str, Bid]]) -> list[str]:
    out: list[str] = []
    ids = list(assignment)
    for i, a in enumerate(ids):
        sa = assignment[a]
        if sa is None:
            continue
        m = problem.meetings[a]
        if not feasible(problem, m, slot_of(problem, a, sa), bids.get(a, {})):
            out.append(f"{a}@{sa}: infeasible (availability/attendance/resource)")
        for b in ids[i + 1 :]:
            if pairwise_conflict(problem, a, sa, b, assignment[b]):
                out.append(f"{a}@{sa} overlaps {b}@{assignment[b]}")
    return out
