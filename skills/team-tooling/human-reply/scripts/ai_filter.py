"""Score long messages for AI scaffolding and drop the ones at or over the threshold.

    python ai_filter.py --corpus <channel>.jsonl --module channels/<channel>.md
        --reference references/ai-filter.md --cutoff 2026-01|never
        [--threshold 3] [--borrow] --kept <channel>.kept.jsonl

Prints a JSON summary: total, scanned, dropped, drop_rate (dropped over
scanned), total_drop_rate (dropped over total), threshold, and up to five
dropped samples with the patterns each one hit.
"""
import argparse
import json
import re
import sys

from corpus import cutoff_arg, fenced_block, is_pre_cutoff, read_jsonl, record_id, word_count, write_jsonl

DEFAULT_THRESHOLD = 3
LONG_MESSAGE_WORDS = 60
MAX_RAISE = 1
SAMPLES = 5

BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+\S")
EMOJI_START = re.compile(r"^\s*(?::[a-z0-9_+\-]+:|[\u2600-\u27bf\U0001F300-\U0001FAFF])\s*\S")
TLDR_START = re.compile(r"^\W*tl;?dr\b", re.I)
KEY_LIST = re.compile(r"\bkey (?:highlights|takeaways)\b", re.I)
HEADER = re.compile(r"^\s{0,3}#{1,6}\s+\S")
BOLD_LABEL = re.compile(r"\*\*[^*\n]{1,40}:\*\*|\*\*[^*\n]{1,40}\*\*\s*:|^\s*\*[^*\n]{1,40}:\*|^\s*\*[^*\n]{1,40}\*\s*:", re.M)
CLOSING = re.compile(r"^\W*(?:in short|in summary|to summari[sz]e|overall|all in all|net[- ]net|bottom line)\b", re.I)
NOT_BUT = re.compile(
    r"\bnot (?:just |only |merely )?[^.!?\n]{1,60}?,? but\b"
    r"|\bisn'?t (?:just |only |merely )?[^.!?\n]{1,40}?[;,] it'?s\b",
    re.I,
)


def _lines(text):
    return [line for line in text.splitlines() if line.strip()]


def emoji_section_marker(text, ctx):
    lines = _lines(text)
    return len(lines) >= 2 and any(EMOJI_START.match(line) for line in lines)


def tldr_block(text, ctx):
    lines = _lines(text)
    return len(lines) >= 2 and bool(TLDR_START.match(lines[0]))


def labelled_list(text, ctx):
    if KEY_LIST.search(text):
        return True
    lines = _lines(text)
    return any(a.rstrip().endswith(":") and BULLET.match(b) for a, b in zip(lines, lines[1:]))


def headers_bold_labels(text, ctx):
    return any(HEADER.match(line) for line in _lines(text)) or bool(BOLD_LABEL.search(text))


def em_dash(text, ctx):
    return "\u2014" in text


def parallel_triple(text, ctx):
    if ctx["short_messages_use_bullets"]:
        return False
    run = 0
    for line in _lines(text):
        run = run + 1 if BULLET.match(line) else 0
        if run >= 3:
            return True
    return False


def closing_restatement(text, ctx):
    lines = _lines(text)
    return bool(lines) and bool(CLOSING.match(lines[-1]))


def vocabulary(text, ctx):
    found = {word for word in ctx["vocabulary"]
             if re.search(rf"\b{re.escape(word)}\w*", text, re.I)}
    return len(found) >= 2


def not_x_but_y(text, ctx):
    return bool(NOT_BUT.search(text))


DETECTORS = {
    "emoji-section-marker": emoji_section_marker,
    "tldr-block": tldr_block,
    "labelled-list": labelled_list,
    "headers-bold-labels": headers_bold_labels,
    "em-dash": em_dash,
    "parallel-triple": parallel_triple,
    "closing-restatement": closing_restatement,
    "vocabulary": vocabulary,
    "not-x-but-y": not_x_but_y,
}


def load_patterns(module_path):
    """{pattern_id: set of exempt surfaces} from the module's ```ai-filter block."""
    with open(module_path, encoding="utf-8") as f:
        lines = fenced_block(f.read(), "ai-filter")
    patterns = {}
    for line in lines:
        pattern_id, _, rest = line.partition("|")
        pattern_id = pattern_id.strip()
        if pattern_id not in DETECTORS:
            raise ValueError(f"unknown ai-filter pattern {pattern_id!r} in {module_path}")
        exempt = set()
        rest = rest.strip()
        if rest:
            if not rest.startswith("exempt:"):
                raise ValueError(f"expected 'exempt:' after {pattern_id!r} in {module_path}")
            exempt = {s.strip() for s in rest[len("exempt:"):].split(",") if s.strip()}
        patterns[pattern_id] = exempt
    return patterns


def load_vocabulary(reference_path):
    with open(reference_path, encoding="utf-8") as f:
        return fenced_block(f.read(), "vocabulary")


def short_messages_use_bullets(records):
    return any(BULLET.match(line)
               for r in records if word_count(r["text"]) <= LONG_MESSAGE_WORDS
               for line in r["text"].splitlines())


def score(text, surface, patterns, ctx):
    """Sorted pattern ids the text hits on this surface."""
    return sorted(pid for pid, exempt in patterns.items()
                  if surface not in exempt and DETECTORS[pid](text, ctx))


def in_scope(record, cutoff, borrow):
    return (not record["held_out"]
            and word_count(record["text"]) > LONG_MESSAGE_WORDS
            and (borrow or (cutoff is not None and not is_pre_cutoff(record, cutoff))))


def run_filter(records, patterns, ctx, cutoff, threshold, borrow=False):
    """Split records into (kept, dropped); dropped items are (record, hits)."""
    kept, dropped = [], []
    for record in records:
        hits = score(record["text"], record["surface"], patterns, ctx) if in_scope(record, cutoff, borrow) else []
        if len(hits) >= threshold:
            dropped.append((record, hits))
        else:
            kept.append(record)
    return kept, dropped


def check_threshold(threshold):
    if threshold < 1 or threshold > DEFAULT_THRESHOLD + MAX_RAISE:
        raise ValueError(f"threshold must be 1 to {DEFAULT_THRESHOLD + MAX_RAISE}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--cutoff", required=True, type=cutoff_arg, help="YYYY-MM, or never")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--borrow", action="store_true", help="colleague sample: scan every long message")
    parser.add_argument("--kept", required=True)
    args = parser.parse_args(argv)
    try:
        check_threshold(args.threshold)
    except ValueError as error:
        print(f"ai_filter: {error}", file=sys.stderr)
        return 2

    records = read_jsonl(args.corpus)
    cutoff = None if args.cutoff == "never" else args.cutoff
    ctx = {"vocabulary": load_vocabulary(args.reference),
           "short_messages_use_bullets": short_messages_use_bullets(records)}
    patterns = load_patterns(args.module)
    kept, dropped = run_filter(records, patterns, ctx, cutoff, args.threshold, args.borrow)
    write_jsonl(args.kept, kept)
    scanned = sum(1 for r in records if in_scope(r, cutoff, args.borrow))
    summary = {
        "total": len(records),
        "scanned": scanned,
        "dropped": len(dropped),
        "drop_rate": round(len(dropped) / scanned, 3) if scanned else 0.0,
        "total_drop_rate": round(len(dropped) / len(records), 3) if records else 0.0,
        "threshold": args.threshold,
        "samples": [{"id": record_id(r), "hits": hits, "text": r["text"]} for r, hits in dropped[:SAMPLES]],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
