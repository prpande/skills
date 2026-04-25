# Scout Stage 03 — Hint rendering

## Inputs

- `<run-dir>/hint-draft.json` from stage 2.
- `~/.claude/skills/design-coverage-scout/hint-template.md` as the shape reference.

## Objective

Render `<target_dir>/<name>.md.draft` (where `<target_dir>` is
`<repo>/.claude/skills/design-coverage/platforms/` in the consuming repo),
preview it to the user in the live session, and on explicit approval move
`.draft` → `<target_dir>/<name>.md`.

## Method

1. **Resolve target path.** The `__file__`-based install-path arithmetic lives in a real `.py` module (`lib/target_path.py`) because `__file__` is undefined in `python -c` blocks. Import it from inline Python:

   ```python
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "design-coverage-scout" / "lib"))
   from target_path import resolve_target_dir
   target_dir = resolve_target_dir()
   ```

2. **Refuse-overwrite.** If `<target_dir>/<name>.md` **or** `<target_dir>/<name>.md.draft`
   exists and `--force` was NOT passed, refuse loudly: an existing `.md.draft`
   means a previous scout run is in progress. Tell the user to pass `--force`
   to overwrite, or choose a different `--platform-name`.

3. **Sanitize harvested section content before substitution.** Pass each
   `<sections.*>` string through `sanitize_section` to neutralize `---` and
   duplicate `## 0N …` lines that would corrupt the enclosing hint's
   frontmatter or confuse the section-header validator:

   ```python
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "design-coverage-scout" / "lib"))
   from sanitize import sanitize_section

   flow = sanitize_section(draft["sections"]["flow_locator"])
   code = sanitize_section(draft["sections"]["code_inventory"])
   clar = sanitize_section(draft["sections"]["clarification"])
   ```

4. **Render to draft.** Read `hint-draft.json`. Delegate rendering to `lib/render_draft.py` which handles the wave-2 frontmatter fields (`sealed_enum_patterns`, `multi_anchor_suffixes`, `default_in_scope_hops`, `hotspot_question_overrides`) in addition to the core fields:

   ```python
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "design-coverage-scout" / "lib"))
   from render_draft import render_draft_to_md
   from sanitize import sanitize_section

   sanitized = {
       "flow_locator": sanitize_section(draft["sections"]["flow_locator"]),
       "code_inventory": sanitize_section(draft["sections"]["code_inventory"]),
       "clarification": sanitize_section(draft["sections"]["clarification"]),
   }
   content = render_draft_to_md(draft, sanitized_sections=sanitized)
   draft_path = target_dir / f"{draft['name']}.md.draft"
   draft_path.write_text(content, encoding="utf-8")
   ```

5. **Pre-preview validation.** Run `python scripts/validate.py` against the
   `.draft` file (the draft is already written at step 4 but not yet moved).
   If the validator refuses, print its errors, delete the `.draft`, and
   report which `<sections.*>` was the likely source — the sanitizer in
   step 3 is not exhaustive; any novel structural char the user reports
   should be added to `lib/sanitize.py`.

6. **Live preview.** Print the drafted file to the user with a header:

   ```
   === DRAFT PLATFORM HINT ===
   <full file content>
   === END DRAFT ===
   Approve writing this to <target_dir>/<name>.md? (yes / no / edit)
   ```

7. **Branch on response:**
   - `yes` → move `.draft` → `<name>.md`; run `python scripts/validate.py`
     once more against the final file (belt + suspenders with step 5);
     print success message including the final path; tell the user to
     commit and push. If this final validate fails, move `<name>.md` back
     to `<name>.md.draft` so the repo stays clean.
   - `no` → delete `.draft`; exit.
   - `edit` → ask the user what to change, apply the change, re-preview.
