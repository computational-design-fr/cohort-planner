"""Standalone HTML report: ``ui/index.html`` with the result JSON injected."""
from __future__ import annotations

import json
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "ui" / "index.html"
MARKER = "/*__DCOP_RESULT__*/"


def render_html(result: dict, title: str | None = None) -> str:
    html = UI.read_text(encoding="utf-8")
    slim = {k: v for k, v in result.items() if k != "reservations"}  # the UI never reads them; keeps the page small
    payload = json.dumps(slim, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace(MARKER + "null", MARKER + payload, 1)
    if title:
        html = html.replace("<title>Cohort Planner</title>", f"<title>Cohort Planner · {title}</title>", 1)
    return html
