"""Participant-side agents. They own private calendars and emit *bids* only."""
from __future__ import annotations

from datetime import timedelta

from .model import Bid, Meeting, Participant, Resource, Slot, SlotBid, overlaps


class ParticipantAgent:
    """Learner / facilitator agent: computes feasible slots from its private
    calendar and scores them; reveals at most ``max_bids`` ranked candidates."""

    def __init__(self, participant: Participant):
        self.p = participant

    # -- private -----------------------------------------------------------
    def is_free(self, slot: Slot) -> bool:
        return not any(overlaps(slot.interval, b) for b in self.p.busy)

    def utility(self, slot: Slot) -> float:
        lo, hi = self.p.preferred_hours
        inside = lo <= slot.start.hour and slot.end.hour + (slot.end.minute > 0) <= hi
        u = 1.0 if inside else self.p.off_hours_utility
        # fragmentation penalty: isolated slot far from any existing commitment
        gaps = [
            min(abs((slot.start - b[1]).total_seconds()), abs((b[0] - slot.end).total_seconds()))
            for b in self.p.busy
            if b[0].date() == slot.start.date()
        ]
        if gaps and min(gaps) > 2 * 3600:
            u -= 0.1
        if self.p.role == "facilitator":
            u = min(1.0, u + 0.05)
        return round(max(0.0, u), 3)

    # -- public ------------------------------------------------------------
    def bid(self, meeting: Meeting, relax_threshold: bool = False, extended: bool = False) -> Bid:
        """Ranked feasible slots. ``extended`` reveals every feasible slot instead of
        the top ``max_bids`` (coordinator asks for it only when no common slot exists)."""
        ranked: list[SlotBid] = []
        for s in meeting.candidate_slots:
            occs = meeting.occurrences(s)
            if all(self.is_free(o) for o in occs):
                u = min(self.utility(o) for o in occs)
                ranked.append(SlotBid(s.id, u))
        ranked.sort(key=lambda b: -b.utility)
        threshold = 0.0 if relax_threshold else self.p.minimum_acceptance
        limit = None if extended or self.p.max_bids <= 0 else self.p.max_bids
        return Bid(meeting.id, self.p.id, ranked[:limit], threshold)

    def accepts(self, bid: Bid, slot_id: str) -> bool:
        u = bid.utility(slot_id)
        return u is not None and u >= bid.minimum_acceptance

    def commit(self, slot: Slot, inconvenience: float) -> None:
        self.p.busy.append(slot.interval)
        self.p.debt += inconvenience


class ResourceAgent:
    def __init__(self, resource: Resource):
        self.r = resource

    def available(self, slot: Slot, headcount: int) -> bool:
        return headcount <= self.r.capacity and not any(overlaps(slot.interval, b) for b in self.r.busy)

    def reserve(self, slot: Slot) -> None:
        self.r.busy.append(slot.interval)

    def release(self, slot: Slot) -> None:
        self.r.busy = [b for b in self.r.busy if b != slot.interval]


def make_grid(start, days: int, hours: tuple[int, int], slot_minutes: int, duration_minutes: int) -> list[Slot]:
    """Candidate slots on a regular grid (start every ``slot_minutes`` inside hours)."""
    out: list[Slot] = []
    for d in range(days):
        day = start + timedelta(days=d)
        if day.weekday() >= 5:
            continue
        t = day.replace(hour=hours[0], minute=0, second=0, microsecond=0)
        close = day.replace(hour=hours[1], minute=0, second=0, microsecond=0)
        while t + timedelta(minutes=duration_minutes) <= close:
            out.append(Slot(t.strftime("%a%d-%H%M").lower(), t, t + timedelta(minutes=duration_minutes)))
            t += timedelta(minutes=slot_minutes)
    return out
