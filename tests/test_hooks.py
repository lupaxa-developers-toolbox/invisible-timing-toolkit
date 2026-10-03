"""Timing hook installation and output lines."""

from __future__ import annotations

import logging
import sqlite3
import subprocess
from pathlib import Path

import pytest

from lupaxa.invisible_timing_toolkit import (
    LOGGER_NAME,
    HookInstallError,
    InvisibleTimingManager,
    apply,
    disable,
    enable,
)
from lupaxa.invisible_timing_toolkit import manager as manager_mod


def _stdout(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out


def _logged(caplog: pytest.LogCaptureFixture) -> str:
    return " ".join(record.message for record in caplog.records)


def test_env_enables_file_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVISIBLE_TIMING_FILES", "yes")
    manager = InvisibleTimingManager()
    assert manager.files_enabled is True
    assert manager._file_installed is True


def test_default_modules_are_main() -> None:
    manager = InvisibleTimingManager()
    assert manager.allowed_modules == {"__main__"}


def test_module_prefixes_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVISIBLE_TIMING_MODULES", "app, cli")
    manager = InvisibleTimingManager()
    assert manager.allowed_modules == {"app", "cli"}


def test_default_output_is_stdout() -> None:
    manager = InvisibleTimingManager()
    assert manager.output == "stdout"


def test_env_selects_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVISIBLE_TIMING_OUTPUT", "stdout+logging")
    manager = InvisibleTimingManager()
    assert manager.output == "stdout+logging"


def test_file_timing_prints_open(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    manager = InvisibleTimingManager()
    target = tmp_path / "note.txt"
    manager.enable(files=True)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("hello\n")
    text = _stdout(capsys)
    assert "[FILE]" in text
    assert "note.txt" in text


def test_logging_output_skips_stdout(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    manager = InvisibleTimingManager()
    target = tmp_path / "note.txt"
    manager.enable(files=True, output="logging")
    with (
        caplog.at_level(logging.INFO, logger=LOGGER_NAME),
        open(target, "w", encoding="utf-8") as handle,
    ):
        handle.write("hello\n")
    assert "[FILE]" in _logged(caplog)
    assert _stdout(capsys) == ""


def test_stdout_and_logging_writes_both(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    manager = InvisibleTimingManager()
    target = tmp_path / "note.txt"
    manager.enable(files=True, output="stdout+logging")
    with (
        caplog.at_level(logging.INFO, logger=LOGGER_NAME),
        open(target, "w", encoding="utf-8") as handle,
    ):
        handle.write("hello\n")
    assert "[FILE]" in _logged(caplog)
    assert "[FILE]" in _stdout(capsys)


def test_unknown_output_is_rejected() -> None:
    manager = InvisibleTimingManager()
    with pytest.raises(ValueError, match=r"output must be stdout, stdout\+logging, or logging"):
        manager.enable(output="printer")


def test_function_timing_respects_module_filter(capsys: pytest.CaptureFixture[str]) -> None:
    manager = InvisibleTimingManager()

    def slow() -> int:
        return 1

    manager.enable(func=True, modules={"not_a_real_package"})
    assert slow() == 1
    assert "[FUNC]" not in _stdout(capsys)


def test_function_timing_prints_allowed_module(capsys: pytest.CaptureFixture[str]) -> None:
    manager = InvisibleTimingManager()

    def slow() -> int:
        return 1

    manager.enable(func=True, modules={__name__})
    slow()
    assert any("[FUNC]" in line and "slow" in line for line in _stdout(capsys).splitlines())


def test_loop_timing_yields_original_values(capsys: pytest.CaptureFixture[str]) -> None:
    manager = InvisibleTimingManager()
    manager.enable(loops=True)
    assert list(range(2)) == [0, 1]
    assert "[LOOP]" in _stdout(capsys)


def test_subprocess_timing_prints_return_code(capsys: pytest.CaptureFixture[str]) -> None:
    manager = InvisibleTimingManager()
    manager.enable(subprocess=True)
    subprocess.run(["echo", "hello"], check=False, capture_output=True, text=True)
    text = _stdout(capsys)
    assert "[PROC]" in text
    assert "returncode=0" in text


def test_import_timing_prints_import(capsys: pytest.CaptureFixture[str]) -> None:
    manager = InvisibleTimingManager()
    manager.enable(imports=True)
    __import__("json")
    text = _stdout(capsys)
    assert "[IMPORT]" in text
    assert "json" in text


def test_sqlite_timing_prints_or_skips(capsys: pytest.CaptureFixture[str]) -> None:
    manager = InvisibleTimingManager()
    manager.enable(sqlite=True)
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE demo (id INTEGER)")
    connection.close()
    text = _stdout(capsys).lower()
    assert "[sql]" in text or "sqlite" in text


def test_http_timing_prints_status(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = pytest.importorskip("requests")

    class _Response:
        status_code = 204

    def fake_request(
        self: object,
        method: str,
        url: str,
        *args: object,
        **kwargs: object,
    ) -> _Response:
        del self, method, url, args, kwargs
        return _Response()

    monkeypatch.setattr(requests.sessions.Session, "request", fake_request)
    manager = InvisibleTimingManager()
    manager.enable(http=True)
    requests.Session().request("GET", "https://example.test")
    text = _stdout(capsys)
    assert "[HTTP]" in text
    assert "status=204" in text


def test_missing_requests_skips_http(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager_mod, "requests", None)
    manager = InvisibleTimingManager()
    manager.enable(http=True)
    assert "requests is not available" in _stdout(capsys)
    assert manager._http_installed is False


def test_disable_leaves_installed_file_hook_in_place(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    manager = InvisibleTimingManager()
    target = tmp_path / "note.txt"
    manager.enable(files=True)
    manager.disable()
    assert manager.files_enabled is False
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("still patched\n")
    assert "[FILE]" in _stdout(capsys)


def test_apply_wraps_unexpected_installer_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = InvisibleTimingManager()

    def boom() -> None:
        raise RuntimeError("nope")

    monkeypatch.setattr(manager, "_install_function_timing", boom)
    manager.func_enabled = True
    with pytest.raises(HookInstallError, match="failed to install timing hook"):
        manager.apply()


def test_module_enable_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_enable(**kwargs: object) -> None:
        seen.update(kwargs)

    from lupaxa import invisible_timing_toolkit as api

    monkeypatch.setattr(api._manager, "enable", fake_enable)
    enable(func=True, modules={"app"})
    assert seen["func"] is True
    assert seen["modules"] == {"app"}
    assert seen["output"] == "stdout"


def test_module_disable_and_apply_delegate(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    from lupaxa import invisible_timing_toolkit as api

    monkeypatch.setattr(api._manager, "disable", lambda: calls.append("disable"))
    monkeypatch.setattr(api._manager, "apply", lambda: calls.append("apply"))
    disable()
    apply()
    assert calls == ["disable", "apply"]
