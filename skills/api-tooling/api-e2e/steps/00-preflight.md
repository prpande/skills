# Phase 0 — Preflight: tooling & access probe

Detect what exists on this machine. Every gap degrades to "ask the user" —
nothing is assumed installed, and no missing tool blocks the run.

Resolve `{scratchpad}` to this session's private scratchpad directory
(absolute path) before running anything; every later phase substitutes the
same path.

Create the run workspace first:

```bash
mkdir -p "{scratchpad}/api-e2e/secrets" "{scratchpad}/api-e2e/scripts" "{scratchpad}/api-e2e/results"
```

## Probe (non-fatal, one pass)

Run each probe; record the outcome in the Capabilities table:

```bash
gh --version        # GitHub CLI
az --version        # Azure CLI (optional, heaviest dependency — never required)
curl --version
jq --version || python --version   # at least one JSON processor
git rev-parse --show-toplevel      # inside the target repo? (run from the repo if known)
```

For MCP-provided pipeline tools (e.g., an Azure DevOps MCP server), use
ToolSearch with a keyword query like "pipelines get build" — presence of
matching tools means MCP access exists. Interactively-authenticated MCP
servers may be absent in headless runs; treat absence as a normal gap.

## Access ladders (record the selected rung per capability)

**Target repo access** — the run derives everything from the deployed repo
head, so one of these must exist:
1. A local checkout the run can `git -C <path>` into at the right commit.
2. A GitHub (or equivalent) token the user pastes — verify with one benign
   API read before recording it as working.
3. Last resort: the user pastes specific files on request. Acceptable but
   slow; tell the user derivation quality depends on what they paste.

**Pipeline visibility** (PR mode deploy monitoring only — zero pipeline
access is acceptable because the build fingerprint, not the pipeline, is
ground truth for what is deployed):
1. MCP pipeline tools (if the probe found them).
2. Plain REST with a user-supplied PAT (read scope for builds), Basic auth
   via curl. A raw pipeline URL (e.g., `dev.azure.com/...`) is NOT directly
   fetchable without auth — never assume it is.
3. The user runs the check themselves and pastes the result.

## Capabilities table

Write `{scratchpad}/api-e2e/run-context.md` starting with:

```markdown
# api-e2e run context
## Capabilities
| capability | status | detail |
|---|---|---|
| repo access | tool / user-mediated | <rung + how verified> |
| pipeline visibility | tool / user-mediated / none | <rung> |
| http client | tool | curl <version> |
| json processor | tool | jq / python |
```

Secrets never go into this file — mint scripts live in
`{scratchpad}/api-e2e/secrets/` only.

## Gate

The run knows, for each capability it will need, either a working tool or
the user-mediated fallback. Do not proceed to the interview until the
Capabilities table has a row for repo access, pipeline visibility, http
client, and JSON processor.
