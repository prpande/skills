# Setup 2: Interview

Four questions, one per turn, in this order. Wait for each answer before
asking the next. Write every answer into `<home>/corpus/setup.json` as it
arrives, so an interrupted interview resumes at the next question.

When `<home>/profile.md` already exists, first show its `cutoff`,
`window`, and `inner circle` lines and ask whether they still hold. On a
yes, copy them into `setup.json` and ask only question 4. On a no, ask all
four.

## 1. Cutoff

Ask: "When did you start drafting messages with AI tools? A month is
enough, or say never."

- Store `"cutoff": "YYYY-MM"`, or `"cutoff": "never"`.
- Messages sent before that month are trusted. Messages from that month
  on and over sixty words go through the filter step.
- "Never" means none of the person's own messages are filtered.

## 2. Inner circle

Skip this question when Slack is not in `channels`.

Ask: "Who is your inner circle on Slack? Name the people you DM most."

Resolve each name with the Slack user search tool. When a name matches
more than one person, show the matches and ask which one, in the same
turn as nothing else. Store:

```
"inner_circle": [{"name": "Ana", "slack_id": "U0123ABCD"}]
```

An empty list is allowed; every 1:1 DM is then an outer DM.

## 3. Sample window

Ask: "How far back should I read? The default is the last twelve months."

Store `"window": {"since": "YYYY-MM-DD", "until": "YYYY-MM-DD"}`, with
`until` set to today.

When the cutoff is a month and it is on or before the month of `since`,
nothing in the window is pre-cutoff, so every budget would fall back to a
module default. Say that, and offer to move `since` back to twelve months
before the cutoff. Store whichever window the person accepts.

## 4. Borrowing from a colleague

Ask: "Is there a colleague whose writing you want to borrow from? Give
their name and the channel to read them on, or say no."

On a name, ask one follow-up: "Have you told them their messages will be
read for this?"

- On a yes, resolve the colleague on that channel: a Slack user id, a
  GitHub login, or a Notion user id from the Notion user search. Store:

  ```
  "borrow": {"name": "Ana", "channel": "slack", "author": "U0123ABCD", "told": "2026-09-16"}
  ```

- On a no, store `"borrow": null` and say the colleague sample is skipped
  until they have been told.
- The borrow channel must be one of `channels`; when it is not, say so and
  store `"borrow": null`.

Add `"interview"` to `done`.
