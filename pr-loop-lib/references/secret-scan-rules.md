# Secret scan rules

Used by:
- `pr-autopilot/steps/04-open-pr.md` sub-step 4a — scans the initial PR
  commit's staged files.
- `pr-loop-lib/steps/06-commit-push.md` pre-stage secret scan — re-scans
  any files a fixer subagent modified before they are staged for the
  address-feedback commit.

BLOCKING: any match halts the skill and surfaces the file + line to the
user. `pr-loop-lib/steps/04.5-local-verify.md` runs build/test sanity
checks but does NOT invoke this scan (the scan runs at commit-stage time
in step 06, immediately after verify).

## Patterns

Regex flavor: **Python `re`** (compatible with most modern engines; `ripgrep`
uses the same syntax). Run each pattern against the full text of every
file about to be staged. Patterns are listed in a fenced block (one per
line, unescaped) because markdown-table cells would force `|` to be
escaped and change the meaning.

```
# 1 — Private keys
-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----

# 2 — Keyed assignments (api_key, secret_key, access_token, auth_token, client_secret)
(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\s*[:=]\s*["']?[A-Za-z0-9+/=_\-]{20,}["']?

# 3 — Password assignments
(?i)password\s*[:=]\s*["'][^"']{8,}["']

# 4 — Google OAuth client IDs
[A-Za-z0-9]{32,64}\.apps\.googleusercontent\.com

# 5 — AWS access key ID
AKIA[0-9A-Z]{16}

# 6 — AWS secret access key
(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[:=]\s*["']?[A-Za-z0-9+/=]{40}["']?

# 7 — Slack tokens
xox[baprs]-[A-Za-z0-9-]{10,}

# 8 — GitHub personal access tokens
ghp_[A-Za-z0-9]{36}

# 9 — GitHub fine-grained PATs
github_pat_[A-Za-z0-9_]{82}

# 10 — Connection strings (with password)
(?i)(Server|Host|Data Source)\s*=\s*[^;]+;\s*.*?(?:Password|Pwd)\s*=\s*[^;]+

# 11 — MongoDB connection strings
mongodb(\+srv)?://[^:]+:[^@]+@

# 12 — Postgres connection strings
postgres(?:ql)?://[^:]+:[^@]+@

# 13 — .env entries (SECRET/PASSWORD/TOKEN/KEY assignments; apply only to .env / .env.* files)
(?i)^\s*(SECRET|PASSWORD|TOKEN|KEY)\s*=\s*\S{8,}\s*$
```

## File-type guardrails

Extra-strict for these paths — halt on ANY GUID-shaped string or any
assignment of a 20+ char opaque value:
- `appsettings*.json`
- `.env`, `.env.*`
- `*.config`, `web.config`, `app.config`
- Files with paths containing `secrets`, `credentials`, or `keys`

## Allowlist

These are not secrets (skip when matched):
- `example.com`, `your-key-here`, `replace-me`, `CHANGE_ME` in any case.
- Values exactly matching `00000000-0000-0000-0000-000000000000` or
  `12345678-1234-1234-1234-123456789abc` (obvious placeholders).
- The GUID inside an obvious documentation example (e.g., inside a
  Markdown code fence tagged `json` or `yaml` where a surrounding
  paragraph says "example" or "placeholder").

## Handling

On first match the skill halts with:

```
Secret-scan BLOCK:
  file: <path>
  line: <N>
  rule: #<rule-number>  <rule-description>
  matched substring: <first 40 chars>...

Resolve by:
  - replacing the value with a secret-manager reference (e.g., AppSecrets:...)
  - moving the value into a gitignored .env file
  - or confirming it is a false positive in conversation before re-invoking
```

Do not stage the file. Do not push. Wait for user.
