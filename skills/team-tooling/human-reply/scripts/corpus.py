"""Corpus records for human-reply setup: read, validate, count words, pick hold-outs.

    python corpus.py validate --corpus <channel>.jsonl --module channels/<channel>.md
    python corpus.py holdout --corpus <channel>.jsonl --cutoff 2026-01|never --seed N [--passed kept.jsonl] [--reset]
    python corpus.py normalize --corpus <channel>.jsonl --cap 1500 [--cutoff 2026-01|never]
    python corpus.py oldest --corpus <channel>.jsonl [--from-month 2026-01]
    python corpus.py templated --corpus <channel>.jsonl [--min 10]
    python corpus.py drop --corpus <channel>.jsonl --audience <id> [--audience <id> ...]
    python corpus.py phrases --corpus <channel>.kept.jsonl --out <channel>.phrases.jsonl [--min 3] [--top 200] [--singles 50]
    python corpus.py count --corpus <channel>.kept.jsonl --phrase "<phrase>" [--phrase "<phrase>" ...]
    python corpus.py fingerprint --skill-dir <skill-dir>
"""
import argparse
import hashlib
import json
import pathlib
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
PHRASE_MAX_WORDS = 5
OPENER_MAX_WORDS = 3
MARKER = re.compile(r"(?<![\w:])(?::[a-z0-9_+'-]+:(?![\w:])|[A-Z]{2,5}(?!\w))")
# Slack escapes these three in message text; order matters so a typed "&lt;" survives as text.
SLACK_ENTITIES = (("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"))
PHRASE_BREAK = re.compile(r"<[^>\n]*>|https?://\S+")
PHRASE_STRIP = "\"'()[]{}.,;?!*_~`"
STOPWORDS = frozenset(
    "a an the and or but if so of to in on at by for from with as is are was were be been being it its "
    "this that these those i me my we our you your he she they them their his her there here what which "
    "who when where why how not no yes do does did done have has had will would can could should may "
    "might must just also then than too very all any some more most other into out up down over about "
    "again only own same such both each few am".split())
FINGERPRINT_PARTS = ("SKILL.md", "setup", "references", "channels", "scripts")
# Calibration drafts a reply to someone else's message, and a PR body answers nobody.
NO_REPLY_TARGET_SURFACE = "PR body"
# A thread's opening post answers nobody either, so it cannot be the reply calibration compares against.
THREAD_ROOT_SURFACES = frozenset({"PR body", "channel new post", "write-up"})


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


def _spread_by_month(records):
    """Newest first within each month, then round-robin across months, newest month first."""
    months = {}
    for record in sorted(records, key=lambda r: r["ts"], reverse=True):
        months.setdefault(record["ts"][:7], []).append(record)
    queues = [months[m] for m in sorted(months, reverse=True)]
    order = []
    for depth in range(max((len(q) for q in queues), default=0)):
        order.extend(q[depth] for q in queues if depth < len(q))
    return order


def decode_entities(text):
    for entity, char in SLACK_ENTITIES:
        text = text.replace(entity, char)
    return text


def normalize(records, cap, cutoff=None):
    """Decode &lt; &gt; &amp;, drop repeated ids and blank messages, and keep `cap` records, newest first.

    Trimming spreads the cap across months: each month keeps its newest
    records, one round at a time, so a busy month cannot crowd out the rest.
    With a cutoff, pre-cutoff records take the cap first and post-cutoff
    records fill what room is left.
    """
    unique = {}
    for record in records:
        if isinstance(record.get("text"), str):
            if not record["text"].strip():
                continue
            record["text"] = decode_entities(record["text"])
        unique.setdefault(record_id(record), record)
    if cutoff is None:
        order = _spread_by_month(unique.values())
    else:
        order = (_spread_by_month(r for r in unique.values() if is_pre_cutoff(r, cutoff))
                 + _spread_by_month(r for r in unique.values() if not is_pre_cutoff(r, cutoff)))
    return sorted(order[:cap], key=lambda r: r["ts"], reverse=True)


def oldest_ts(records, from_month=None):
    """Oldest ts, counting only records sent in or after from_month ("YYYY-MM") when given."""
    return min((r["ts"] for r in records if from_month is None or r["ts"][:7] >= from_month), default=None)


def templated(records, minimum=10):
    """Audiences with at least `minimum` records where half or more open with the same three tokens."""
    by_audience = {}
    for record in records:
        by_audience.setdefault(record["audience"], []).append(record)
    flagged = []
    for audience, rs in by_audience.items():
        if len(rs) < minimum:
            continue
        prefixes = {}
        for record in rs:
            tokens = record["text"].split()[:3]
            if len(tokens) == 3:
                prefix = " ".join(tokens)
                prefixes[prefix] = prefixes.get(prefix, 0) + 1
        if not prefixes:
            continue
        prefix, count = max(sorted(prefixes.items()), key=lambda item: item[1])
        if count * 2 >= len(rs):
            flagged.append({"audience": audience, "records": len(rs), "share": round(count / len(rs), 2),
                            "prefix": prefix})
    return sorted(flagged, key=lambda line: (-line["records"], line["audience"]))


def phrase_tokens(text):
    """Lowercased word runs; a code block, link, mention, or placeholder breaks a run."""
    runs = []
    for chunk in PHRASE_BREAK.split(FENCED_CODE.sub("<code>", text)):
        run = [token.strip(PHRASE_STRIP) for token in chunk.lower().split()]
        run = [token for token in run if token]
        if run:
            runs.append(run)
    return runs


def _ngrams(runs, max_words):
    grams = set()
    for run in runs:
        for size in range(1, max_words + 1):
            for start in range(len(run) - size + 1):
                grams.add(tuple(run[start:start + size]))
    return grams


def phrases(records, minimum=3, top=200, singles=50, max_words=PHRASE_MAX_WORDS):
    """Word sequences of 1 to max_words words by the number of records holding them.

    Held-out records are skipped. A sequence made only of stopwords and
    tokens without letters is left out, and so is one whose longer extension
    appears in as many records. Single words take at most `singles` of the
    `top` places, since most frequent single words are topic words.
    """
    counts = {}
    for record in records:
        if record.get("held_out"):
            continue
        for gram in _ngrams(phrase_tokens(record["text"]), max_words):
            counts[gram] = counts.get(gram, 0) + 1
    subsumed = set()
    for gram, count in counts.items():
        if len(gram) > 1:
            for part in (gram[:-1], gram[1:]):
                if counts.get(part) == count:
                    subsumed.add(part)
    kept = [(gram, count) for gram, count in counts.items()
            if count >= minimum and gram not in subsumed
            and not all(token in STOPWORDS or not any(ch.isalpha() for ch in token) for token in gram)]
    kept.sort(key=lambda item: (-item[1], -len(item[0]), item[0]))
    single_room = min(singles, top)
    single = [item for item in kept if len(item[0]) == 1][:single_room]
    multi = [item for item in kept if len(item[0]) > 1][:top - len(single)]
    return [{"phrase": " ".join(gram), "records": count} for gram, count in single + multi]


def _usable_lines(record):
    """Lines of a record's text, without fenced blocks and without lines quoting someone else."""
    text = FENCED_CODE.sub("\n", record["text"])
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(">")]


def line_openers(records, minimum=2, top=250, max_words=OPENER_MAX_WORDS):
    """The first 1 to max_words words of each line, by the number of records holding them.

    A line that starts with a link, mention, or placeholder has no opener.
    Stopwords are kept, since "Also," or "So" opening a line is a habit. An
    opener without letters, or one whose longer extension appears in as many
    records, is left out.
    """
    counts = {}
    for record in records:
        if record.get("held_out"):
            continue
        grams = set()
        for line in _usable_lines(record):
            if PHRASE_BREAK.match(line):
                continue
            runs = phrase_tokens(line)
            if runs:
                grams.update(tuple(runs[0][:size]) for size in range(1, min(max_words, len(runs[0])) + 1))
        for gram in grams:
            counts[gram] = counts.get(gram, 0) + 1
    subsumed = {gram[:-1] for gram, count in counts.items() if len(gram) > 1 and counts.get(gram[:-1]) == count}
    kept = [(gram, count) for gram, count in counts.items()
            if count >= minimum and gram not in subsumed
            and any(any(ch.isalpha() for ch in token) for token in gram)]
    kept.sort(key=lambda item: (-item[1], -len(item[0]), item[0]))
    return [{"phrase": " ".join(gram), "records": count} for gram, count in kept[:top]]


def markers(records, minimum=2):
    """Emoji shortcodes and all-caps words of 2 to 5 letters, as written, by the number of records holding them."""
    counts = {}
    for record in records:
        if record.get("held_out"):
            continue
        found = set()
        for line in _usable_lines(record):
            found.update(MARKER.findall(PHRASE_BREAK.sub(" ", line)))
        for marker in found:
            counts[marker] = counts.get(marker, 0) + 1
    kept = sorted(((m, c) for m, c in counts.items() if c >= minimum), key=lambda item: (-item[1], item[0]))
    return [{"phrase": marker, "records": count} for marker, count in kept]


def candidates(records, minimum=3, top=200, singles=50):
    """Phrase, line-opener, and marker candidates for the readers, each tagged with its kind."""
    return ([dict(p, kind="phrase") for p in phrases(records, minimum, top, singles)]
            + [dict(p, kind="line opener") for p in line_openers(records)]
            + [dict(p, kind="marker") for p in markers(records)])


def count_phrase(records, phrase):
    """Records, held-out ones skipped, whose words hold the phrase's words in order, tokenized as `phrases` does."""
    target = [token for run in phrase_tokens(phrase) for token in run]
    if not target:
        return 0
    size = len(target)
    total = 0
    for record in records:
        if record.get("held_out"):
            continue
        if any(run[i:i + size] == target for run in phrase_tokens(record["text"])
               for i in range(len(run) - size + 1)):
            total += 1
    return total


def fingerprint(skill_dir):
    """Short hash of the skill's instructions and scripts, line endings ignored."""
    root = pathlib.Path(skill_dir)
    files = []
    for part in FINGERPRINT_PARTS:
        target = root / part
        candidates = [target] if target.is_file() else sorted(target.rglob("*")) if target.is_dir() else []
        files.extend(f for f in candidates
                     if f.is_file() and "__pycache__" not in f.parts and f.suffix in (".md", ".py"))
    digest = hashlib.sha256()
    for f in files:
        digest.update(f.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(f.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()[:12]


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
                if any(r["others"] >= 1 and r["surface"] not in THREAD_ROOT_SURFACES for r in rs)
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
    n.add_argument("--cutoff", type=cutoff_arg, help="YYYY-MM, or never")
    o = sub.add_parser("oldest")
    o.add_argument("--corpus", required=True)
    o.add_argument("--from-month", type=cutoff_arg, help="YYYY-MM: ignore records sent before this month")
    t = sub.add_parser("templated")
    t.add_argument("--corpus", required=True)
    t.add_argument("--min", type=int, default=10)
    d = sub.add_parser("drop")
    d.add_argument("--corpus", required=True)
    d.add_argument("--audience", required=True, action="append")
    p = sub.add_parser("phrases")
    p.add_argument("--corpus", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--min", type=int, default=3)
    p.add_argument("--top", type=int, default=200)
    p.add_argument("--singles", type=int, default=50)
    c = sub.add_parser("count")
    c.add_argument("--corpus", required=True)
    c.add_argument("--phrase", required=True, action="append")
    f = sub.add_parser("fingerprint")
    f.add_argument("--skill-dir", required=True)
    args = parser.parse_args(argv)

    if args.command == "fingerprint":
        print(fingerprint(args.skill_dir))
        return 0
    records = read_jsonl(args.corpus)
    if args.command == "phrases":
        found = candidates(records, args.min, args.top, args.singles)
        write_jsonl(args.out, found)
        kinds = [sum(line["kind"] == kind for line in found) for kind in ("phrase", "line opener", "marker")]
        print("phrases: {} phrases, {} line openers, {} markers written".format(*kinds))
        return 0
    if args.command == "count":
        for phrase in args.phrase:
            print(json.dumps({"phrase": phrase, "records": count_phrase(records, phrase)}, ensure_ascii=False))
        return 0
    if args.command == "normalize":
        kept = normalize(records, args.cap, None if args.cutoff in (None, "never") else args.cutoff)
        write_jsonl(args.corpus, kept)
        print(f"corpus: {len(records)} records in, {len(kept)} kept")
        return 0
    if args.command == "oldest":
        month = None if args.from_month in (None, "never") else args.from_month
        print(oldest_ts(records, month) or "none")
        return 0
    if args.command == "templated":
        for line in templated(records, args.min):
            print(json.dumps(line, ensure_ascii=False))
        return 0
    if args.command == "drop":
        kept = [r for r in records if r["audience"] not in set(args.audience)]
        write_jsonl(args.corpus, kept)
        print(f"drop: {len(records) - len(kept)} records removed")
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
