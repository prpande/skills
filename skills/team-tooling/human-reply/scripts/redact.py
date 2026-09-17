"""Replace secret-shaped substrings in corpus records with <redacted:kind> placeholders.

Reads JSONL records on stdin, appends redacted records to --out, and prints
how many records were touched to stderr.
"""
import argparse
import json
import re
import sys

# Rules 1-12 of pr-loop-lib/references/secret-scan-rules.md, verbatim and in
# order. Rule 13 applies only to .env files and has no meaning for messages.
SOURCE_PATTERNS = [
    ("private-key", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"),
    ("keyed-assignment", r"""(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\s*[:=]\s*["']?[A-Za-z0-9+/=_\-]{20,}["']?"""),
    ("password", r"""(?i)password\s*[:=]\s*["'][^"']{8,}["']"""),
    ("google-oauth-client-id", r"[A-Za-z0-9]{32,64}\.apps\.googleusercontent\.com"),
    ("aws-access-key-id", r"AKIA[0-9A-Z]{16}"),
    ("aws-secret-access-key", r"""(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[:=]\s*["']?[A-Za-z0-9+/=]{40}["']?"""),
    ("slack-token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("github-pat", r"ghp_[A-Za-z0-9]{36}"),
    ("github-fine-grained-pat", r"github_pat_[A-Za-z0-9_]{82}"),
    ("connection-string", r"(?i)(Server|Host|Data Source)\s*=\s*[^;]+;\s*.*?(?:Password|Pwd)\s*=\s*[^;]+"),
    ("mongodb-connection-string", r"mongodb(\+srv)?://[^:]+:[^@]+@"),
    ("postgres-connection-string", r"postgres(?:ql)?://[^:]+:[^@]+@"),
]

# The scan rule only needs the header to block a commit; redaction must also
# remove the key body, so rule 1 is widened to the whole PEM block.
PEM_BLOCK = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"
    r"[\s\S]*?(?:-----END (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----|\Z)"
)

# Skill-local additions, kept apart so the list above stays a verbatim copy.
# Group 1 is kept and only the value after it is replaced. A value starting
# with "<" is skipped, so a secret a copied rule already replaced is not counted twice.
SKILL_LOCAL_PATTERNS = [
    ("password", r"(?i)([?&]pwd=)[^&#\s<][^&#\s]*"),
    ("cookie", r"(?i)(\b(?:set-)?cookie:[ \t]*)(?=[^\s=;]+=)[^\r\n]+"),
    ("cookie", r"(?i)((?<![\w.])(?:_cfuvid|__cf_bm|cf_clearance|JSESSIONID|PHPSESSID|sessionid|session|connect\.sid)=)[^;\s&'\"<][^;\s&'\"]*"),
    ("token", r"(?i)(\bBearer[ \t]+)[A-Za-z0-9\-._~+/]{20,}=*"),
]

COMPILED = [(kind, re.compile(pattern)) for kind, pattern in SOURCE_PATTERNS]
LOCAL_COMPILED = [(kind, re.compile(pattern)) for kind, pattern in SKILL_LOCAL_PATTERNS]


def redact(text):
    """Return (redacted_text, replacement_count)."""
    total = 0
    text, n = PEM_BLOCK.subn("<redacted:private-key>", text)
    total += n
    for kind, pattern in COMPILED:
        if kind == "private-key":
            continue
        text, n = pattern.subn(f"<redacted:{kind}>", text)
        total += n
    for kind, pattern in LOCAL_COMPILED:
        text, n = pattern.subn(rf"\g<1><redacted:{kind}>", text)
        total += n
    return text, total


def main(argv=None, stdin=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="JSONL file to append redacted records to")
    args = parser.parse_args(argv)
    stdin = stdin if stdin is not None else sys.stdin
    seen = touched = 0
    with open(args.out, "a", encoding="utf-8", newline="\n") as out:
        for line in stdin:
            if not line.strip():
                continue
            record = json.loads(line)
            record["text"], count = redact(record["text"])
            seen += 1
            touched += 1 if count else 0
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"redact: {touched} of {seen} records touched", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    sys.exit(main())
