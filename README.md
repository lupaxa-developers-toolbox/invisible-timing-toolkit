<p align="center">
  <a href="https://github.com/lupaxa-developers-toolbox">
    <img src="https://raw.githubusercontent.com/the-lupaxa-project/brand-assets/master/logos/organisations/developers-toolbox/readme-logo.png" alt="Developers Toolbox" />
  </a>
</p>

<h1 align="center">Invisible Timing Toolkit</h1>

Opt-in timing for Python programs. Import the library, enable the hooks
you want, and selected runtime calls print how long they took. Application
code stays free of decorators and manual timers.

The PyPI name is `lupaxa-invisible-timing-toolkit`. The import path is
`lupaxa.invisible_timing_toolkit`. `lupaxa` is a namespace package — there
is no `lupaxa/__init__.py`.

## Install

```bash
pip install lupaxa-invisible-timing-toolkit
```

Requires Python 3.10+. There are no required runtime dependencies.
HTTP timing needs `requests`:

```bash
pip install "lupaxa-invisible-timing-toolkit[http]"
```

From a clone of this repository (editable install):

```bash
make init
make python-install-dev
```

This is a library only. There is no console script and no
`python -m` entry point.

A walkthrough of the same API lives in `demo.py` at the repository
root (not shipped in the wheel):

```bash
python demo.py
```

## Usage

Timing lines go to stdout. A hook that cannot be installed prints a
notice and the process keeps running. Each run prints its own
duration; the samples show the line shape.

`enable()` replaces the current flags. A flag you leave at its default
is turned off. `modules` limits function timing to those module-name
prefixes (`myapp` also matches `myapp.utils`). Omit `modules` to keep
the current set. The environment default is `__main__`.

```python
from lupaxa.invisible_timing_toolkit import enable

enable(
    func=True,
    files=True,
    http=True,
    modules={"__main__", "myapp"},
)
```

> **Note:** Function timing (`sys.setprofile`) and the `range`
> replacement apply to the whole process. Leave them off unless you
> are profiling.

### Choose the Output

`output` has three settings. The default is `stdout`.

```python
enable(files=True)  # stdout
enable(files=True, output="stdout+logging")
enable(files=True, output="logging")
```

`stdout` prints each line. `stdout+logging` prints the line and also
sends it to the `invisible_timing` logger. `logging` sends the line to
that logger and does not print it. `INFO` is a timing line and
`WARNING` is a skipped hook:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
)

enable(files=True, output="logging")

with open("notes.txt", "w", encoding="utf-8") as handle:
    handle.write("hello\n")
```

```text
INFO invisible_timing [FILE] open('notes.txt') took 0.000128s
```

`stdout+logging` prints that same `[FILE]` line and writes the logger
record above.

### Function Calls

```python
from lupaxa.invisible_timing_toolkit import enable

enable(func=True, modules={"__main__"})

def slow() -> None:
    return None

slow()
```

```text
[FUNC] __main__.slow took 0.000012s
```

### Loop Iterations

`range` is replaced with a generator. Each line is the time spent
in the loop body for that step.

```python
from lupaxa.invisible_timing_toolkit import enable

enable(loops=True)

for _ in range(2):
    pass
```

```text
[LOOP] range iteration 0 took 0.000001s
[LOOP] range iteration 1 took 0.000001s
```

### File Opens

Pass the path as a string if you want that string in the line.
`Path.write_text` does not go through `builtins.open`.

```python
from lupaxa.invisible_timing_toolkit import enable

enable(files=True)

with open("notes.txt", "w", encoding="utf-8") as handle:
    handle.write("hello\n")
```

```text
[FILE] open('notes.txt') took 0.000128s
```

### HTTP Requests

Requires `requests`. `requests.get` and the other helpers call
`Session.request`, which is the wrapped method.

```python
import requests

from lupaxa.invisible_timing_toolkit import enable

enable(http=True)
requests.get("https://example.com", timeout=5)
```

```text
[HTTP] GET https://example.com took 0.112321s (status=200)
```

When `requests` is not installed the hook skips itself:

```text
requests is not available; HTTP timing skipped
```

### SQLite Queries

```python
import sqlite3

from lupaxa.invisible_timing_toolkit import enable

enable(sqlite=True)
connection = sqlite3.connect(":memory:")
connection.execute("CREATE TABLE demo (name TEXT)")
connection.execute("SELECT name FROM demo")
connection.close()
```

When `sqlite3.Cursor.execute` can be replaced, each statement is printed:

```text
[SQL] 'CREATE TABLE demo (name TEXT)' took 0.000120s
[SQL] 'SELECT name FROM demo' took 0.000040s
```

On current CPython the cursor type is immutable, so the hook prints a
notice and does not time the statements:

```text
sqlite3.Cursor appears immutable; sqlite timing disabled for this runtime
```

### Subprocess Calls

```python
import subprocess

from lupaxa.invisible_timing_toolkit import enable

enable(subprocess=True)
subprocess.run(["/bin/echo", "hello"], check=False, capture_output=True, text=True)
```

```text
[PROC] subprocess.run(['/bin/echo', 'hello'],) took 0.003166s (returncode=0)
```

The bracketed value is the positional arguments. A one-argument call
is a one-item tuple, so the printed line keeps the trailing comma.

### Module Imports

```python
from lupaxa.invisible_timing_toolkit import enable

enable(imports=True)
import json
```

```text
[IMPORT] import 'json' took 0.000004s
```

### Turn Hooks Off

`disable()` blocks later installs. Callables that are already patched
stay patched, so a file open after `disable()` can still print.

```python
from lupaxa.invisible_timing_toolkit import disable

disable()
```

`apply()` installs whatever is currently enabled. `enable()` calls it
for you.

### What it Times

| Hook         | Target                     | Flag              |
| ------------ | -------------------------- | ----------------- |
| Functions    | `sys.setprofile`           | `func=True`       |
| Loops        | `builtins.range`           | `loops=True`      |
| Files        | `builtins.open`            | `files=True`      |
| HTTP         | `requests.Session.request` | `http=True`       |
| SQLite       | `sqlite3.Cursor.execute`   | `sqlite=True`     |
| Subprocesses | `subprocess.run`           | `subprocess=True` |
| Imports      | `builtins.__import__`      | `imports=True`    |

## Environment Variables

Set these before the package is imported. The shared manager reads
them once, at import, and installs any hook whose variable is truthy.
`1`, `true`, and `yes` count. The default module list is `__main__`.

| Variable                     | Effect                                              |
| ---------------------------- | --------------------------------------------------- |
| `INVISIBLE_TIMING=1`         | Time function calls                                 |
| `INVISIBLE_TIMING_LOOPS=1`   | Time `range` iterations                             |
| `INVISIBLE_TIMING_FILES=1`   | Time `open` calls                                   |
| `INVISIBLE_TIMING_HTTP=1`    | Time `requests` calls                               |
| `INVISIBLE_TIMING_SQLITE=1`  | Time `sqlite3` executes                             |
| `INVISIBLE_TIMING_SUBPROC=1` | Time `subprocess.run`                               |
| `INVISIBLE_TIMING_IMPORTS=1` | Time imports                                        |
| `INVISIBLE_TIMING_MODULES`   | Comma-separated module prefixes for function timing |
| `INVISIBLE_TIMING_OUTPUT`    | `stdout`, `stdout+logging`, or `logging`            |

```bash
export INVISIBLE_TIMING=1
export INVISIBLE_TIMING_FILES=1
export INVISIBLE_TIMING_MODULES=__main__,myapp
python myapp.py
```

That is the same as calling
`enable(func=True, files=True, modules={"__main__", "myapp"})`
after import. Opening a file then prints a `[FILE]` line, and
functions defined in `myapp` or `__main__` print `[FUNC]` lines.
Set `INVISIBLE_TIMING_OUTPUT=stdout+logging` or
`INVISIBLE_TIMING_OUTPUT=logging` before import to change the
destination. `stdout` is the default. `enable()` resets `output` to
stdout unless you pass it again.

## Check

```bash
make init
make python-check
```

<a href="https://github.com/the-lupaxa-project">
    <img src="https://raw.githubusercontent.com/the-lupaxa-project/brand-assets/master/logos/components/footer-for-child-orgs.svg" alt="The Lupaxa Project Footer" width="100%" />
</a>
