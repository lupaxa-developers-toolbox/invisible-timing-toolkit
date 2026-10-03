"""Opt-in runtime timing hooks for Python programs."""

from __future__ import annotations

from collections.abc import Set as AbstractSet

from .exceptions import HookInstallError, InvisibleTimingError
from .manager import LOGGER_NAME, InvisibleTimingManager
from .version import __version__, get_version

_manager = InvisibleTimingManager()


def enable(
    *,
    func: bool = False,
    loops: bool = False,
    files: bool = False,
    http: bool = False,
    sqlite: bool = False,
    subprocess: bool = False,
    imports: bool = False,
    modules: AbstractSet[str] | None = None,
    output: str = "stdout",
) -> None:
    """Enable the selected hooks and install them now.

    ``output`` is ``stdout`` by default. Pass ``stdout+logging`` to
    print and also log, or ``logging`` to send lines only to the
    ``invisible_timing`` logger.
    """
    _manager.enable(
        func=func,
        loops=loops,
        files=files,
        http=http,
        sqlite=sqlite,
        subprocess=subprocess,
        imports=imports,
        modules=modules,
        output=output,
    )


def apply() -> None:
    """Install every hook that is currently enabled."""
    _manager.apply()


def disable() -> None:
    """Stop future hook installs.

    Callables that are already patched stay patched.
    """
    _manager.disable()


__all__ = [
    "LOGGER_NAME",
    "HookInstallError",
    "InvisibleTimingError",
    "InvisibleTimingManager",
    "__version__",
    "apply",
    "disable",
    "enable",
    "get_version",
]
