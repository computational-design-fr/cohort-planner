"""dcop — distributed meeting scheduling for co-learning environments.

DCOP formulation after MULBS (JNCA 2011) solved by local-search algorithms
(DSA, MGM) wrapped in a bid-based negotiation protocol that keeps calendars private.
"""
from .model import Bid, Meeting, Participant, Problem, Resource, Slot
from .negotiation import Coordinator, ScheduleResult
from .solvers import DSA, MGM, SOLVERS

__all__ = ["Bid", "Coordinator", "DSA", "MGM", "Meeting", "Participant", "Problem", "Resource", "SOLVERS", "ScheduleResult", "Slot"]
