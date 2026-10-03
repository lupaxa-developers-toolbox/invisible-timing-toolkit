"""Restore process-wide hooks installed by timing tests."""

from __future__ import annotations

import builtins
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import suppress

import pytest


@pytest.fixture(autouse=True)
def restore_process_hooks() -> Iterator[None]:
    """Put builtins and stdlib callables back after each test."""
    saved_range = builtins.range
    saved_open = builtins.open
    saved_import = builtins.__import__
    saved_run = subprocess.run
    saved_profile = sys.getprofile()
    saved_execute = sqlite3.Cursor.execute
    saved_request: object | None = None
    try:
        import requests
    except ImportError:
        requests = None  # type: ignore[assignment]
    else:
        saved_request = requests.sessions.Session.request

    yield

    builtins.range = saved_range
    builtins.open = saved_open
    builtins.__import__ = saved_import
    subprocess.run = saved_run
    sys.setprofile(saved_profile)
    threading.setprofile(None)
    with suppress(TypeError, AttributeError):
        sqlite3.Cursor.execute = saved_execute  # type: ignore[method-assign]
    if requests is not None and saved_request is not None:
        requests.sessions.Session.request = saved_request  # type: ignore[method-assign]
