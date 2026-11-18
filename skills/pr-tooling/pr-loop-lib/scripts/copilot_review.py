"""Pull the findings out of a Copilot code review body.

Usage: python copilot_review.py BODY_FILE   (or - for stdin)

Prints one JSON object {"classification": "parse" | "skip", "findings": [...]}.
Each finding is {"kind", "severity", "path", "line", "title", "text", "key"}:
"kind" is "suppressed" (a `### Suppressed comments` item) or "missed" (an item
of the "previously missed issues" block), "severity" is "high", "medium",
"low" or null, and "key" is the disposition key pr-watch records in
`handled_top_level_ids`. "skip" means the body holds neither section; the
verdict, overview, open issues and resolved issues are never findings.
Exit 2 on a body that names one of the two sections but yields no finding.
"""

import json
import re
import sys

ZERO_WIDTH = "​"
SUPPRESSED_HEADING = re.compile(r"^### Suppressed comments\b.*$", re.M)
SUPPRESSED_ITEM = re.compile(r"^\*\*(?P<path>[^*\n]+?):(?P<line>\d+)\*\*[ \t]*$", re.M)
SUPPRESSED_END = re.compile(r"^- \*\*[^*\n]+:\*\*|^</details>", re.M)
MISSED_OPEN = re.compile(r"<summary><strong>\d+ previously missed issues?</strong></summary>")
SEVERITY = re.compile(r'alt="(High|Medium|Low) severity"')
LOCATION = re.compile(r"^`(?P<path>[^`\n]+?):(?P<line>\d+)`[ \t]*$", re.M)
TAG = re.compile(r"<[^>]+>")
FIRST_SENTENCE = re.compile(r"^(.*?[.!?])(?=\s|$)", re.S)


def _clean_path(path):
    return path.replace(ZERO_WIDTH, "").strip()


def _first_sentence(text):
    flat = " ".join(text.split())
    m = FIRST_SENTENCE.match(flat)
    return m.group(1) if m else flat


def _block_end(body, start):
    """Index just past the </details> that closes the <details> opened before start."""
    depth = 1
    for m in re.finditer(r"<details\b[^>]*>|</details>", body[start:]):
        depth += 1 if m.group(0).startswith("<details") else -1
        if depth == 0:
            return start + m.start(), start + m.end()
    return len(body), len(body)


def _suppressed(body):
    heading = SUPPRESSED_HEADING.search(body)
    if not heading:
        return []
    section = body[heading.end():]
    end = SUPPRESSED_END.search(section)
    if end:
        section = section[:end.start()]
    items = list(SUPPRESSED_ITEM.finditer(section))
    findings = []
    for i, m in enumerate(items):
        chunk = section[m.end():items[i + 1].start() if i + 1 < len(items) else len(section)]
        fence = chunk.find("```")
        text = chunk[:fence] if fence >= 0 else chunk
        text = re.sub(r"^\s*\*\s+", "", text.strip())
        text = " ".join(text.split())
        path = _clean_path(m.group("path"))
        title = _first_sentence(text)
        findings.append({
            "kind": "suppressed", "severity": None, "path": path, "line": int(m.group("line")),
            "title": title, "text": text, "key": f"copilot|{path}|{title}",
        })
    return findings


def _missed(body):
    opened = MISSED_OPEN.search(body)
    if not opened:
        return []
    block_end, _ = _block_end(body, opened.end())
    block = body[opened.end():block_end]
    findings = []
    pos = 0
    while True:
        m = re.search(r"<details\b[^>]*>", block[pos:])
        if not m:
            break
        inner_start = pos + m.end()
        inner_end, after = _block_end(block, inner_start)
        item = block[inner_start:inner_end]
        pos = after
        summary = re.search(r"<summary>(.*?)</summary>", item, re.S)
        loc = LOCATION.search(item)
        if not summary or not loc:
            continue
        sev = SEVERITY.search(summary.group(1))
        title = " ".join(TAG.sub("", summary.group(1)).split())
        text = " ".join(item[loc.end():].split())
        path = _clean_path(loc.group("path"))
        findings.append({
            "kind": "missed", "severity": sev.group(1).lower() if sev else None,
            "path": path, "line": int(loc.group("line")), "title": title, "text": text,
            "key": f"copilot|{path}|{title}",
        })
    return findings


def parse(body):
    """Return (classification, findings) for one Copilot review body."""
    findings = _suppressed(body) + _missed(body)
    return ("parse" if findings else "skip"), findings


def names_a_section(body):
    return bool(SUPPRESSED_HEADING.search(body) or MISSED_OPEN.search(body))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__.splitlines()[2], file=sys.stderr)
        return 2
    if argv[0] == "-":
        body = sys.stdin.buffer.read().decode("utf-8")
    else:
        with open(argv[0], encoding="utf-8") as fh:
            body = fh.read()
    classification, findings = parse(body)
    if not findings and names_a_section(body):
        print("a findings section is present but no finding could be read", file=sys.stderr)
        return 2
    print(json.dumps({"classification": classification, "findings": findings}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
