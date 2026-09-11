# Cohort Planner — distributed meeting scheduling for co-learning

Python (3.11+, **stdlib only**) implementation of distributed meeting scheduling as a
**DCOP** (Distributed Constraint Optimization Problem), for co-learning cohorts:
learners, facilitators, rooms/video channels, single or weekly sessions.

Sources:
- *Distributed constraint optimization with MULBS: a case study on collaborative meeting
  scheduling*, Journal of Network and Computer Applications, 2011
  ([S1084804511000543](https://www.sciencedirect.com/science/article/pii/S1084804511000543)) —
  DCOP formulation: meetings are variables, time slots are values, constraints are
  agreement / non-overlap / availability, preferences are soft costs.
- a private design note (not in the repo) — agent
  roles, bid-based negotiation protocol, objective, fairness, relaxation ladder.
- `_archives (GH)/` — the 2016 Grasshopper "Co-Learning Planner" (visual prior art).

## Model (`dcop/model.py`)

| Object | Role |
|---|---|
| `Participant` | learner / facilitator. `busy`, `preferred_hours`, `minimum_acceptance`, `max_bids` are **private** to its agent. `debt` = cumulative inconvenience D_p. |
| `Resource` | room / video / equipment: capacity, busy intervals, hourly cost. |
| `Meeting` | DCOP variable: participants, mandatory ones, duration, `min_attendance`, resource, priority, `recurrence_weeks`, `candidate_slots` (domain), `fallback`. |
| `Bid` | what an agent reveals per meeting: ranked feasible `SlotBid(slot_id, utility)` + threshold. Never a calendar. |
| `Reservation` | provisional (with TTL) → confirmed / released, per participant and resource per occurrence. |

Hard constraints (`constraints.py`): every mandatory participant available on **every occurrence**
of a series, attendance ≥ `min_attendance`, resource free and large enough, no overlap between
meetings sharing a participant or a resource.

Objective (`objective.py`), maximised:  `U = w_a·A + w_p·P + w_f·F − w_i·I − w_c·C`
(A attendance, P mean utility, F fairness = min utility penalised by debt, I shortfall below
acceptance thresholds, C resource cost).

## Algorithms (`dcop/solvers/`)

Round-based simulation of local-search DCOP algorithms: each meeting is a variable agent that
only sees its own domain/costs and its neighbours' current values (`ValueMessage`).
Cost = `hard_penalty × #conflicts − U(m,t) × priority/50`.

- `dsa` — DSA-B: best response, move with probability `p` (default 0.7) when it improves or when in conflict.
- `mgm` — MGM: agents exchange `GainMessage`s, only the neighbourhood-maximal gainer moves; monotone.

Both stop after 3 quiet rounds or `max_rounds`; results carry rounds, message count, cost history.

## Negotiation protocol (`dcop/negotiation.py`)

1. session requests = `Problem.meetings` · 2. each agent computes feasible slots privately ·
3. ranked bids (top `max_bids`; the coordinator asks for *extended* bids only when no common slot
exists) · 4. common candidates · 5. DCOP local search · 6. provisional reservations with TTL ·
7. confirm (mandatory agents accept ≥ threshold) or repair with the next-best slot, then the
relaxation ladder · 8. publish (`ScheduledSession`).

Relaxation ladder (`relaxation.py`), never silent: 2 preferences → 3 shorten → 4 split optional
attendees → 5 partial attendance → 6 asynchronous fallback → 7 escalate to a human.

## Usage

```bash
PYTHONIOENCODING=utf-8 "C:/ProgramData/anaconda3/envs/os/python.exe" -m dcop.cli solve examples/cohort_week.json --solver mgm --seed 1 --json out.json
```

```python
from dcop import Coordinator
from dcop.io import load_problem, result_to_dict
res = Coordinator(load_problem("examples/cohort_week.json"), solver="dsa", seed=1).schedule()
for s in res.sessions: print(s.meeting.id, s.status, s.slot and s.slot.id, s.utilities)
```

Problem JSON: `horizon` (start, days, hours, slot_minutes), `participants`, `resources`, `meetings`
(see `examples/cohort_week.json`; `jun-nora-pair` has no common slot and lands on the async fallback).

## Calendar sync (Microsoft Graph)

Participants may carry an `email`. The agent calls the MCP tool `find_meeting_availability`
(one call per day, `duration = slot_minutes`, `maxCandidates = 50`), saves each raw answer under
`examples/graph/` with an `_organizer` key, then:

```bash
PYTHONIOENCODING=utf-8 "C:/ProgramData/anaconda3/envs/os/python.exe" -m dcop.cli sync-graph examples/cohort_graph.json --graph examples/graph --out examples/cohort_graph.synced.json
```

Busy = horizon minus the union of `free` windows (a day without suggestions is fully busy;
`unknown` calendars are non-free and reported). Recipe and caveats: `docs/graph-sync.md`.
`examples/graph/` holds real answers for organizer@example.com (week of 2026-09-14).

## Datasets

| File | What | Source |
|---|---|---|
| `examples/cohort_week.json` | 8 people, 7 meetings incl. a weekly series and an impossible pair | hand-made |
| `examples/cohort_small.json` | 5 people, 4 meetings, nominal | `generate.py --seed 1 --learners 4 --mentors 1 --meetings 3 --rooms 1` |
| `examples/cohort_large.json` | 34 people, 5 resources, 19 meetings | `generate.py --seed 1 --learners 30 --mentors 4 --meetings 18 --rooms 4` |
| `examples/cohort_conflict.json` | saturated mentors, 4-seat rooms → relaxation ladder | `generate.py --seed 7 … --preset conflict` |
| `examples/cohort_graph(.synced).json` | real organizer availability from Graph | `sync-graph` |

## Visual report

```bash
PYTHONIOENCODING=utf-8 "C:/ProgramData/anaconda3/envs/os/python.exe" -m dcop.cli solve examples/cohort_large.json --solver mgm --seed 1 --html out/cohort_large.html
```

Published reports: https://computational-design-fr.github.io/cohort-planner/ (`reports/`, GitHub Pages from the repo root).

`ui/index.html` is a static page (no build, no library): week grid with the confirmed blocks,
session rail (status, score, min utility, relaxation level, repair trace), participant × session
utility heatmap with the inconvenience debt, solver cost per round. It can also load any
`--json` result through its file picker.

## Tests

```bash
PYTHONIOENCODING=utf-8 "C:/ProgramData/anaconda3/envs/os/python.exe" -m pytest tests -q -p no:asyncio
```

## Not in v1

Cohort formation (who learns together), writing events back to the calendar (`outlook_create_event`),
persistence (the note's PostgreSQL schema), message broker, OR-Tools centralised solver. All are boundary
layers around the same `Bid` / `Reservation` objects.
