<!-- contribution-log:begin — installed by the contribution-log skill; delete everything between these markers to uninstall -->
## Contribution log

When a unit of work reaches a milestone in a session — a PR merged, a
feature or fix shipped, an incident diagnosed or resolved, a
design or document delivered, a substantial review completed, a migration
or rollout executed — append an entry to
`~/.claude/contribution-log/<year>-Q<quarter>.md` right away, without
being asked. Create the folder and file if missing; start a new file with
a `# <year>-Q<quarter>` heading. Entry format, appended at the end:

```
## <yyyy-mm-dd> | <repo or area> | <one-line what was delivered>
kind: <feature|fix|incident|review|design|doc|mentoring|ops|other> | size: <s|m|l>
<1-3 lines on the outcome and its impact: what it unblocked, who it
helped, numbers where the session produced them.>
links: <PR/issue/work-item/doc URLs from the session, or none>
```

Size: `s` under a day, `m` days, `l` a week or more. Include every
relevant link visible in the session (PR URL, work item, document) —
links are what make the record verifiable later.
One entry per delivered unit, not per commit or edit. If today's work
extends an existing entry (same PR or work item), update that entry and
its links instead of adding a new one. Record work-related outcomes
only; never include secrets, tokens, connection strings, customer data,
or personal information.
<!-- contribution-log:end -->
