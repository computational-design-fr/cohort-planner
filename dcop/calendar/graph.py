"""Adapter for the Microsoft Graph MCP tool ``find_meeting_availability``.

The tool is called by the agent (Claude), not by Python; its raw JSON answer is
saved to disk and ingested here. One answer = up to 50 ``meetingTimeSlot``s of
``duration`` minutes; each carries ``organizerAvailability`` (the signed-in
user) and ``attendeeAvailability`` per other participant. A day with no free
slot comes back with ``emptySuggestionsReason`` and no suggestions.

A participant is *free* on a slot where its availability is ``free``; its busy
list is the complement of the union of those windows over the horizon.
``unknown`` / ``tentative`` / ``busy`` / ``oof`` are all treated as not free;
``unknown`` (calendar unreadable) is additionally reported as unconfirmed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..model import Interval, Problem

# Windows display names Graph may return → IANA
_WINDOWS_TZ = {
    "Romance Standard Time": "Europe/Paris",
    "W. Europe Standard Time": "Europe/Berlin",
    "GMT Standard Time": "Europe/London",
    "Central Europe Standard Time": "Europe/Warsaw",
    "Eastern Standard Time": "America/New_York",
    "Pacific Standard Time": "America/Los_Angeles",
    "UTC": "UTC",
}
_FRACTION = re.compile(r"\.\d+")


def _tz(name: str | None):
    if not name or name.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(_WINDOWS_TZ.get(name, name))
    except Exception:  # unknown zone name → UTC rather than crashing a sync
        return timezone.utc


def _dt(obj) -> datetime:
    """Graph ``{dateTime, timeZone}`` or ISO string → aware datetime."""
    raw, tz = (obj.get("dateTime"), obj.get("timeZone")) if isinstance(obj, dict) else (obj, None)
    raw = _FRACTION.sub("", raw.replace("Z", "+00:00"))
    d = datetime.fromisoformat(raw)
    return d if d.tzinfo else d.replace(tzinfo=_tz(tz))


@dataclass(frozen=True)
class GraphSlot:
    start: datetime
    end: datetime
    availability: dict[str, str]  # email (lower) → free | busy | tentative | unknown | oof
    confidence: float | None = None


@dataclass
class SyncReport:
    synced: dict[str, int] = field(default_factory=dict)  # participant id → number of free windows
    unconfirmed: list[str] = field(default_factory=list)  # emails with unknown availability
    unmatched: list[str] = field(default_factory=list)  # emails in payload without participant
    horizon: tuple[datetime, datetime] | None = None
    slots: int = 0

    def lines(self) -> list[str]:
        out = [f"slots ingested: {self.slots}"]
        if self.horizon:
            out.append(f"horizon: {self.horizon[0].isoformat()} -> {self.horizon[1].isoformat()}")
        for pid, n in self.synced.items():
            out.append(f"synced {pid}: {n} free window(s)")
        for e in self.unconfirmed:
            out.append(f"unconfirmed (calendar unreadable): {e}")
        for e in self.unmatched:
            out.append(f"no participant for email: {e}")
        return out


def _email(a: dict) -> str:
    e = a.get("attendee", a.get("email", ""))
    if isinstance(e, dict):
        e = e.get("emailAddress", e).get("address", "") if isinstance(e.get("emailAddress", e), dict) else e.get("address", "")
    return str(e).lower()


def parse_suggestions(payload: dict, organizer: str | None = None) -> list[GraphSlot]:
    """Normalise one raw answer. ``organizer`` (or payload["_organizer"]) names
    the signed-in user whose availability Graph reports as ``organizerAvailability``."""
    organizer = (organizer or payload.get("_organizer") or "").lower()
    out: list[GraphSlot] = []
    for s in payload.get("meetingTimeSuggestions") or []:
        slot = s.get("meetingTimeSlot") or s
        av: dict[str, str] = {}
        if organizer and "organizerAvailability" in s:
            av[organizer] = str(s["organizerAvailability"]).lower()
        for a in s.get("attendeeAvailability", []) or []:
            av[_email(a)] = str(a.get("availability", "unknown")).lower()
        for email in payload.get("unavailableParticipants") or []:
            av.setdefault(str(email).lower(), "unknown")
        conf = s.get("confidence")
        out.append(GraphSlot(_dt(slot["start"]), _dt(slot["end"]), av, float(conf) if conf is not None else None))
    out.sort(key=lambda g: g.start)
    return out


def _merge(intervals: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def free_windows(slots: list[GraphSlot], email: str) -> list[Interval]:
    email = email.lower()
    return _merge([(g.start, g.end) for g in slots if g.availability.get(email) == "free"])


def availability_to_busy(slots: list[GraphSlot], horizon_start: datetime, horizon_end: datetime, email: str) -> list[Interval]:
    """Busy = horizon minus the participant's free windows (conservative)."""
    busy: list[Interval] = []
    cursor = horizon_start
    for a, b in free_windows(slots, email):
        a, b = max(a, horizon_start), min(b, horizon_end)
        if a >= b:
            continue
        if a > cursor:
            busy.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < horizon_end:
        busy.append((cursor, horizon_end))
    return busy


def apply_to_problem(problem: Problem, payloads: list[dict], email_map: dict[str, str] | None = None,
                     horizon: tuple[datetime, datetime] | None = None) -> SyncReport:
    """Overwrite ``Participant.busy`` from Graph availability.

    ``email_map`` maps email → participant id; defaults to ``Participant.email``.
    ``horizon`` defaults to the span covered by the payload slots — pass the
    problem's horizon explicitly so days without any suggestion become busy.
    """
    slots = [g for p in payloads for g in parse_suggestions(p)]
    report = SyncReport(slots=len(slots))
    if not slots and horizon is None:
        return report
    h0, h1 = horizon or (min(g.start for g in slots), max(g.end for g in slots))
    report.horizon = (h0, h1)
    emap = {k.lower(): v for k, v in (email_map or {}).items()}
    for p in problem.participants.values():
        if p.email and p.email.lower() not in emap:
            emap[p.email.lower()] = p.id
    seen = {e for g in slots for e in g.availability} | {str(p.get("_organizer", "")).lower() for p in payloads} - {""}
    for email, pid in emap.items():
        if pid not in problem.participants or email not in seen:
            continue
        p = problem.participants[pid]
        p.busy = availability_to_busy(slots, h0, h1, email)
        report.synced[pid] = len(free_windows(slots, email))
        if any(g.availability.get(email) == "unknown" for g in slots):
            report.unconfirmed.append(email)
    report.unmatched = sorted(seen - set(emap))
    return report
