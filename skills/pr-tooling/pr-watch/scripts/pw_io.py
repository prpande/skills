"""JSON file helpers shared by the pr-watch scripts."""
from __future__ import annotations

import json
import os
import time


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is None:
            raise
        return default


def write_json_atomic(path, data, attempts=5, sleep=time.sleep):
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, indent=2) + "\n")
    for attempt in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            # Windows refuses a replace while any reader or scanner holds the target open.
            if attempt == attempts - 1:
                tmp.unlink(missing_ok=True)
                raise
            sleep(0.1)
