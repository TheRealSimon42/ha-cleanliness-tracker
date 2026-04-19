"""Pure-logic soil calculator. No Home Assistant imports allowed.

This module is the single source of truth for the score formulas. It is kept
free of any Home Assistant dependency so it can be exercised at 100 % line +
branch coverage from plain pytest.
"""

from __future__ import annotations

# TODO(phase-1.1): implement compute_score_delta() and apply_delta() via TDD.
