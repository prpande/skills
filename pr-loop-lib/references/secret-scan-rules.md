# Secret scan rules

Used by `pr-autopilot/steps/04-open-pr.md` (sub-step 4a) and
`pr-loop-lib/steps/04.5-local-verify.md` (after fixer changes). BLOCKING:
any match halts the skill and surfaces the file + line to the user.

## Patterns

Run each pattern against the full text of every file about to be staged.

| # | Pattern | Matches |
|---|---|---|
| 1 | `-----BEGIN (?:RSA \|EC \|OPENSSH \|DSA \|)PRIVATE KEY-----` | Private keys |
| 2 | `(?i)(api[_-]?key\|secret[_-]?key\|access[_-]?token\|auth[_-]?token\|client[_-]?secret)\s*[:=]\s*["']?[A-Za-z0-9+/=_\-]{20,}["']?` | Keyed assignments |
| 3 | `(?i)password\s*[:=]\s*["'][^"']{8,}["']` | Password assignments |
| 4 | `[A-Za-z0-9]{32,64}\.apps\.googleusercontent\.com` | Google OAuth client IDs |
| 5 | `AKIA[0-9A-Z]{16}` | AWS access key ID |
| 6 | `(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[:=]\s*["']?[A-Za-z0-9+/=]{40}["']?` | AWS secret access key |
| 7 | `xox[baprs]-[A-Za-z0-9-]{10,}` | Slack tokens |
| 8 | `ghp_[A-Za-z0-9]{36}` | GitHub personal access tokens |
| 9 | `github_pat_[A-Za-z0-9_]{82}` | GitHub fine-grained PATs |
| 10 | `(?i)(Server\|Host\|Data Source)\s*=\s*[^;]+;\s*.*?(?:Password\|Pwd)\s*=\s*[^;]+` | Connection strings |
| 11 | `mongodb(\+srv)?://[^:]+:[^@]+@` | MongoDB connection strings |
| 12 | `postgres(?:ql)?://[^:]+:[^@]+@` | Postgres connection strings |
| 13 | `(?i)^\s*(SECRET\|PASSWORD\|TOKEN\|KEY)\s*=\s*\S{8,}\s*$` (in `.env` / `.env.*` files) | `.env` entries |

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
