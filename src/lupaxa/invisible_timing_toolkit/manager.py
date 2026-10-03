"""Install opt-in timing hooks around selected runtime choke points."""

from __future__ import annotations

import builtins
import logging
import os
import subprocess as _subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from collections.abc import Set as AbstractSet
from types import FrameType, ModuleType
from typing import Any, cast

from .exceptions import HookInstallError

LOGGER_NAME = "invisible_timing"
logger = logging.getLogger(LOGGER_NAME)

_TRUTHY = {"1", "true", "yes"}

try:
    import requests as _requests
except ImportError:  # pragma: no cover
    requests: ModuleType | None = None
else:
    requests = _requests

try:
    import sqlite3 as _sqlite3
except ImportError:  # pragma: no cover
    sqlite3: ModuleType | None = None
else:
    sqlite3 = _sqlite3


_OUTPUTS = frozenset({"stdout", "stdout+logging", "logging"})


def _env_enabled(name: str) -> bool:
    """Return whether an environment flag is set to a truthy value."""
    return os.getenv(name, "0").lower() in _TRUTHY


def _output_from_env() -> str:
    """Return the output mode selected by ``INVISIBLE_TIMING_OUTPUT``."""
    value = os.getenv("INVISIBLE_TIMING_OUTPUT", "stdout").strip().lower()
    if value in _OUTPUTS:
        return value
    return "stdout"


def _check_output(value: str) -> str:
    """Return *value* when it names a known output mode."""
    if value not in _OUTPUTS:
        raise ValueError("output must be stdout, stdout+logging, or logging")
    return value


class InvisibleTimingManager:
    """Hold timing configuration and install each hook once.

    Importing the package builds one shared manager. Call
    :meth:`enable` to turn hooks on. :meth:`disable` only blocks later
    installs; it does not unpatch callables that are already wrapped.
    """

    def __init__(self) -> None:
        """Read environment defaults and install any hooks they select."""
        self.func_enabled = _env_enabled("INVISIBLE_TIMING")
        self.loops_enabled = _env_enabled("INVISIBLE_TIMING_LOOPS")
        self.files_enabled = _env_enabled("INVISIBLE_TIMING_FILES")
        self.http_enabled = _env_enabled("INVISIBLE_TIMING_HTTP")
        self.sqlite_enabled = _env_enabled("INVISIBLE_TIMING_SQLITE")
        self.subproc_enabled = _env_enabled("INVISIBLE_TIMING_SUBPROC")
        self.imports_enabled = _env_enabled("INVISIBLE_TIMING_IMPORTS")

        env_mods = os.getenv("INVISIBLE_TIMING_MODULES", "__main__")
        self.allowed_modules = {part.strip() for part in env_mods.split(",") if part.strip()}
        self.output = _output_from_env()

        self._func_installed = False
        self._loop_installed = False
        self._file_installed = False
        self._http_installed = False
        self._sqlite_installed = False
        self._subproc_installed = False
        self._import_installed = False

        self._original_range: Callable[..., Any] | None = None
        self._original_open: Callable[..., Any] | None = None
        self._original_requests_request: Callable[..., Any] | None = None
        self._original_sqlite_execute: Callable[..., Any] | None = None
        self._original_subprocess_run: Callable[..., Any] | None = None
        self._original_import: Callable[..., Any] | None = None

        self._thread_local = threading.local()
        self._this_module_name = __name__

        if any(
            (
                self.func_enabled,
                self.loops_enabled,
                self.files_enabled,
                self.http_enabled,
                self.sqlite_enabled,
                self.subproc_enabled,
                self.imports_enabled,
            )
        ):
            self.apply()

    def _call_starts(self) -> dict[int, float]:
        """Return the per-thread map of frame id to start time."""
        if not hasattr(self._thread_local, "call_starts"):
            self._thread_local.call_starts = {}
        starts: dict[int, float] = self._thread_local.call_starts
        return starts

    def _is_allowed_module(self, modname: str) -> bool:
        """Return whether *modname* matches a configured prefix."""
        if not modname or modname == self._this_module_name or not self.allowed_modules:
            return False
        return any(modname.startswith(prefix) for prefix in self.allowed_modules)

    def _write(self, message: str, *, level: int) -> None:
        """Send *message* to stdout, the logger, or both."""
        if self.output in {"logging", "stdout+logging"}:
            logger.log(level, message)
        if self.output in {"stdout", "stdout+logging"}:
            print(message, file=sys.stdout)

    def _emit(self, message: str) -> None:
        """Write one timing line."""
        self._write(message, level=logging.INFO)

    def _warn(self, message: str) -> None:
        """Write one skipped-hook notice."""
        self._write(message, level=logging.WARNING)

    def profile_callback(self, frame: FrameType, event: str, _arg: object) -> None:
        """Record function durations for modules selected by the caller."""
        if not self._func_installed:
            return

        call_starts = self._call_starts()
        if event == "call":
            call_starts[id(frame)] = time.perf_counter()
            return
        if event != "return":
            return

        start_time = call_starts.pop(id(frame), None)
        if start_time is None:
            return

        duration = time.perf_counter() - start_time
        modname = str(frame.f_globals.get("__name__", ""))
        if not self._is_allowed_module(modname):
            return

        self._emit(f"[FUNC] {modname}.{frame.f_code.co_name} took {duration:.6f}s")

    def _install_function_timing(self) -> None:
        """Install a process-wide ``sys.setprofile`` hook."""
        if self._func_installed:
            return
        sys.setprofile(self.profile_callback)
        threading.setprofile(self.profile_callback)
        self._func_installed = True
        logger.debug("Installed function timing hook")

    def _install_loop_timing(self) -> None:
        """Replace ``builtins.range`` with a generator that times each step."""
        if self._loop_installed:
            return
        if self._original_range is None:
            self._original_range = cast("Callable[..., Any]", builtins.range)

        original_range = self._original_range

        def _timed_range(*args: Any) -> Iterator[Any]:
            for index, value in enumerate(original_range(*args)):
                start = time.perf_counter()
                yield value
                elapsed = time.perf_counter() - start
                self._emit(f"[LOOP] range iteration {index} took {elapsed:.6f}s")

        builtins.range = _timed_range  # type: ignore[assignment,misc]
        self._loop_installed = True
        logger.debug("Installed loop timing hook")

    def _install_file_timing(self) -> None:
        """Wrap ``builtins.open`` and log how long the open takes."""
        if self._file_installed:
            return
        if self._original_open is None:
            self._original_open = cast("Callable[..., Any]", builtins.open)

        original_open = self._original_open

        def _timed_open(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            opened = original_open(*args, **kwargs)
            filename = args[0] if args else "<unknown>"
            elapsed = time.perf_counter() - start
            self._emit(f"[FILE] open({filename!r}) took {elapsed:.6f}s")
            return opened

        builtins.open = _timed_open  # type: ignore[assignment,misc]
        self._file_installed = True
        logger.debug("Installed file timing hook")

    def _install_http_timing(self) -> None:
        """Wrap ``requests.Session.request`` when requests is installed."""
        if self._http_installed:
            return
        http = requests
        if http is None:
            self._warn("requests is not available; HTTP timing skipped")
            return

        if self._original_requests_request is None:
            self._original_requests_request = cast(
                "Callable[..., Any]", http.sessions.Session.request
            )

        original_request = self._original_requests_request

        def _timed_request(
            self_: object,
            method: str,
            url: str,
            *args: object,
            **kwargs: object,
        ) -> object:
            start = time.perf_counter()
            response = original_request(self_, method, url, *args, **kwargs)
            elapsed = time.perf_counter() - start
            status = getattr(response, "status_code", "?")
            self._emit(f"[HTTP] {method.upper()} {url} took {elapsed:.6f}s (status={status})")
            return response

        http.sessions.Session.request = _timed_request  # type: ignore[method-assign]
        self._http_installed = True
        logger.debug("Installed HTTP timing hook")

    def _install_sqlite_timing(self) -> None:
        """Wrap ``sqlite3.Cursor.execute`` when the cursor type is mutable."""
        if self._sqlite_installed:
            return
        database = sqlite3
        if database is None:
            self._warn("sqlite3 is not available; sqlite timing skipped")
            return

        if self._original_sqlite_execute is None:
            try:
                self._original_sqlite_execute = cast("Callable[..., Any]", database.Cursor.execute)
            except AttributeError:
                self._warn("sqlite3.Cursor.execute not found; sqlite timing skipped")
                self._sqlite_installed = True
                return

        original_execute = self._original_sqlite_execute

        def _timed_execute(
            self_: object,
            sql: object,
            *args: object,
            **kwargs: object,
        ) -> object:
            start = time.perf_counter()
            result = original_execute(self_, sql, *args, **kwargs)
            elapsed = time.perf_counter() - start
            self._emit(f"[SQL] {sql!r} took {elapsed:.6f}s")
            return result

        try:
            database.Cursor.execute = _timed_execute  # type: ignore[method-assign]
        except (TypeError, AttributeError):
            self._warn("sqlite3.Cursor appears immutable; sqlite timing disabled for this runtime")
            self._sqlite_installed = True
            return

        self._sqlite_installed = True
        logger.debug("Installed sqlite timing hook")

    def _install_subprocess_timing(self) -> None:
        """Wrap :func:`subprocess.run` and log the duration and return code."""
        if self._subproc_installed:
            return
        if self._original_subprocess_run is None:
            self._original_subprocess_run = cast("Callable[..., Any]", _subprocess.run)

        original_run = self._original_subprocess_run

        def _timed_run(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            check_value = kwargs.pop("check", False)
            result = original_run(*args, check=check_value, **kwargs)
            elapsed = time.perf_counter() - start
            returncode = getattr(result, "returncode", "?")
            self._emit(
                f"[PROC] subprocess.run{args!r} took {elapsed:.6f}s (returncode={returncode})"
            )
            return result

        _subprocess.run = _timed_run  # type: ignore[assignment,misc]
        self._subproc_installed = True
        logger.debug("Installed subprocess timing hook")

    def _install_import_timing(self) -> None:
        """Wrap ``builtins.__import__`` and log each import duration."""
        if self._import_installed:
            return
        if self._original_import is None:
            self._original_import = cast("Callable[..., Any]", builtins.__import__)

        original_import = self._original_import

        def _timed_import(
            name: str,
            globalns: Mapping[str, object] | None = None,
            localns: Mapping[str, object] | None = None,
            fromlist: Sequence[str] | None = (),
            level: int = 0,
        ) -> ModuleType:
            start = time.perf_counter()
            module = original_import(name, globalns, localns, fromlist, level)
            elapsed = time.perf_counter() - start
            self._emit(f"[IMPORT] import {name!r} took {elapsed:.6f}s")
            return cast("ModuleType", module)

        builtins.__import__ = _timed_import  # type: ignore[assignment,misc]
        self._import_installed = True
        logger.debug("Installed import timing hook")

    def apply(self) -> None:
        """Install every hook whose flag is currently set."""
        try:
            if self.func_enabled:
                self._install_function_timing()
            if self.loops_enabled:
                self._install_loop_timing()
            if self.files_enabled:
                self._install_file_timing()
            if self.http_enabled:
                self._install_http_timing()
            if self.sqlite_enabled:
                self._install_sqlite_timing()
            if self.subproc_enabled:
                self._install_subprocess_timing()
            if self.imports_enabled:
                self._install_import_timing()
        except Exception as exc:
            logger.exception("Failed to install one of the timing hooks: %s", exc)
            raise HookInstallError("failed to install timing hook") from exc

    def enable(
        self,
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
        """Replace the enabled hooks with the flags passed here.

        Omitted flags are turned off. Pass ``modules`` to replace the
        function-timing prefixes; omit it to keep the current set.
        ``output`` selects where lines go: ``stdout`` (the default),
        ``stdout+logging``, or ``logging``.
        """
        checked_output = _check_output(output)
        self.func_enabled = func
        self.loops_enabled = loops
        self.files_enabled = files
        self.http_enabled = http
        self.sqlite_enabled = sqlite
        self.subproc_enabled = subprocess
        self.imports_enabled = imports
        if modules is not None:
            self.allowed_modules = set(modules)
        self.output = checked_output
        self.apply()

    def disable(self) -> None:
        """Turn every flag off so later :meth:`apply` calls install nothing."""
        self.func_enabled = False
        self.loops_enabled = False
        self.files_enabled = False
        self.http_enabled = False
        self.sqlite_enabled = False
        self.subproc_enabled = False
        self.imports_enabled = False
        logger.debug("Disabled all future timing installs")
