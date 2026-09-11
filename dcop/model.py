"""Canonical data model for distributed meeting scheduling (DCOP formulation).

Formulation (after MULBS, Journal of Network and Computer Applications 2011):
- one DCOP variable per meeting, domain = its candidate slots;
- hard constraints: no overlap for a shared participant/resource, capacity,
  availability of every mandatory participant (per occurrence of a series);
- soft constraints: private unary utilities revealed only as *bids*.

Everything is a plain dataclass; time is timezone-aware ``datetime``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

Interval = tuple[datetime, datetime]


def overlaps(a: Interval, b: Interval) -> bool:
    return a[0] < b[1] and b[0] < a[1]


@dataclass(frozen=True)
class Slot:
    id: str
    start: datetime
    end: datetime

    @property
    def interval(self) -> Interval:
        return (self.start, self.end)

    def shifted(self, weeks: int) -> "Slot":
        d = timedelta(weeks=weeks)
        return Slot(f"{self.id}+{weeks}w", self.start + d, self.end + d)

    def shortened(self, minutes: int) -> "Slot":
        return Slot(f"{self.id}~{minutes}m", self.start, self.start + timedelta(minutes=minutes))


@dataclass
class Participant:
    """A learner or facilitator. ``busy`` and ``preferred_hours`` are PRIVATE:
    only the owning agent reads them; the coordinator sees bids."""

    id: str
    role: str = "learner"  # learner | facilitator | expert
    busy: list[Interval] = field(default_factory=list)
    preferred_hours: tuple[int, int] = (9, 18)
    off_hours_utility: float = 0.4
    minimum_acceptance: float = 0.5
    max_bids: int = 8
    debt: float = 0.0  # cumulative inconvenience D_p
    email: str | None = None  # calendar-provider identity (see dcop.calendar)


@dataclass
class Resource:
    id: str
    kind: str = "room"  # room | video | equipment
    capacity: int = 100
    busy: list[Interval] = field(default_factory=list)
    cost_per_hour: float = 0.0


@dataclass
class Meeting:
    id: str
    title: str
    participants: list[str]
    duration_minutes: int
    facilitator: str | None = None
    mandatory: list[str] = field(default_factory=list)
    min_attendance: int | None = None  # default: all participants
    resource: str | None = None
    priority: int = 50
    recurrence_weeks: int = 1  # 1 = single occurrence
    candidate_slots: list[Slot] = field(default_factory=list)
    fallback: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.facilitator and self.facilitator not in self.participants:
            self.participants.insert(0, self.facilitator)
        if self.facilitator and self.facilitator not in self.mandatory:
            self.mandatory.append(self.facilitator)
        if self.min_attendance is None:
            self.min_attendance = len(self.participants)

    def occurrences(self, slot: Slot) -> list[Slot]:
        return [slot.shifted(k) for k in range(self.recurrence_weeks)]


@dataclass
class Problem:
    participants: dict[str, Participant]
    resources: dict[str, Resource]
    meetings: dict[str, Meeting]

    def neighbours(self, meeting_id: str) -> set[str]:
        """Meetings sharing a participant or a resource (DCOP constraint graph)."""
        m = self.meetings[meeting_id]
        out: set[str] = set()
        for o in self.meetings.values():
            if o.id == m.id:
                continue
            if set(m.participants) & set(o.participants):
                out.add(o.id)
            elif m.resource and m.resource == o.resource:
                out.add(o.id)
        return out


@dataclass(frozen=True)
class SlotBid:
    slot_id: str
    utility: float


@dataclass
class Bid:
    """What a participant agent reveals about one meeting: ranked feasible slots
    with a private-utility score, plus its acceptance threshold. Never the calendar."""

    session_id: str
    participant_id: str
    candidate_slots: list[SlotBid]
    minimum_acceptance: float

    def utility(self, slot_id: str) -> float | None:
        for b in self.candidate_slots:
            if b.slot_id == slot_id:
                return b.utility
        return None


Assignment = dict[str, str | None]  # meeting_id -> slot_id


@dataclass
class Reservation:
    resource_type: str  # participant | resource
    resource_id: str
    slot: Slot
    session_id: str
    status: str  # provisional | confirmed | released
    expires_at: datetime | None = None
