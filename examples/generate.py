"""Deterministic generator of realistic co-learning scheduling problems.

    python examples/generate.py --seed 1 --learners 30 --mentors 4 --meetings 18 --out examples/cohort_large.json
    python examples/generate.py --preset conflict --out examples/cohort_conflict.json

Profiles: morning / afternoon / evening people with different busy loads; a
share of meetings are weekly series; a few meetings pair people who can never
meet (with an asynchronous fallback) so the relaxation ladder is exercised.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=2))
PROFILES = {  # preferred hours, off-hours utility, busy blocks per day (mean)
    "morning": ((9, 13), 0.3, 1.2),
    "office": ((9, 18), 0.5, 1.6),
    "afternoon": ((13, 19), 0.35, 1.2),
    "evening": ((17, 19), 0.2, 2.2),
}
TOPICS = ["python-async", "geospatial", "rhino-compute", "ml-basics", "peer-review", "design-crit", "git-workflow",
          "data-viz", "open-source", "career-circle", "retro", "kata"]


def iso(d: datetime) -> str:
    return d.isoformat()


def busy_blocks(rng: random.Random, start: datetime, days: int, hours: tuple[int, int], load: float, all_day_p: float):
    out = []
    for d in range(days):
        day = start + timedelta(days=d)
        if day.weekday() >= 5:
            continue
        if rng.random() < all_day_p:
            out.append([iso(day.replace(hour=hours[0])), iso(day.replace(hour=hours[1]))])
            continue
        n = max(0, int(round(rng.gauss(load, 0.8))))
        for _ in range(n):
            h = rng.randint(hours[0], hours[1] - 1)
            length = rng.choice([1, 1, 2, 3])
            out.append([iso(day.replace(hour=h)), iso(day.replace(hour=min(hours[1], h + length)))])
    return out


def generate(seed: int, learners: int, mentors: int, meetings: int, days: int = 5, rooms: int = 3,
             preset: str = "normal", start: str = "2026-09-14") -> dict:
    rng = random.Random(seed)
    hours = (9, 19)
    t0 = datetime.fromisoformat(start).replace(tzinfo=TZ)
    tight = preset == "conflict"
    participants = []
    for i in range(mentors):
        prof = rng.choice(list(PROFILES))
        pref, off, load = PROFILES[prof]
        participants.append({"id": f"mentor-{i+1:02d}", "role": "facilitator", "preferred_hours": list(pref), "off_hours_utility": off,
                             "busy": busy_blocks(rng, t0, days, hours, load * (2.2 if tight else 1.0), 0.35 if tight else 0.1)})
    for i in range(learners):
        prof = rng.choice(list(PROFILES))
        pref, off, load = PROFILES[prof]
        participants.append({"id": f"learner-{i+1:02d}", "preferred_hours": list(pref), "off_hours_utility": off,
                             "minimum_acceptance": rng.choice([0.4, 0.5, 0.5, 0.6]),
                             "busy": busy_blocks(rng, t0, days, hours, load * (1.6 if tight else 1.0), 0.25 if tight else 0.08)})
    resources = [{"id": f"room-{chr(97+i)}", "kind": "room", "capacity": (4 if tight else rng.choice([6, 8, 12, 20])),
                  "cost_per_hour": rng.choice([0, 10, 25]), "busy": busy_blocks(rng, t0, days, hours, 1.0 if tight else 0.4, 0.0)}
                 for i in range(rooms)]
    resources.append({"id": "video-1", "kind": "video", "capacity": 50, "cost_per_hour": 0})
    learner_ids = [p["id"] for p in participants if p["role"] == "learner"] if False else [p["id"] for p in participants if "learner" in p["id"]]
    mentor_ids = [p["id"] for p in participants if "mentor" in p["id"]]
    out_meetings = []
    for k in range(meetings):
        topic = TOPICS[k % len(TOPICS)]
        size = rng.choice([2, 3, 4, 5, 6, 8]) if not tight else rng.choice([4, 5, 6, 8])
        group = rng.sample(learner_ids, min(size, len(learner_ids)))
        m = {"id": f"{topic}-{k+1:02d}", "title": f"{topic.replace('-', ' ').title()} #{k+1}",
             "duration_minutes": rng.choice([30, 60, 60, 90, 120]), "participants": group,
             "priority": rng.randint(20, 90)}
        if rng.random() < 0.7:
            m["facilitator"] = rng.choice(mentor_ids)
        if rng.random() < 0.3:
            m["recurrence_weeks"] = rng.choice([2, 3, 4])
        if rng.random() < 0.6:
            m["resource"] = rng.choice(resources)["id"]
        if rng.random() < 0.4:
            m["min_attendance"] = max(1, len(group) - 1)
        if rng.random() < 0.5:
            m["fallback"] = {"materials": [f"{topic}-notes", "exercise-set"], "deadline": iso(t0 + timedelta(days=days + 2)),
                             "required_evidence": ["submitted-exercise"]}
        out_meetings.append(m)
    # one deliberately impossible pairing: both members busy the whole horizon
    if learners >= 2:
        a, b = rng.sample(learner_ids, 2)
        for p in participants:
            if p["id"] in (a, b):
                p["busy"] = [[iso(t0 + timedelta(days=d, hours=hours[0])), iso(t0 + timedelta(days=d, hours=hours[1]))] for d in range(days)]
        out_meetings.append({"id": "pair-impossible", "title": "Pair kata (no common slot)", "duration_minutes": 60,
                             "participants": [a, b], "mandatory": [a, b], "priority": 10,
                             "fallback": {"materials": ["kata", "recording"], "deadline": iso(t0 + timedelta(days=days + 2)),
                                          "required_evidence": ["submitted-exercise", "peer-review"]}})
    return {"generated": {"seed": seed, "learners": learners, "mentors": mentors, "meetings": meetings, "preset": preset},
            "horizon": {"start": iso(t0), "days": days, "hours": list(hours), "slot_minutes": 30},
            "participants": participants, "resources": resources, "meetings": out_meetings}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--learners", type=int, default=12)
    ap.add_argument("--mentors", type=int, default=2)
    ap.add_argument("--meetings", type=int, default=8)
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--rooms", type=int, default=3)
    ap.add_argument("--preset", choices=["normal", "conflict"], default="normal")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    data = generate(a.seed, a.learners, a.mentors, a.meetings, a.days, a.rooms, a.preset)
    Path(a.out).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{a.out}: {len(data['participants'])} participants, {len(data['resources'])} resources, {len(data['meetings'])} meetings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
