Build me a live status page artifact called "What needs your attention" that shows
what I need to follow up on today across my connected tools.

BEHAVIOR

1. Clarify first. Before building anything, ask me:
   - Which of my connected tools to pull from (Slack, Notion, Asana, Linear, Jira,
     email — whatever I actually have connected).
   - What counts as "needs attention" (direct mentions/DMs, items assigned to me,
     overdue/due today, unread activity).
   - The time window (24 hours / 3 days / 7 days).
   - Whether to auto-refresh on open or use a manual refresh button.

2. Probe before you build. For every connector tool you plan to call from the
   artifact, call it once in this session with a small representative query and
   inspect the real response shape. MCP wrappers often return pre-formatted
   markdown strings instead of structured JSON — build your parser around what
   you actually observe, not what you assume.

3. Capture enough context to identify the work. A one-line search snippet isn't
   enough to tell what work item is being discussed. For any matched message
   that lives in a thread or channel, follow it into the thread (e.g.
   slack_read_thread, or the equivalent for your connector) and pull the
   surrounding messages. Keep the full thread excerpt on each item so the
   clustering step has real context to work with.

4. Group by work item, not by source type. After collecting items, call
   window.cowork.sample() with a tight JSON-only prompt that clusters items into
   specific work-item groups — e.g. "X migration – Y repo PRs", "Gen AI Copilot
   training rules", "Staff Identity rollout" — not generic buckets like
   "engineering" or channel names. Titles should name the deliverable or
   question. Every item belongs to exactly one group; anything truly orphan goes
   into an "Other" group that sorts last. Use this response shape:
   {"groups":[{"title":string,"description":string,"indexes":number[]}]}
   Fall back to grouping by channel if the LLM returns nothing parseable.

5. Dedupe. The same message may appear in multiple searches (e.g. a mention
   that's also in a DM). Key on channel_id + message_ts and merge the source
   tags so each item can display multiple source pills.

LAYOUT

- Dark theme. Light text on a near-black background, accent colors chosen for
  dark mode (not washed-out pastels).
- Header with title, one-line subtitle describing the data, a live/partial
  status dot with "Updated HH:MM", and a small stage indicator (e.g.
  "Searching…", "Loading threads…", "Clustering…").
- Summary strip with four stat tiles: Work items with activity, Total items,
  Mentions & DMs (with a breakdown), Saved for later (or the equivalent for
  your connector).
- Accordion list of work items. Each group is a <details class="topic"> element
  — all collapsed on initial render. The summary row shows: a colored indicator
  stripe, topic title, one-line description, channel/project reference pills,
  an item count badge, and an animated chevron that rotates on expand.
- Expand all / Collapse all buttons above the list for quick navigation.
- Inside each group, items render as cards with: source pills (@mention, DM,
  saved, etc.), channel or DM label, author, timestamp, reply-count pill, an
  "Open in <Tool> ↗" permalink, a 4-line clamped body preview, and a nested
  <details> that reveals the full thread text when clicked.

IMPLEMENTATION CONSTRAINTS

- Single self-contained HTML artifact. Inline all CSS and JS. No external
  network except approved CDNs.
- The artifact fetches live data on open via window.cowork.callMcpTool(name, args)
  and does lightweight synthesis via window.cowork.sample(prompt, data). Don't
  add your own refresh button — the artifact panel already has a Reload button.
- Use native <details>/<summary> for the accordion so keyboard navigation and
  accessibility work out of the box; style the summary with list-style: none
  and hide the default marker.
- Handle partial failures: if one source errors, render the others and mark
  the status dot as "Partial data".

Once it's built, show the artifact and ask me if I want to extend it with
additional connectors.
