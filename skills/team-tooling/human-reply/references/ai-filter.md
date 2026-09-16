# AI filter

Keeps messages the person drafted with AI tools out of the profile. The
pattern list for each channel lives in that channel module's `ai-filter`
block; this file defines what each pattern id means, how a message is
scored, and the threshold. `scripts/ai_filter.py` implements it; the
no-Python path applies the same definitions by reading each message.

## Scope

A message is scanned when all of these hold:

- it is not held out for calibration
- it is over 60 words, counting each link and each fenced block as one word
- it is the person's own message sent in or after the cutoff month, or it
  is any message in a colleague sample

A person who answered "never" to the cutoff question has none of their
own messages scanned. Messages not scanned are always kept.

## Score

Each pattern id listed in the channel module scores one point when the
message shows it, unless the message's surface is in that pattern's
`exempt:` list. A message scoring the threshold or more is dropped.

The default threshold is 3. Setup lets the person change it once per
channel: lower it to any value from 1, or raise it by one point, to 4 at
most. A threshold other than 3 is written into the channel profile
header as `threshold: <n>`.

## Pattern ids

| Id | The message shows it when |
|---|---|
| `emoji-section-marker` | it has two or more non-blank lines and a line starts with an emoji or a `:shortcode:` followed by text |
| `tldr-block` | it has two or more non-blank lines and the first starts with "TL;DR" or "TLDR"; a "Summary" header counts under `headers-bold-labels` instead |
| `labelled-list` | it contains "Key highlights" or "Key takeaways", or a line ending in `:` is followed directly by a bullet line |
| `headers-bold-labels` | a line starts with a markdown header (`#` to `######`), or it contains a bold label such as `**Impact:**` or Slack's `*Impact:*` |
| `em-dash` | it contains an em dash |
| `parallel-triple` | it has three bullet lines in a row, and none of the person's messages of 60 words or fewer in this channel uses a bullet |
| `closing-restatement` | its last non-blank line starts with "In short", "In summary", "To summarize", "Overall", "All in all", "Net-net", or "Bottom line" |
| `vocabulary` | it uses two or more different words from the vocabulary block below, matched as word starts |
| `not-x-but-y` | it has a "not X, but Y" construction, or an "isn't X, it's Y" one |

## Vocabulary

Taken from the humanizer skill's list of overused AI words, without
"actually", "key", "highlight", and "landscape", which engineers use in
their literal sense too often to count.

```vocabulary
additionally
align with
crucial
delve
emphasizing
enduring
enhance
fostering
garner
interplay
intricate
intricacies
pivotal
showcase
tapestry
testament
underscore
valuable
vibrant
```

## Drop rate

The drop rate is dropped messages over all messages in the channel,
including short ones and held-out ones. `scripts/ai_filter.py` prints
it with the drop count and five dropped samples. Setup reads it before
and after the one threshold change, as its filter step describes.
