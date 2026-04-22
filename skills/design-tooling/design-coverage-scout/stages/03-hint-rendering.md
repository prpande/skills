# Scout Stage 03 — Hint rendering

## Inputs

- `<run-dir>/hint-draft.json` from stage 2.
- `~/.claude/skills/design-coverage-scout/hint-template.md` as the shape reference.

## Objective

Render `<design-coverage-install>/platforms/<name>.md.draft`, preview it to
the user in the live session, and on explicit approval move `.draft` →
`<name>.md`.

## Method

1. **Resolve target path.**

   ```python
   import os, pathlib
   scout_realpath = pathlib.Path(os.path.realpath(__file__)).parent.parent
   target_dir = scout_realpath.parent / "design-coverage" / "platforms"
   if not target_dir.exists():
       # Fallback — user installed via copy instead of symlink.
       target_dir = pathlib.Path.home() / ".claude" / "skills" / "design-coverage" / "platforms"
   target_dir.mkdir(parents=True, exist_ok=True)
   ```

2. **Refuse-overwrite.** If `<target_dir>/<name>.md` exists and `--force` was
   NOT passed, refuse loudly and tell the user to pass `--force` or choose a
   different `--platform-name`.

3. **Render to draft.** Read `hint-draft.json`. Emit `<name>.md.draft`:

   ```markdown
   ---
   name: <name>
   detect:
     - "<detect glob 1>"
     - "<detect glob 2>"
   description: <description>
   confidence: <confidence>
   ---

   ## 01 Flow locator
   <sections.flow_locator>

   ## 02 Code inventory
   <sections.code_inventory>

   ## 03 Clarification
   <sections.clarification>

   ## Unresolved questions
   <unresolved_questions bullets, if any>
   ```

   Drop the `## Unresolved questions` section entirely if the array is empty
   or absent.

4. **Live preview.** Print the drafted file to the user with a header:

   ```
   === DRAFT PLATFORM HINT ===
   <full file content>
   === END DRAFT ===
   Approve writing this to platforms/<name>.md? (yes / no / edit)
   ```

5. **Branch on response:**
   - `yes` → move `.draft` → `<name>.md`; run `python scripts/validate.py`
     against the parent skills repo (resolved from `target_dir`) to sanity-check;
     print success message including the final path; tell the user to commit and push.
   - `no` → delete `.draft`; exit.
   - `edit` → ask the user what to change, apply the change, re-preview.

6. **Post-rendering sanity check.** After the move, run `python scripts/validate.py`
   against the parent repo. If it fails, print the validator errors and refuse
   to finalize — move `<name>.md` back to `<name>.md.draft` so the repo stays
   clean, and ask the user to fix the issues before approving again.
