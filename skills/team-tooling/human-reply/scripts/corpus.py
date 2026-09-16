"""Corpus records for human-reply setup: read, validate, count words, pick hold-outs.

    python corpus.py validate --corpus <channel>.jsonl --module channels/<channel>.md
    python corpus.py holdout --corpus <channel>.jsonl --cutoff 2026-01|never --seed N [--passed kept.jsonl] [--reset]
    python corpus.py normalize --corpus <channel>.jsonl --cap 1500
    python corpus.py oldest --corpus <channel>.jsonl
"""
import argparse
import json
import random
import re
import sys

FIELDS = {
    "channel": str,
    "surface": str,
    "ts": str,
    "audience": str,
    "thread": str,
    "others": int,
    "text": str,
    "held_out": bool,
}
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FENCED_CODE = re.compile(r"```[\s\S]*?```")
SLACK_LINK = re.compile(r"<https?://[^>\n]+>")
MARKDOWN_LINK = re.compile(r"\[[^\]\n]*\]\([^)\s]+\)")
CUTOFF = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
HOLDOUTS_PER_CHANNEL = 3
# Calibration drafts a reply to someone else's message, and a PR body answers nobody.
NO_REPLY_TARGET_SURFACE = "PR body"


def read_jsonl(path):
    with open(path, encoding="utf-8-sig") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def fenced_block(markdown, tag):
    """Lines inside the first ```<tag> fence, without blanks or # comments."""
    match = re.search(rf"^```{re.escape(tag)}[ \t]*\n(.*?)^```", markdown, re.S | re.M)
    if not match:
        raise ValueError(f"no ```{tag} block")
    lines = [line.strip() for line in match.group(1).splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def load_surfaces(module_path):
    """{surface: {"minimum": int, "default": int}} in module order."""
    with open(module_path, encoding="utf-8") as f:
        lines = fenced_block(f.read(), "surfaces")
    surfaces = {}
    for line in lines:
        name, minimum, default = [part.strip() for part in line.split("|")]
        surfaces[name] = {"minimum": int(minimum), "default": int(default)}
    return surfaces


def word_count(text):
    """Whitespace tokens, with each fenced block and each link counted as one."""
    text = FENCED_CODE.sub(" CODE ", text)
    text = SLACK_LINK.sub(" LINK ", text)
    text = MARKDOWN_LINK.sub(" LINK ", text)
    return len(text.split())


def record_id(record):
    return f"{record['audience']}/{record['ts']}"


def is_pre_cutoff(record, cutoff):
    """cutoff is "YYYY-MM" or None; a message sent in the cutoff month is after it."""
    return cutoff is None or record["ts"][:7] < cutoff


def cutoff_arg(value):
    """argparse type for --cutoff: returns "YYYY-MM" or "never" unchanged."""
    if value == "never" or CUTOFF.match(value):
        return value
    raise argparse.ArgumentTypeError(f"{value!r} is not YYYY-MM or never")


def validate_record(record, surfaces):
    errors = []
    for field, kind in FIELDS.items():
        if field not in record:
            errors.append(f"missing field {field}")
        elif type(record[field]) is not kind:
            errors.append(f"field {field} is not {kind.__name__}")
    extra = set(record) - set(FIELDS)
    if extra:
        errors.append(f"unknown fields {sorted(extra)}")
    if isinstance(record.get("surface"), str) and record["surface"] not in surfaces:
        errors.append(f"surface {record['surface']!r} is not in the channel module")
    if isinstance(record.get("ts"), str) and not TS.match(record["ts"]):
        errors.append(f"ts {record['ts']!r} is not YYYY-MM-DDTHH:MM:SSZ")
    if isinstance(record.get("others"), int) and record["others"] < 0:
        errors.append("others is negative")
    return errors


def normalize(records, cap):
    """Drop repeated ids, keep the newest `cap` records, newest first."""
    unique = {}
    for record in records:
        unique.setdefault(record_id(record), record)
    return sorted(unique.values(), key=lambda r: r["ts"], reverse=True)[:cap]


def oldest_ts(records):
    return min((r["ts"] for r in records), default=None)


def _threads(records):
    threads = {}
    for record in records:
        threads.setdefault(record["thread"], []).append(record)
    return threads


def select_holdouts(records, cutoff, seed, passed_ids=None):
    """Mark up to three threads held out and return [(thread, pool)] for every held-out thread.

    Threads already held out are kept. The pre-cutoff pool (the whole window
    when cutoff is None) is drawn first. Only when a cutoff exists and
    passed_ids is given does the post-cutoff pool fill the remainder, and
    only with threads whose every record passed the filter.
    """
    rng = random.Random(seed)
    threads = _threads(records)
    chosen = [(t, "earlier") for t, rs in threads.items() if any(r["held_out"] for r in rs)]
    eligible = {t: rs for t, rs in threads.items()
                if max(r["others"] for r in rs) >= 1
                and all(r["surface"] != NO_REPLY_TARGET_SURFACE for r in rs)
                and t not in dict(chosen)}
    pre = sorted(t for t, rs in eligible.items() if all(is_pre_cutoff(r, cutoff) for r in rs))
    pools = [("pre-cutoff", pre)]
    if cutoff is not None and passed_ids is not None:
        post = sorted(t for t, rs in eligible.items()
                      if not any(is_pre_cutoff(r, cutoff) for r in rs)
                      and all(record_id(r) in passed_ids for r in rs))
        pools.append(("post-cutoff", post))
    for name, pool in pools:
        need = HOLDOUTS_PER_CHANNEL - len(chosen)
        if need <= 0:
            break
        for thread in rng.sample(pool, min(need, len(pool))):
            chosen.append((thread, name))
    held = dict(chosen)
    for record in records:
        if record["thread"] in held:
            record["held_out"] = True
    return chosen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--corpus", required=True)
    v.add_argument("--module", required=True)
    h = sub.add_parser("holdout")
    h.add_argument("--corpus", required=True)
    h.add_argument("--cutoff", required=True, type=cutoff_arg, help="YYYY-MM, or never")
    h.add_argument("--seed", required=True, type=int)
    h.add_argument("--passed", help="JSONL of records that passed the filter")
    h.add_argument("--reset", action="store_true", help="clear every hold-out mark before choosing")
    n = sub.add_parser("normalize")
    n.add_argument("--corpus", required=True)
    n.add_argument("--cap", required=True, type=int)
    o = sub.add_parser("oldest")
    o.add_argument("--corpus", required=True)
    args = parser.parse_args(argv)

    records = read_jsonl(args.corpus)
    if args.command == "normalize":
        kept = normalize(records, args.cap)
        write_jsonl(args.corpus, kept)
        print(f"corpus: {len(records)} records in, {len(kept)} kept")
        return 0
    if args.command == "oldest":
        print(oldest_ts(records) or "none")
        return 0
    if args.command == "validate":
        surfaces = load_surfaces(args.module)
        bad = 0
        for index, record in enumerate(records, 1):
            for error in validate_record(record, surfaces):
                bad += 1
                print(f"{args.corpus}:{index}: {error}")
        print(f"corpus: {len(records)} records, {bad} errors")
        return 1 if bad else 0

    cutoff = None if args.cutoff == "never" else args.cutoff
    passed = {record_id(r) for r in read_jsonl(args.passed)} if args.passed else None
    if args.reset:
        for record in records:
            record["held_out"] = False
    chosen = select_holdouts(records, cutoff, args.seed, passed)
    write_jsonl(args.corpus, records)
    print(json.dumps([{"thread": t, "pool": p} for t, p in chosen]))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
