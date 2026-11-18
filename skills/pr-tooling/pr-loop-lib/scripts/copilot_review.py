"""Pull the findings out of a Copilot code review body.

Prints {"classification": "parse" | "skip", "findings": [...]}; "skip" means the
body holds neither a Suppressed comments section nor a previously missed issues block.
A finding is {"kind": "suppressed" | "missed", "severity": "high" | "medium" | "low" | null,
"path", "line", "title", "text", "key"}; "key" is "copilot|<path>|<title>".
Exit 2: a named section yielded fewer findings than it holds. Exit 64: bad call or unopenable body file.
The body may be UTF-8, UTF-8 with a BOM or UTF-16 with a BOM.
"""

import json
import re
import sys

USAGE = "Usage: python copilot_review.py BODY_FILE   (or - for stdin)"
EXIT_UNREADABLE_BODY = 2
EXIT_BAD_CALL = 64
ZERO_WIDTH = "\u200b"
SUPPRESSED_NAMED = "### Suppressed comments"
SUPPRESSED_HEADING = re.compile(r"^[ \t]{0,3}#{3,6}[ \t]+Suppressed comments\b.*$", re.M)
SUPPRESSED_ITEM = re.compile(
    r"^\*\*(?P<path>[^*\n]+?):(?P<line>\d+)(?:-\d+)?\*\*[ \t]*$", re.M)
SUPPRESSED_ITEM_LOOSE = re.compile(r"^\*\*[^\n]*\*\*[ \t]*$", re.M)
SUPPRESSED_END = re.compile(r"^- \*\*[^*\n]+:\*\*|^</details>", re.M)
DECLARED_COUNT = re.compile(r"\((\d+)\)")
MISSED_NAMED = re.compile(r"previously missed issues?\s*</strong>")
MISSED_OPEN = re.compile(
    r"<summary>\s*<strong>\s*(?P<count>\d+)\s+previously missed issues?\s*</strong>\s*</summary>")
SUMMARY = re.compile(r"<summary>(.*?)</summary>", re.S)
SEVERITY = re.compile(r'alt="(High|Medium|Low) severity"')
LOCATION = re.compile(r"^`(?P<path>[^`\n]+?):(?P<line>\d+)(?:-\d+)?`[ \t]*$", re.M)
TAG = re.compile(r"</?(?:picture|source|img|strong|b|em|i|code|a|br|span|sup|sub)(?=[\s/>])[^>]*>", re.I)
SENTENCE_END = re.compile(r"[.!?](?=\s+[^a-z\s]|\s*$)")
NOT_A_SENTENCE_END = re.compile(r"(?:^|\s)(?:e\.g|i\.e|vs|cf|\d+)$", re.I)
BULLET = re.compile(r"^\s*[-*+]\s+")
FENCE_LINE = re.compile(r"^ {0,3}(?:`{3,}|~{3,})", re.M)
FENCE_OPEN = re.compile(r"^ {0,3}(?:(`{3,})[^`]*|(~{3,}).*)$")
BACKTICK_RUN = re.compile(r"`+")
BLANK_LINE = re.compile(r"\n[ \t\r]*\n")


def _clean_path(path):
    return path.replace(ZERO_WIDTH, "").strip()


def _first_sentence(text):
    flat = " ".join(text.split())
    for m in SENTENCE_END.finditer(flat):
        if not NOT_A_SENTENCE_END.search(flat[:m.start()]):
            return flat[:m.end()]
    return flat


def _blank(chars, start, end):
    for i in range(start, end):
        if chars[i] not in "\r\n":
            chars[i] = " "


def _mask_code_spans(text):
    """Blank code spans: a backtick run closes at the next run of the same length, within one paragraph."""
    chars = list(text)
    runs = [(m.start(), m.end()) for m in BACKTICK_RUN.finditer(text)]
    fence_starts = {m.end() - len(m.group().lstrip(" ")) for m in FENCE_LINE.finditer(text)}
    i = 0
    while i < len(runs):
        start, end = runs[i]
        width = end - start
        close = None
        if start in fence_starts:
            i += 1
            continue
        for j in range(i + 1, len(runs)):
            if runs[j][0] in fence_starts or BLANK_LINE.search(text, end, runs[j][0]):
                break
            if runs[j][1] - runs[j][0] == width:
                close = j
                break
        if close is None:
            i += 1
            continue
        _blank(chars, start, runs[close][1])
        i = close + 1
    return "".join(chars)


def _mask(body):
    """Return body at the same length with fenced blocks and inline code blanked."""
    chars = list(body)
    lines = body.split("\n")
    starts = []
    pos = 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1
    i = 0
    while i < len(lines):
        opener = FENCE_OPEN.match(lines[i].rstrip("\r"))
        close = None
        if opener:
            marker = opener.group(1) or opener.group(2)
            closer = re.compile(r"^ {0,3}%s{%d,}[ \t]*$" % (re.escape(marker[0]), len(marker)))
            for j in range(i + 1, len(lines)):
                if closer.match(lines[j].rstrip("\r")):
                    close = j
                    break
        if close is None:
            i += 1
            continue
        _blank(chars, starts[i + 1], starts[close])
        i = close + 1
    return _mask_code_spans("".join(chars))


def _block_end(masked, start):
    """Return (start of the closing </details>, index past it) for the <details> opened before start.

    Both are len(masked) when it is never closed.
    """
    depth = 1
    for m in re.finditer(r"<details\b[^>]*>|</details>", masked[start:]):
        depth += 1 if m.group(0).startswith("<details") else -1
        if depth == 0:
            return start + m.start(), start + m.end()
    return len(masked), len(masked)


def _suppressed(body, masked):
    """Return (findings, complete); complete is False when the section holds more than was read."""
    heading = SUPPRESSED_HEADING.search(masked)
    if not heading:
        return [], SUPPRESSED_NAMED not in masked
    section = body[heading.end():]
    msection = masked[heading.end():]
    end = SUPPRESSED_END.search(msection)
    if end:
        section, msection = section[:end.start()], msection[:end.start()]
    items = list(SUPPRESSED_ITEM.finditer(msection))
    findings = []
    for i, m in enumerate(items):
        stop = items[i + 1].start() if i + 1 < len(items) else len(msection)
        fence = FENCE_LINE.search(msection, m.end(), stop)
        text = section[m.end():fence.start() if fence else stop]
        text = BULLET.sub("", text.strip())
        text = " ".join(text.split())
        path = _clean_path(m.group("path"))
        title = _first_sentence(text)
        findings.append({
            "kind": "suppressed", "severity": None, "path": path, "line": int(m.group("line")),
            "title": title, "text": text, "key": f"copilot|{path}|{title}",
        })
    declared = DECLARED_COUNT.search(heading.group(0))
    complete = (bool(findings)
                and len(findings) == len(SUPPRESSED_ITEM_LOOSE.findall(msection))
                and (declared is None or int(declared.group(1)) == len(findings)))
    return findings, complete


def _missed(body, masked):
    """Return (findings, complete); complete is False when the block holds more than was read."""
    opened = MISSED_OPEN.search(masked)
    if not opened:
        return [], MISSED_NAMED.search(masked) is None
    block_end, _ = _block_end(masked, opened.end())
    block = body[opened.end():block_end]
    mblock = masked[opened.end():block_end]
    findings = []
    unread = 0
    pos = 0
    while True:
        m = re.search(r"<details\b[^>]*>", mblock[pos:])
        if not m:
            break
        inner_start = pos + m.end()
        inner_end, after = _block_end(mblock, inner_start)
        item = block[inner_start:inner_end]
        pos = after
        summary = SUMMARY.search(mblock[inner_start:inner_end])
        loc = LOCATION.search(item)
        if not summary or not loc:
            unread += 1
            continue
        summary_text = item[summary.start(1):summary.end(1)]
        sev = SEVERITY.search(summary_text)
        title = " ".join(TAG.sub("", summary_text).split())
        text = " ".join(item[loc.end():].split())
        path = _clean_path(loc.group("path"))
        findings.append({
            "kind": "missed", "severity": sev.group(1).lower() if sev else None,
            "path": path, "line": int(loc.group("line")), "title": title, "text": text,
            "key": f"copilot|{path}|{title}",
        })
    complete = (bool(findings) and not unread
                and int(opened.group("count")) == len(findings))
    return findings, complete


def _scan(body):
    masked = _mask(body)
    suppressed, suppressed_complete = _suppressed(body, masked)
    missed, missed_complete = _missed(body, masked)
    findings = suppressed + missed
    readable = all(f["path"] and f["title"] and f["text"] for f in findings)
    return findings, suppressed_complete and missed_complete and readable


def parse(body):
    """Return (classification, findings) for one Copilot review body."""
    findings, _ = _scan(body)
    return ("parse" if findings else "skip"), findings


def _decode(raw):
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(USAGE, file=sys.stderr)
        return EXIT_BAD_CALL
    try:
        if argv[0] == "-":
            raw = sys.stdin.buffer.read()
        else:
            with open(argv[0], "rb") as fh:
                raw = fh.read()
    except OSError as exc:
        print(f"cannot read the body: {exc}", file=sys.stderr)
        return EXIT_BAD_CALL
    findings, complete = _scan(_decode(raw))
    if not complete:
        print("a findings section is present but not every finding could be read", file=sys.stderr)
        return EXIT_UNREADABLE_BODY
    print(json.dumps({"classification": "parse" if findings else "skip", "findings": findings}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
