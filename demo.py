"""Walkthrough of the lupaxa.invisible_timing_toolkit public API."""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

from lupaxa.invisible_timing_toolkit import enable


def main() -> None:
    """Enable the local hooks and exercise each one once.

    Lines go to stdout. Pass ``output="stdout+logging"`` to print and
    log, or ``output="logging"`` to log only.
    """
    enable(
        func=True,
        loops=True,
        files=True,
        http=True,
        sqlite=True,
        subprocess=True,
        imports=False,
        modules={"__main__"},
    )

    print("\n--- functions ---")

    def slow() -> None:
        return None

    slow()

    print("\n--- loops ---")
    for _ in range(2):
        pass

    print("\n--- files ---")
    path = Path("demo_temp.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("hello\n")
    path.unlink(missing_ok=True)

    print("\n--- sqlite ---")
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE demo (name TEXT)")
    connection.execute("INSERT INTO demo (name) VALUES (?)", ("alice",))
    rows = connection.execute("SELECT name FROM demo").fetchall()
    connection.close()
    print("sqlite rows:", rows)

    print("\n--- subprocess ---")
    if Path("/bin/echo").is_file():
        result = subprocess.run(
            ["/bin/echo", "hello"],
            check=False,
            capture_output=True,
            text=True,
        )
        print("subprocess output:", result.stdout.strip())
    else:
        print("/bin/echo is not available; subprocess timing skipped")

    print("\n--- http ---")
    try:
        import requests
    except ImportError:
        print("requests is not installed; HTTP timing skipped")
    else:
        try:
            response = requests.get("https://example.com", timeout=2)
        except requests.RequestException as exc:
            print(f"HTTP request failed: {exc!r}")
        else:
            print(f"HTTP status: {response.status_code}")

    print("\ndemo done.")


if __name__ == "__main__":
    main()
