<!-- squad-learnings:begin — installed by the squad-learnings skill; delete everything between these markers to uninstall -->
## Squad-learnings capture

When work in a session surfaces a learning the team would want at its
quarter-half review — a root cause that contradicts what was assumed, a
"we thought the code handled X, it doesn't" discovery, an incident
takeaway, or unexpected tool/platform behavior — append an entry to the
current cycle file in `~/.claude/squad-learnings/` right away, without
being asked. Do this in the same turn the learning surfaces; do not wait
for the task to finish.

Cycle file: `<year>-Q<quarter>H<half>.md`, where half 1 is days 1-46 of
the calendar quarter and half 2 is the rest. Create the folder and file
if missing (start a new file with a `# <cycle-name>` heading). Entry
format, appended at the end of the file:

```
## <yyyy-mm-dd> | <repo or area> | <one-line title>
tags: <domain-discovery|incident|tooling|process> | ours: <yes|no>
<2-4 lines: what was assumed vs what is actually true, plus a pointer to
the evidence (PR, incident id, file).>
```

`ours: yes` means our own mistake; `ours: no` means a discovery about
the system. A routine fix with no broken assumption behind it is not a
squad-review learning; skip it.
Skim the file's existing titles first and extend a matching entry instead
of duplicating it. Never put secrets, tokens, connection strings,
customer data, or personal information in an entry; entries end up in
presentations.
<!-- squad-learnings:end -->
