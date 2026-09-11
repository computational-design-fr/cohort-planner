"""Calendar-provider boundary. Providers never enter the DCOP core: they only
fill ``Participant.busy`` before bids are computed."""
from .graph import GraphSlot, SyncReport, apply_to_problem, availability_to_busy, parse_suggestions

__all__ = ["GraphSlot", "SyncReport", "apply_to_problem", "availability_to_busy", "parse_suggestions"]
