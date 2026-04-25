import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

def atomic_write_json(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(json.dumps(obj, indent=2, sort_keys=True).encode("utf-8"))
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError as e:
            logging.getLogger(__name__).warning("fsync skipped for %s: %s", path, e)
    try:
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise

def read_json(path: Path) -> Optional[Any]:
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def new_run_dir(base: Path, date: str, slug: str) -> Path:
    d = Path(base) / f"{date}-{slug}"
    d.mkdir(parents=True, exist_ok=True)
    return d

_RETRY_FILE = "retry_tracker.json"

def record_retry(run_dir: Path, stage: str) -> None:
    path = Path(run_dir) / _RETRY_FILE
    data = read_json(path) or {}
    data[stage] = int(data.get(stage, 0)) + 1
    atomic_write_json(path, data)

def get_retry_count(run_dir: Path, stage: str) -> int:
    data = read_json(Path(run_dir) / _RETRY_FILE) or {}
    return int(data.get(stage, 0))

def validate_and_write_json(path: Path, obj: Any, schema_name: str,
                            schemas_dir: Path) -> None:
    """Validate `obj` against `schemas_dir/<schema_name>` then write atomically.

    On validation failure: raise ValidationError with the JSON-pointer-style
    path of the failing field. The file is NOT written on failure; no tmp
    file is left behind.
    """
    import json as _json
    from validator import Validator, ValidationError

    schema_path = Path(schemas_dir) / schema_name
    if not schema_path.exists():
        raise FileNotFoundError(
            f"validate_and_write_json: schema not found at {schema_path}"
        )
    schema = _json.loads(schema_path.read_text(encoding="utf-8"))
    Validator(Path(schemas_dir)).validate(obj, schema)
    atomic_write_json(path, obj)
