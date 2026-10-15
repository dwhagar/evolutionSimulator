"""The error the run store raises."""

from __future__ import annotations


class RunError(Exception):
    """A run cannot be created, found, opened or resumed."""
