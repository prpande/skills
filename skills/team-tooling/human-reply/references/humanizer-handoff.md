# Humanizer handoff

The draft step runs a finished draft through the `humanizer` skill when it
is installed. Pass the draft with this instruction, with the slots
filled, and nothing else:

````
Remove AI writing patterns from the draft below. Constraints:
- You may delete words or replace a word or phrase with a plainer one.
  Never add a sentence, a clause, a greeting, a sign-off, or a caveat.
- Keep every fact, number, link, code span, fenced block, @mention, and
  placeholder in angle brackets exactly as written.
- Keep the markup: line breaks, blank lines after quote lines, bullets,
  and backticks stay where they are.
- These phrases are the author's own. Keep them even if your list flags
  them: <phrasebook phrases used in the draft, one per line, or "none">
- The draft must stay at or under <budget> words.
Return only the edited draft.

<draft>
````

After it returns:

1. Check that every phrase passed as the author's own is still there. Put
   back any that was removed.
2. Count words. Over the budget, trim the humanizer's output, never by
   restoring cut text.
3. Run the channel audit checklist again.
