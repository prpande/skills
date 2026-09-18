"""Measure a filtered channel corpus and write <channel>.stats.json.

    python measure.py --corpus <channel>.kept.jsonl --module channels/<channel>.md
        --cutoff 2026-01|never --out <channel>.stats.json

Held-out records are never measured.
"""
import argparse
import json
import math
import re
import sys

from corpus import cutoff_arg, is_pre_cutoff, load_surfaces, read_jsonl, record_id, word_count

LONG_MESSAGE_WORDS = 60
VERY_LONG_WORDS = 150
BUDGET_FLOOR_RECORDS = 30

LINE_PATTERNS = {
    "cc line": re.compile(r"^\s*cc:", re.I | re.M),
    "bullets": re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+\S", re.M),
    "quote-reply": re.compile(r"^\s*>", re.M),
}
TEXT_PATTERNS = {
    "opener": re.compile(r"^\s*(?:hi|hey|hello)\b", re.I),
    "sign-off": re.compile(r"(?:thanks|thank you|cheers)[!.]*\s*(?::[a-z0-9_+\-]+:)?\s*$|:[a-z0-9_+\-]*smil[a-z_]*:\s*$", re.I),
    "hedge": re.compile(r"\b(?:i think|imo|afaik|maybe|not sure|from the top of my head)\b", re.I),
    "question": re.compile(r"\?"),
    "link": re.compile(r"https?://"),
    "code span": re.compile(r"(?<!`)`[^`\n]+`(?!`)"),
    "fenced block": re.compile(r"```"),
    "bold": re.compile(r"\*\*[^*\n]+\*\*|(?<![\w*])\*[^*\n]+\*(?![\w*])"),
    "emoji": re.compile(r":[a-z0-9_+\-]+:|[\u2600-\u27bf\U0001F300-\U0001FAFF]"),
}


def percentile(values, p):
    """Nearest-rank percentile of a non-empty list."""
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def round_up_to_ten(n):
    return int(math.ceil(n / 10) * 10)


def surface_stats(records, surfaces, cutoff):
    stats = {}
    for name, limits in surfaces.items():
        counts = [word_count(r["text"]) for r in records if r["surface"] == name]
        pre = [word_count(r["text"]) for r in records
               if r["surface"] == name and is_pre_cutoff(r, cutoff)]
        row = {"records": len(counts), "pre_cutoff_records": len(pre),
               "median": None, "p75": None, "p90": None}
        if counts:
            row.update(median=percentile(counts, 50), p75=percentile(counts, 75), p90=percentile(counts, 90))
        if len(pre) >= BUDGET_FLOOR_RECORDS:
            row["budget"] = max(round_up_to_ten(percentile(pre, 90)), limits["minimum"])
            row["label"] = "measured"
        else:
            row["budget"] = limits["default"]
            row["label"] = "estimated"
        row["over_budget"] = round(sum(c > row["budget"] for c in counts) / len(counts), 2) if counts else None
        stats[name] = row
    return stats


def pattern_rates(records):
    long = [r["text"] for r in records if word_count(r["text"]) > LONG_MESSAGE_WORDS]
    rates = {"long_messages": len(long)}
    for name, pattern in {**TEXT_PATTERNS, **LINE_PATTERNS}.items():
        rates[name] = round(sum(bool(pattern.search(t)) for t in long) / len(long), 2) if long else None
    return rates


def quarter_of(ts):
    return f"{ts[:4]}Q{(int(ts[5:7]) - 1) // 3 + 1}"


def quarters(records):
    grouped = {}
    for record in records:
        grouped.setdefault(quarter_of(record["ts"]), []).append(word_count(record["text"]))
    return {q: {"messages": len(c), "p90": percentile(c, 90),
                "over_150": round(sum(n > VERY_LONG_WORDS for n in c) / len(c), 3)}
            for q, c in sorted(grouped.items())}


def measure(records, surfaces, cutoff, channel):
    usable = [r for r in records if not r["held_out"]]
    return {
        "channel": channel,
        "method": "measured",
        "cutoff": cutoff or "never",
        "surfaces": surface_stats(usable, surfaces, cutoff),
        "pattern_rates": pattern_rates(usable),
        "quarters": quarters(usable),
        "long_message_ids": [record_id(r) for r in usable if word_count(r["text"]) > LONG_MESSAGE_WORDS],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--cutoff", required=True, type=cutoff_arg, help="YYYY-MM, or never")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    records = read_jsonl(args.corpus)
    cutoff = None if args.cutoff == "never" else args.cutoff
    channel = records[0]["channel"] if records else None
    stats = measure(records, load_surfaces(args.module), cutoff, channel)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"measure: {len(records)} records, {len(stats['long_message_ids'])} over {LONG_MESSAGE_WORDS} words")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
