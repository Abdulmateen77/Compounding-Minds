"""Evaluation: frozen twins, baselines, held-out split, quality report (BRIEF_HERMES H2).

Everything here works on plain `Scored` records, so it runs and tests without a database.
"""
from .metrics import Scored

__all__ = ["Scored"]
