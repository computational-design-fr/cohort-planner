from dcop.agents import ParticipantAgent
from dcop.constraints import feasible, pairwise_conflict, violations
from dcop.model import Slot, overlaps

from conftest import MONDAY, day


def test_overlap_is_strict():
    a = day(0, 9, 10)
    assert not overlaps(a, day(0, 10, 11))  # touching intervals do not overlap
    assert overlaps(a, day(0, 9, 10))
    assert overlaps(a, (a[0], a[1]))


def test_bid_hides_calendar_and_respects_busy(problem):
    m = problem.meetings["a"]
    bid = ParticipantAgent(problem.participants["ana"]).bid(m, extended=True)
    assert not hasattr(bid, "busy")
    ids = {b.slot_id for b in bid.candidate_slots}
    assert not any(s.startswith("tue15") for s in ids)  # ana busy all Tuesday
    assert all(0.0 <= b.utility <= 1.0 for b in bid.candidate_slots)
    assert bid.candidate_slots == sorted(bid.candidate_slots, key=lambda b: -b.utility)


def test_recurring_bid_requires_every_occurrence(problem):
    ana = problem.participants["ana"]
    ana.busy.append(day(7, 9, 18))  # next Monday busy => no Monday slot for the 2-week series
    bid = ParticipantAgent(ana).bid(problem.meetings["b"], extended=True)
    assert not any(b.slot_id.startswith("mon14") for b in bid.candidate_slots)


def test_feasible_needs_mandatory_and_resource(problem):
    m = problem.meetings["a"]
    bids = {p: ParticipantAgent(problem.participants[p]).bid(m, extended=True) for p in m.participants}
    thu = next(s for s in m.candidate_slots if s.id == "thu17-1000")
    assert not feasible(problem, m, thu, bids)  # room busy Thursday
    mon_am = next(s for s in m.candidate_slots if s.id == "mon14-1000")
    assert not feasible(problem, m, mon_am, bids)  # mentor (mandatory) busy
    ok = next(s for s in m.candidate_slots if s.id == "mon14-1400")
    assert feasible(problem, m, ok, bids)


def test_pairwise_conflict_and_violations(problem):
    assert pairwise_conflict(problem, "a", "mon14-1400", "b", "mon14-1430")
    assert not pairwise_conflict(problem, "a", "mon14-1400", "b", "mon14-1500")
    bids = {mid: {p: ParticipantAgent(problem.participants[p]).bid(m, extended=True) for p in m.participants}
            for mid, m in problem.meetings.items()}
    v = violations(problem, {"a": "mon14-1400", "b": "mon14-1430", "pair": None}, bids)
    assert any("overlaps" in x for x in v)
