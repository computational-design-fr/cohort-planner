from datetime import datetime, timedelta, timezone

from dcop.calendar import apply_to_problem, availability_to_busy, parse_suggestions
from dcop.model import Participant

UTC = timezone.utc


def _slot(day: int, h: int, m: int, organizer="free", attendees=()):
    s = datetime(2026, 9, day, h, m, tzinfo=UTC)
    return {"meetingTimeSlot": {"start": {"dateTime": s.strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"},
                                "end": {"dateTime": (s + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"}},
            "confidence": 100, "organizerAvailability": organizer,
            "attendeeAvailability": [{"attendee": {"emailAddress": {"address": e}}, "availability": a} for e, a in attendees]}


def _payload():
    return {"_organizer": "organizer@example.com", "unavailableParticipants": ["ghost@x.io"],
            "meetingTimeSuggestions": [
                _slot(15, 7, 0, attendees=[("lea@x.io", "free")]),
                _slot(15, 7, 30, attendees=[("lea@x.io", "free")]),
                _slot(15, 9, 0, attendees=[("lea@x.io", "busy")]),
            ]}


def test_parse_handles_organizer_attendees_and_fractions():
    slots = parse_suggestions(_payload())
    assert len(slots) == 3 and slots[0].start.tzinfo is not None
    assert slots[0].availability == {"organizer@example.com": "free", "lea@x.io": "free", "ghost@x.io": "unknown"}
    assert slots[0].end - slots[0].start == timedelta(minutes=30)


def test_busy_is_complement_of_merged_free_windows():
    slots = parse_suggestions(_payload())
    h0, h1 = datetime(2026, 9, 15, 7, tzinfo=UTC), datetime(2026, 9, 15, 17, tzinfo=UTC)
    assert availability_to_busy(slots, h0, h1, "lea@x.io") == [(datetime(2026, 9, 15, 8, tzinfo=UTC), h1)]
    assert availability_to_busy(slots, h0, h1, "organizer@example.com") == [
        (datetime(2026, 9, 15, 8, tzinfo=UTC), datetime(2026, 9, 15, 9, tzinfo=UTC)),
        (datetime(2026, 9, 15, 9, 30, tzinfo=UTC), h1)]
    assert availability_to_busy(slots, h0, h1, "ghost@x.io") == [(h0, h1)]  # unknown → conservative


def test_apply_to_problem_uses_participant_email_and_reports(problem):
    problem.participants["sp"] = Participant("sp", "facilitator", email="organizer@example.com")
    problem.participants["ana"].email = "lea@x.io"
    h = (datetime(2026, 9, 14, 7, tzinfo=UTC), datetime(2026, 9, 18, 17, tzinfo=UTC))
    rep = apply_to_problem(problem, [_payload()], horizon=h)
    assert rep.synced == {"sp": 2, "ana": 1}
    assert rep.unconfirmed == [] and rep.unmatched == ["ghost@x.io"]
    assert problem.participants["sp"].busy[0] == (h[0], datetime(2026, 9, 15, 7, tzinfo=UTC))  # Monday: no suggestion → busy
    assert problem.participants["bob"].busy  # untouched: no email
    assert any("synced sp" in line for line in rep.lines())


def test_empty_day_payload_makes_whole_horizon_busy(problem):
    problem.participants["ana"].email = "organizer@example.com"
    h = (datetime(2026, 9, 14, 7, tzinfo=UTC), datetime(2026, 9, 14, 17, tzinfo=UTC))
    rep = apply_to_problem(problem, [{"_organizer": "organizer@example.com", "emptySuggestionsReason": "OrganizerUnavailable",
                                      "meetingTimeSuggestions": []}], horizon=h)
    assert rep.synced == {"ana": 0} and problem.participants["ana"].busy == [h]
