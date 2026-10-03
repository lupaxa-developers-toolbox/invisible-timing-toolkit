"""Public export surface."""

from __future__ import annotations

import lupaxa.invisible_timing_toolkit as invisible_timing


def test_public_names_are_exported() -> None:
    for name in (
        "LOGGER_NAME",
        "HookInstallError",
        "InvisibleTimingError",
        "InvisibleTimingManager",
        "__version__",
        "apply",
        "disable",
        "enable",
        "get_version",
    ):
        assert hasattr(invisible_timing, name)
        assert name in invisible_timing.__all__
