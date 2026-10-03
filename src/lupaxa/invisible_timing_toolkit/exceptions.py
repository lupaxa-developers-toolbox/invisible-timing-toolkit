"""Errors raised by ``lupaxa.invisible_timing_toolkit``."""

from __future__ import annotations


class InvisibleTimingError(Exception):
    """Base exception for invisible timing failures."""


class HookInstallError(InvisibleTimingError):
    """Raised when a timing hook fails to install."""
