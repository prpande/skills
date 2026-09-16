"""Place a JSON file the session composed into its state directory, atomically."""
import json
import pathlib
import sys

from poll import write_json_atomic

USAGE = "usage: state_put.py <source.json> <destination.json>\n"


def main(argv):
    if len(argv) != 2:
        sys.stderr.write(USAGE)
        return 2
    source, destination = (pathlib.Path(arg) for arg in argv)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        sys.stderr.write(f"unreadable source {source}: {err}\n")
        return 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(destination, data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
