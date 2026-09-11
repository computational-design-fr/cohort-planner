# Calendar sync via Microsoft Graph (`find_meeting_availability`)

The MCP tool is called by the agent (Claude), not by Python. The recipe is two-step:

1. **Fetch availability** — one call per working day of the horizon, `duration` = the problem's
   `slot_minutes`, `maxCandidates=50` (the tool's cap; 30-min slots × 10 h = 20 per day):
   ```
   find_meeting_availability(participants=[<emails>], afterDateTime="2026-09-15T07:00:00Z",
                             beforeDateTime="2026-09-15T17:00:00Z", duration=30, maxCandidates=50)
   ```
   Save each raw answer to `examples/graph/<date>-<duration>min.json` and add the envelope key
   `"_organizer": "<signed-in email>"` — Graph reports the organizer only as `organizerAvailability`,
   other participants under `attendeeAvailability`. A day with no free slot comes back with
   `emptySuggestionsReason` and no suggestions (it becomes fully busy).
   Times are UTC wall-clock with `timeZone`; the adapter converts them to aware datetimes.
2. **Ingest** into a problem whose participants carry an `email`:
   ```bash
   python -m dcop.cli sync-graph examples/cohort_graph.json --graph examples/graph --out examples/cohort_graph.synced.json
   ```
   Without `--out` it is a dry run printing the report (synced participants, unconfirmed
   calendars, unmatched emails). Busy = horizon minus the union of `free` windows; `unknown`,
   `tentative`, `busy`, `oof` are all non-free, `unknown` is reported as unconfirmed.

`examples/graph/2026-09-1[4-8]-30min.json` are real answers for organizer@example.com fetched on
2026-09-11 (Monday 14th fully unavailable, Tue-Fri free 07:00-17:00 UTC).
