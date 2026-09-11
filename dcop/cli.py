"""CLI:  python -m dcop.cli solve examples/cohort_week.json --solver mgm --seed 1 [--json out.json]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .io import load_graph_payloads, load_problem, problem_horizon, problem_to_dict, result_to_dict
from .negotiation import Coordinator
from .solvers import SOLVERS


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dcop")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("solve", help="run the negotiation protocol on a JSON problem")
    s.add_argument("problem")
    s.add_argument("--solver", choices=sorted(SOLVERS), default="mgm")
    s.add_argument("--seed", type=int, default=None)
    s.add_argument("--rounds", type=int, default=50)
    s.add_argument("--json", help="write full result to this file")
    s.add_argument("--html", help="write a standalone visual report (ui/index.html + result)")
    g = sub.add_parser("sync-graph", help="fill participants' busy lists from saved find_meeting_availability answers")
    g.add_argument("problem")
    g.add_argument("--graph", nargs="+", required=True, help="JSON files or directories of raw Graph answers")
    g.add_argument("--out", help="write the synced problem here (dry run without it)")
    a = ap.parse_args(argv)

    if a.cmd == "sync-graph":
        return sync_graph(a)

    problem = load_problem(a.problem)
    res = Coordinator(problem, solver=a.solver, seed=a.seed, max_rounds=a.rounds).schedule()
    out = result_to_dict(res)

    print(f"solver={res.solver} rounds={res.rounds} messages={res.messages} violations={len(res.violations)}")
    for sess in out["sessions"]:
        slot = sess["slot"]
        when = f"{slot['start'][:16]} -> {slot['end'][11:16]}" if slot else "-"
        rec = f" x{sess['recurrence_weeks']}w" if sess["recurrence_weeks"] > 1 else ""
        mu = "" if sess["min_utility"] is None else f" score={sess['score']:.2f} min_u={sess['min_utility']:.2f}"
        rel = f" [{sess['relaxation']['kind']} L{sess['relaxation']['level']}]" if sess["relaxation"] else ""
        print(f"  {sess['status']:<12} {sess['id']:<22} {when}{rec}{mu}{rel}")
        if sess["status"] != "confirmed":
            for t in sess["trace"]:
                print(f"      · {t}")
    for v in res.violations:
        print("  VIOLATION", v)
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    if a.html:
        from .report import render_html
        Path(a.html).parent.mkdir(parents=True, exist_ok=True)
        Path(a.html).write_text(render_html(out, title=Path(a.problem).stem), encoding="utf-8")
        print(f"report: {a.html}")
    return 1 if res.violations else 0


def sync_graph(a) -> int:
    from .calendar import apply_to_problem

    problem = load_problem(a.problem)
    payloads = load_graph_payloads(a.graph)
    report = apply_to_problem(problem, payloads, horizon=problem_horizon(a.problem))
    for line in report.lines():
        print("  " + line)
    if not a.out:
        print("dry run: pass --out to write the synced problem")
        return 0
    data = json.loads(Path(a.problem).read_text(encoding="utf-8"))
    data.update(problem_to_dict(problem))
    Path(a.out).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"written {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
