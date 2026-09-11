from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dcop.agents import make_grid  # noqa: E402
from dcop.model import Meeting, Participant, Problem, Resource  # noqa: E402

TZ = timezone(timedelta(hours=2))
MONDAY = datetime(2026, 9, 14, tzinfo=TZ)


def day(d: int, h0: int, h1: int):
    return (MONDAY + timedelta(days=d, hours=h0), MONDAY + timedelta(days=d, hours=h1))


@pytest.fixture
def problem() -> Problem:
    """3 meetings, 4 people, 1 room. ``bob`` and ``ana`` share two meetings so
    they must not overlap; ``pair`` has no common slot (busy all week)."""
    people = {
        "mentor": Participant("mentor", "facilitator", busy=[day(0, 9, 13)], preferred_hours=(9, 17)),
        "ana": Participant("ana", busy=[day(1, 9, 18)], preferred_hours=(9, 13), off_hours_utility=0.3),
        "bob": Participant("bob", busy=[day(2, 9, 18)], preferred_hours=(14, 18), off_hours_utility=0.3),
        "zed": Participant("zed", busy=[day(d, 9, 18) for d in range(5)]),
    }
    room = {"room": Resource("room", capacity=4, busy=[day(3, 9, 18)])}
    grid = lambda mins: make_grid(MONDAY, 5, (9, 18), 30, mins)  # noqa: E731
    meetings = {
        "a": Meeting("a", "A", ["ana", "bob"], 60, facilitator="mentor", resource="room", priority=70, candidate_slots=grid(60)),
        "b": Meeting("b", "B", ["ana", "bob"], 60, resource="room", priority=50, recurrence_weeks=2, candidate_slots=grid(60)),
        "pair": Meeting("pair", "pair", ["zed", "ana"], 60, mandatory=["zed", "ana"], candidate_slots=grid(60),
                        fallback={"materials": ["notes"], "deadline": "2026-09-20"}),
    }
    return Problem(people, room, meetings)
