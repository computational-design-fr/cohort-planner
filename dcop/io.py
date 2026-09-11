"""JSON loading of a problem and dumping of a schedule result."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .agents import make_grid
from .model import Meeting, Participant, Problem, Resource
from .negotiation import ScheduleResult


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _intervals(raw: list) -> list:
    return [(_dt(a), _dt(b)) for a, b in raw]


def load_problem(path: str | Path) -> Problem:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    h = data["horizon"]
    start = _dt(h["start"])
    participants = {
        p["id"]: Participant(
            id=p["id"], role=p.get("role", "learner"), busy=_intervals(p.get("busy", [])),
            preferred_hours=tuple(p.get("preferred_hours", (9, 18))),
            off_hours_utility=p.get("off_hours_utility", 0.4),
            minimum_acceptance=p.get("minimum_acceptance", 0.5), max_bids=p.get("max_bids", 8),
            email=p.get("email"),
        )
        for p in data["participants"]
    }
    resources = {
        r["id"]: Resource(r["id"], r.get("kind", "room"), r.get("capacity", 100), _intervals(r.get("busy", [])),
                          r.get("cost_per_hour", 0.0))
        for r in data.get("resources", [])
    }
    meetings = {}
    for m in data["meetings"]:
        slots = make_grid(start, h["days"], tuple(h.get("hours", (9, 18))), h.get("slot_minutes", 30), m["duration_minutes"])
        meetings[m["id"]] = Meeting(
            id=m["id"], title=m.get("title", m["id"]), participants=list(m["participants"]),
            duration_minutes=m["duration_minutes"], facilitator=m.get("facilitator"),
            mandatory=list(m.get("mandatory", [])), min_attendance=m.get("min_attendance"),
            resource=m.get("resource"), priority=m.get("priority", 50),
            recurrence_weeks=m.get("recurrence_weeks", 1), candidate_slots=slots, fallback=m.get("fallback", {}),
        )
    return Problem(participants, resources, meetings)


def problem_horizon(path: str | Path) -> tuple[datetime, datetime]:
    """(start of first day, end of last day) of a problem file's horizon, aware."""
    h = json.loads(Path(path).read_text(encoding="utf-8"))["horizon"]
    start = _dt(h["start"])
    from datetime import timedelta
    return start, start + timedelta(days=h["days"])


def load_graph_payloads(paths: list[str | Path]) -> list[dict]:
    """Raw ``find_meeting_availability`` answers saved as JSON (files or directories)."""
    out: list[dict] = []
    for p in paths:
        p = Path(p)
        files = sorted(p.glob("*.json")) if p.is_dir() else [p]
        for f in files:
            out.append(json.loads(f.read_text(encoding="utf-8")))
    return out


def problem_to_dict(problem: Problem) -> dict:
    """Serialise a (synced) problem back to the input JSON shape; slots are regenerated on load."""
    def iv(v):
        return [[a.isoformat(), b.isoformat()] for a, b in v]
    return {
        "participants": [
            {"id": p.id, "role": p.role, "email": p.email, "busy": iv(p.busy), "preferred_hours": list(p.preferred_hours),
             "off_hours_utility": p.off_hours_utility, "minimum_acceptance": p.minimum_acceptance, "max_bids": p.max_bids}
            for p in problem.participants.values()
        ],
        "resources": [
            {"id": r.id, "kind": r.kind, "capacity": r.capacity, "busy": iv(r.busy), "cost_per_hour": r.cost_per_hour}
            for r in problem.resources.values()
        ],
        "meetings": [
            {"id": m.id, "title": m.title, "duration_minutes": m.duration_minutes, "facilitator": m.facilitator,
             "participants": [p for p in m.participants if p != m.facilitator], "mandatory": [p for p in m.mandatory if p != m.facilitator],
             "min_attendance": m.min_attendance, "resource": m.resource, "priority": m.priority,
             "recurrence_weeks": m.recurrence_weeks, "fallback": m.fallback}
            for m in problem.meetings.values()
        ],
    }


def result_to_dict(res: ScheduleResult) -> dict:
    return {
        "solver": res.solver,
        "rounds": res.rounds,
        "messages": res.messages,
        "cost_history": res.history,
        "violations": res.violations,
        "horizon": None if res.horizon is None else {"start": res.horizon[0].isoformat(), "end": res.horizon[1].isoformat()},
        "participants": res.participants,
        "sessions": [
            {
                "id": s.meeting.id,
                "title": s.meeting.title,
                "status": s.status,
                "slot": None if s.slot is None else {"id": s.slot.id, "start": s.slot.start.isoformat(), "end": s.slot.end.isoformat()},
                "recurrence_weeks": s.meeting.recurrence_weeks,
                "participants": s.meeting.participants,
                "mandatory": s.meeting.mandatory,
                "resource": s.meeting.resource,
                "duration_minutes": s.meeting.duration_minutes,
                "priority": s.meeting.priority,
                "score": s.score,
                "utilities": s.utilities,
                "min_utility": min(s.utilities.values()) if s.utilities else None,
                "relaxation": None if s.relaxation is None else {"level": s.relaxation.level, "kind": s.relaxation.kind, "fallback": s.relaxation.fallback},
                "trace": s.trace,
            }
            for s in res.sessions
        ],
        "reservations": [
            {**{k: v for k, v in asdict(r).items() if k not in ("slot", "expires_at")},
             "start": r.slot.start.isoformat(), "end": r.slot.end.isoformat(),
             "expires_at": r.expires_at.isoformat() if r.expires_at else None}
            for r in res.reservations
        ],
    }
