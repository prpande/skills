---
name: contribution-log
description: >
  Use when a piece of work completes and should be recorded for later
  performance conversations — a PR merged, a feature shipped, an incident
  resolved, a design or document delivered; when the user says "log this
  contribution", "add to my brag doc", or "/contribution-log"; when
  compiling what someone worked on over a week, month, cycle
  (quarter-half), quarter, or year; when preparing an annual review
  self-assessment or a promotion package; or to set up or remove
  automatic contribution capture on this machine (install/uninstall).
argument-hint: "[capture <note> | review [week|month|cycle|quarter|year|all|from..to] | promo [window] | install | uninstall]"
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, ToolSearch
---

# contribution-log

A per-machine, local-first record of what the user delivered, written as it
happens. External systems each see only a fragment of someone's work — GitHub
sees PRs, ADO sees work items, Notion sees documents, and much day-to-day work
appears nowhere at all. The ledger is the holistic record; links tie entries
back to those systems where they exist. At review or promotion time, the
history is already written.

The intended flow: run `install` once, sessions append contributions
proactively from then on, and `review`/`promo` turn the accumulated history
into a quantified readout. Works on a bare Claude Code install; all state is a
folder of markdown files in the user's home directory.

## Ledger

- Folder: `~/.claude/contribution-log/` (Windows: `%USERPROFILE%\.claude\contribution-log\`).
- One file per quarter: `<year>-Q<quarter>.md`, starting with a
  `# <year>-Q<quarter>` heading.
- Entry format (also embedded in `references/capture-block.md`; keep the two
  in sync when editing):

```
## <yyyy-mm-dd> | <repo or area> | <one-line what was delivered>
kind: <feature|fix|incident|review|design|doc|mentoring|ops|other> | size: <s|m|l>
<1-3 lines on the outcome and its impact: what it unblocked, who it
helped, numbers where the session produced them.>
links: <PR/issue/work-item/doc URLs from the session, or none>
```

One entry per delivered unit, not per commit. Extending an existing entry
(same PR or work item) beats adding a duplicate. Record work-related
outcomes only; never include secrets, tokens, connection strings, customer
data, or personal information.

## Modes

Pick by argument; with no argument, treat prose describing finished work as
`capture` and "what did I work on" phrasing as `review`.

### capture

1. Resolve the current quarter file; create the folder and file if missing.
2. Read existing titles and links; extend the entry for the same PR or
   work item (match on the links line, not title wording alone) instead
   of duplicating. Near a quarter boundary, also check the previous
   quarter's file before appending.
3. Append one entry in the format above. Include every relevant link visible
   in the session (PR URL, work-item id, document page). Size honestly:
   `s` under a day, `m` days, `l` a week or more of effort.
4. Confirm to the user with the file path and the entry title.

### review [window]

1. Window: `week`, `month`, `cycle` (quarter-half: days 1-46 of the quarter
   are half 1), `quarter`, `year`, `all`, or an explicit `from..to` date
   range. Default is the current cycle. Select entries by their dates across
   however many quarter files the window spans. If the ledger folder is
   empty or missing, say so and suggest `install`; do not invent content.
2. External enrichment is opt-in: only query sources the user names. GitHub
   via the `gh` CLI (PRs merged and issues closed in the window, whenever
   they were authored), Azure DevOps via
   its REST API when a PAT is configured, Notion or Slack via their connected
   tools when present. Skip anything unavailable without failing the review.
   Dedupe external items against the ledger; list items found externally but
   missing locally and offer to backfill them as entries.
3. Output, grouped by theme or area after merging entries that share a PR
   or work-item link: numbered contributions with their
   impact lines and links, then a quantified summary (counts by kind and
   size, plus any concrete numbers the entries themselves carry). Use only
   numbers that appear in entries or came back from the named sources; never
   estimate or invent metrics.
4. Close with an accounting line: entries read, entries shown, anything
   merged or out of window.

### promo [window]

For an annual review self-assessment or promotion package. Default window is
one year.

1. Gather exactly as `review` does, enrichment included if the user names
   sources.
2. Synthesize 3-6 impact themes (for example: shipped surfaces, incident
   response, cross-team influence, quality and process improvements). Under
   each theme: the strongest evidence entries with their links, scope
   ("affected N sites", "unblocked team X") only where an entry or source
   states it.
3. Produce a draft the user edits, not a finished claim sheet: flag every
   theme whose evidence is thin so the user can substantiate or drop it, and
   keep a links appendix so reviewers can verify. Close with review's
   accounting line (entries read, shown, merged, or out of window).
4. Deliver text only; never post or submit anywhere yourself.

### install

1. Target the user-level `~/.claude/CLAUDE.md` (create it if missing). Never
   touch project-level CLAUDE.md files.
2. If the file already contains `contribution-log:begin`, report that capture
   is already installed and stop.
3. Otherwise append the entire contents of `references/capture-block.md`
   verbatim (markers included) to the end of the file, with a blank line
   separating it from existing content.
4. Tell the user exactly what was modified, that future sessions will now
   record contributions proactively on a best-effort basis (a busy session
   can miss one, so spot-check the ledger occasionally), and that
   `uninstall` (or deleting the marker block) reverses it.

### uninstall

If `~/.claude/CLAUDE.md` or the markers are absent, report that capture
is not installed and change nothing. Otherwise remove everything between
and including the `contribution-log:begin` and `contribution-log:end`
markers from `~/.claude/CLAUDE.md`. Leave the ledger folder untouched;
say where it lives so the user can archive or delete it.

## Common mistakes

- Logging every commit. The unit is a delivered outcome.
- Waiting for review season. The point of the skill is that the history
  already exists; a year-old week is unrecoverable.
- Entries without links when links existed in the session. Links are what
  make the promo draft verifiable.
- Inventing or extrapolating metrics at review time. If a number is not in
  an entry or a queried source, it does not go in the output.
- Expecting GitHub/ADO/Notion to reconstruct the year. They hold fragments;
  the local ledger is the primary record and the reason this skill exists.

Related skill: `squad-learnings` records what the team should learn from an
event; this skill records what you delivered. One event often deserves an
entry in each.
