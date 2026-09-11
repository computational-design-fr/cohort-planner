from datetime import timedelta

from dcop.negotiation import Coordinator

from conftest import MONDAY


def test_protocol_end_to_end(problem):
    res = Coordinator(problem, solver="mgm", seed=1).schedule(now=MONDAY)
    by_id = {s.meeting.id: s for s in res.sessions}
    assert res.violations == []
    assert by_id["a"].status == "confirmed" and by_id["b"].status == "confirmed"
    assert by_id["pair"].status == "asynchronous"
    assert by_id["pair"].relaxation.fallback["fallback_type"] == "asynchronous"
    # every confirmed occurrence has a confirmed reservation with a TTL, incl. the room
    confirmed = [r for r in res.reservations if r.status == "confirmed"]
    assert {r.session_id for r in confirmed} == {"a", "b"}
    assert all(r.expires_at == MONDAY + timedelta(minutes=30) for r in confirmed)
    assert sum(1 for r in confirmed if r.session_id == "b" and r.resource_type == "resource") == 2  # 2 weeks


def test_priority_meeting_is_placed_first_and_fairness_reported(problem):
    res = Coordinator(problem, solver="dsa", seed=4).schedule(now=MONDAY)
    ids = [s.meeting.id for s in res.confirmed]
    assert ids.index("a") < ids.index("b")
    for s in res.confirmed:
        assert set(s.utilities) == set(s.meeting.participants)
        assert min(s.utilities.values()) >= 0.0


def test_debt_accumulates_for_inconvenienced_participants(problem):
    coord = Coordinator(problem, seed=1)
    coord.schedule(now=MONDAY)
    debts = {p: coord.agents[p].p.debt for p in ("ana", "bob")}
    assert any(d > 0 for d in debts.values())  # ana (mornings) vs bob (afternoons) cannot both be happy
