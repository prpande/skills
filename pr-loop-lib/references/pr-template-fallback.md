# PR template fallback

Used by `pr-autopilot/steps/04-open-pr.md` sub-step 4c when no repo PR
template is found.

## Template

```markdown
## Summary

[One-paragraph "why": what problem this solves, what the user-visible effect is. Derived from the session's implementation conversation, branch name, and commit messages.]

## Files Changed

| File | Change | Summary |
|------|--------|---------|
| [path] | Added / Modified / Renamed / Deleted | [one-line description] |
| ... | ... | ... |

## Security Impact

- [ ] No security impact
- [ ] The security impact is documented below:
  [Describe. Heuristics that imply impact: auth/authz changes, crypto / secrets handling, input validation or sanitization, new or changed API endpoints, database query / access-pattern changes, logging that could expose sensitive data. If none of these apply, check the "No security impact" box.]

## Testing

- [List the tests run locally, their pass counts, and any manual scenarios exercised.]

## Related Work

- [Link to issues, tickets (AB#..., JIRA-...), related PRs, or external dependencies.]
```

## Fill rules

1. **Summary** — infer from the current Claude Code session's conversation
   history, the branch name, and the top N commit messages. Two to three
   sentences.
2. **Files Changed** — generated from `git diff --stat` + a per-file one-line
   summary derived from the diff.
3. **Security Impact** — auto-classify using the heuristics in the template
   itself. If any heuristic applies, write a short impact paragraph and
   check the second box. Otherwise check "No security impact".
4. **Testing** — pull test counts from the output of the build/test commands
   run during `steps/04.5-local-verify.md` or the preflight-review step.
5. **Related Work** — scan branch name and commit messages for regexes:
   `AB#\d+`, `[A-Z]+-\d+` (JIRA-style), `#\d+` (GitHub issue), and any
   URLs that look like cross-repo PR links.

No `PR Author TODO:` placeholders ever ship. If a section has no content,
write an honest "n/a" or omit the section entirely.
