from .base import SolveResult, Solver
from .dsa import DSA
from .mgm import MGM

SOLVERS: dict[str, type[Solver]] = {"dsa": DSA, "mgm": MGM}

__all__ = ["DSA", "MGM", "SOLVERS", "SolveResult", "Solver"]
