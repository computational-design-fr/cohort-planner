from dataclasses import replace

from dcop.agents import ParticipantAgent
from dcop.model import Participant
from dcop.relaxation import relax

from conftest import day


def _agents(problem):
    return {p.id: ParticipantAgent(p) for p in problem.participants.values()}


def test_no_common_slot_falls_back_to_async(problem):
    out = relax(problem, problem.meetings["pair"], _agents(problem))
    assert out.kind == "asynchronous" and out.level == 6
    assert out.fallback["fallback_type"] == "asynchronous"
    assert out.meetings == []


def test_without_fallback_it_escalates(problem):
    m = replace(problem.meetings["pair"], fallback={})
    out = relax(problem, m, _agents(problem))
    assert out.kind == "escalate" and out.level == 7
    assert "escalate" in out.trace[-1]


def test_relaxing_preferences_keeps_attendance(problem):
    # mentor only free 17-18 (off-hours, utility 0.4 < its 0.99 threshold) → level 2
    mentor = problem.participants["mentor"]
    mentor.busy = [day(d, 9, 17) for d in range(5)]
    mentor.minimum_acceptance = 0.99
    out = relax(problem, problem.meetings["a"], _agents(problem))
    assert out.kind == "preferences" and out.level == 2
    m2 = out.meetings[0]
    assert m2.min_attendance == len(m2.participants)
    assert all(b.minimum_acceptance == 0.0 for b in out.bids[m2.id].values())


def test_shorten_before_split(problem):
    # ana free only 17:00-17:30 each day → 60 min impossible, 30 min possible
    ana = problem.participants["ana"]
    ana.busy = [day(d, 9, 17) for d in range(5)] + [(day(d, 17, 18)[0].replace(minute=30), day(d, 17, 18)[1]) for d in range(5)]
    m = replace(problem.meetings["a"], mandatory=["mentor", "ana"])
    out = relax(problem, m, _agents(problem))
    assert out.kind == "shortened" and out.meetings[0].duration_minutes == 30


def test_split_group_when_shortening_fails(problem):
    # two optional learners never free together, each free with the mentor
    problem.participants["l1"] = Participant("l1", busy=[day(d, 9, 18) for d in (1, 2, 3, 4)])
    problem.participants["l2"] = Participant("l2", busy=[day(d, 9, 18) for d in (0, 1, 3, 4)])
    m = replace(problem.meetings["a"], participants=["mentor", "l1", "l2"], mandatory=["mentor"], min_attendance=3, resource=None)
    out = relax(problem, m, _agents(problem))
    assert out.kind == "split" and out.level == 4 and len(out.meetings) == 2
    assert {tuple(x.participants) for x in out.meetings} == {("mentor", "l1"), ("mentor", "l2")}


def test_partial_attendance_before_async(problem):
    m = replace(problem.meetings["a"], participants=["mentor", "ana", "zed"], mandatory=["mentor"], min_attendance=3, resource=None)
    out = relax(problem, m, _agents(problem))  # zed busy all week; split needs both halves feasible
    assert out.kind == "partial" and out.level == 5
    assert out.meetings[0].min_attendance == 1
