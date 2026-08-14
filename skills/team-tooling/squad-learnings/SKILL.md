---
name: squad-learnings
description: >
  Use when an engineering learning worth the team's quarter-half review
  surfaces — a root cause that contradicts what everyone assumed, a "we
  thought the code handled this but it doesn't" discovery, an incident
  postmortem takeaway, or unexpected tool/platform/CI behavior; when the
  user says "log this learning", "capture this for the squad review", or
  "/squad-learnings"; when compiling learnings for a squad review, retro,
  or quarter-half readout; or to set up or remove automatic capture on
  this machine (install/uninstall).
argument-hint: "[capture <note> | review [cycle|all] | install | uninstall]"
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Skill
---

# squad-learnings

A per-machine ledger of engineering learnings, written down as they happen so
the quarter-half squad review compiles itself instead of relying on anyone's
memory. Works on a bare Claude Code install: all state is a folder of markdown
files in the user's home directory. No memory system, plugin, or hook needed.

The intended flow: run `install` once, sessions append learnings proactively
from then on, and `review` at cycle end turns the accumulated history into a
slide-ready readout. Until `install` is run, capture still works whenever this
skill is invoked or matched; it is just not proactive.

## Ledger

- Folder: `~/.claude/squad-learnings/` (Windows: `%USERPROFILE%\.claude\squad-learnings\`).
- One file per cycle: `<year>-Q<quarter>H<half>.md`. Half 1 is days 1-46 of
  the calendar quarter, half 2 is the rest. New files start with a
  `# <cycle-name>` heading.
- Entry format (also embedded in `references/capture-block.md`; keep the two
  in sync when editing):

```
## <yyyy-mm-dd> | <repo or area> | <one-line title>
tags: <domain-discovery|incident|tooling|process> | ours: <yes|no>
<2-4 lines: what was assumed vs what is actually true, plus a pointer to
the evidence (PR, incident id, file).>
```

`ours: yes` means the learning came from our own mistake; `ours: no` means it
is a discovery about the system. Reviews often present only `ours: no` items,
so classify honestly. Never store secrets, tokens, connection strings,
customer data, or personal information in an entry.

## Modes

Pick by argument; with no argument, treat prose describing a learning as
`capture` and "what have we learned" phrasing as `review`.

### capture

1. Resolve today's cycle file; create the folder and file if missing.
2. Read the file's existing titles. If the learning matches one, extend that
   entry rather than adding a duplicate.
3. Append one entry in the format above. Keep the body to 4 lines or fewer:
   assumption, reality, evidence. Write it so a reader with no context
   understands it at review time.
4. Confirm to the user with the file path and the entry title.

### review [cycle | all]

1. Scope: the named cycle file, `all` files in the folder, or the current
   cycle by default. If the folder is empty or missing, say so and suggest
   `install`; do not invent content. Also skim adjacent cycle files for
   entries whose dates fall inside the requested cycle (a boundary
   miscount at capture time misfiles entries) and include them.
2. Supplementary sources, only when the user asks to include them: fact
   files under `~/.claude/projects/*/memory/` (resolve `~` to the user's
   home directory; `%USERPROFILE%` on Windows) modified inside the cycle
   window; say so when the folder cannot be found. Treat matches as
   candidates, dedupe against the ledger, and screen every import: work
   learnings only — drop anything personal, private, or unrelated to the
   team's systems, applying the same no-secrets rule as ledger entries.
   Count these reads and drops in the accounting line.
3. Distill: merge duplicates, group by repo or area, rank by impact to the
   wider team.
4. Output two sections — discoveries (`ours: no`) first, own-process lessons
   (`ours: yes`) second — as numbered, slide-ready bullets of 2-4 plain
   sentences each, understandable without prior context. Close with an
   accounting line: how many entries were read, how many are shown, and the
   titles of anything dropped or merged.
5. If the user wants it as a message and a `humanizer` skill is installed,
   run the draft through it. Deliver text only; never post to any channel or
   person yourself.

### install

1. Target the user-level `~/.claude/CLAUDE.md` (create it if missing). Never
   touch project-level CLAUDE.md files.
2. If the file already contains `squad-learnings:begin`, report that capture
   is already installed and stop.
3. Otherwise append the entire contents of `references/capture-block.md`
   verbatim (markers included) to the end of the file, with a blank line
   separating it from existing content.
4. Tell the user exactly what was modified, that future sessions will now
   capture proactively on a best-effort basis (a busy session can miss a
   learning, so spot-check the ledger occasionally), and that `uninstall`
   (or deleting the marker block) reverses it.

### uninstall

If `~/.claude/CLAUDE.md` or the markers are absent, report that capture
is not installed and change nothing. Otherwise remove everything between
and including the `squad-learnings:begin` and `squad-learnings:end`
markers from `~/.claude/CLAUDE.md`. Leave the ledger folder untouched;
say where it lives so the user can archive or delete it.

## Common mistakes

- Waiting until review time to write things down. The whole point is capture
  in the moment; details are unrecoverable a month later.
- Essay entries. Four lines. The review step does the prose.
- Rewriting ledger history during review. Review distills; the ledger is
  append-only apart from extending an entry with new evidence.
- Logging routine work. A fixed bug with no broken assumption behind it is
  not a squad-review learning.
- Expecting proactive capture without `install`. The skill alone only fires
  when invoked or matched; the CLAUDE.md block is what makes it automatic.

Related skill: `contribution-log` records what you delivered; this skill
records what the team should learn. One event often deserves an entry in each.
