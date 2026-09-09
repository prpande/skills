# Message shapes

Each shape is the user's own, taken from the corpus. Angle brackets mark
slots. Word counts are from the originals. Names in the examples are
replaced with <name> or <team>.

## In-thread reply, one point

```
<the point in one sentence>. <one sentence of evidence or reasoning, link inline>.
```

From the corpus:

```
Figured out the issue. It seems that the business gateway endpoint is not setting the pagination count parameter (first) correctly. <link|Example NR captures>
```

```
You can ignore them as well. 503, 502, 504 are not actionable. They happen when our downstream services dont respond correctly. They should only be a concern when they persist.
```

```
Yes this is a bug in the flow. Its filtering the staff based on the staff ID sent in the query parameter. I will update the validation logic so that it allows no staffId.
```

## Answering several questions in one reply

Quote each question with `>` and answer under it. This is the user's
standard shape for review comments and multi-question threads.

```
> We have decided to call accomplishment API through the BFF? If so, is a permission check required?
Yes to both. There should always be an authorization check in backend APIs.

> We are aligned with adding static logic in the accomplishment API?
Yes for now, I think.
```

## Cross-team ask or cold outreach in another squad's channel

```
Hi <@team-handle or name>, <"Good morning!" or nothing>
<one or two sentences: what we are doing and why we are here>. <doc or PR link inline>.
<the ask as a question; two or more asks become a numbered list, one line each>
Thanks! :slightly_smiling_face:
cc: <@squad>
```

From the corpus (69 words):

```
Hi <@team>, I needed help in figuring out the secrets key to use in Staffmgmt WebAPI config for ClientIds X and Y. Can you please guide how I can go about getting (or creating, if needed) these? Since this repo was inherited by the current owning squad, folks are unaware of the correct keys.
Thanks! :slightly_smiling_face:
cc: @<name> @<name>
```

The numbered version:

```
Hey <name>
Hope you are doing well!
I had a couple of question regarding ObjectStore
1. Does it have any internal locks to handle race conditions when writing to the same file?
2. Is there a maximum allowed length for file names?
3. Are there any limits on storage and retrieval rates, or throttling?
Thanks! :slightly_smiling_face:
```

## PR review request

```
<"Hi <name>," or "Hey folks,"> floated the following PR that <what it does, one clause>. Please review whenever time permits.
<Pull Request NNN>: <title>
Thanks! :slightly_smiling_face:
cc: <@squad>
```

If the PR needs a why, it is one sentence before the link, or a single
`> TLDR:` quote line after the first sentence. Not a highlights list.

## Investigation update or root cause

```
<headline: what was found>
<two to four lines: the mechanism, numbers and NR link inline>
<one line: workaround or next step>
<optional: who it goes to next>
```

From the corpus (117 words, the top of the budget):

```
Nailed down the issue finally! :phew1:
It is an issue with the Stats endpoint. It seems that the API is filtering the data after fetching the rows from the DB, and it uses the first parameter to get that many rows. As seen in these <link|NR Captures>, changing the first parameter gradually returns all 19 of the client stats once it fetches about 60 rows.
For now we can workaround this by sending Int.Max.
I will raise this issue with <name> and team as well.
```

When the update covers more than one error class, one emoji marker per
class (":arrow-right: 401", ":arrow-right: 500") with a code block under
each is the user's own pattern. That is the only place section markers
belong, and never more than three.

## Design proposal or doc share

```
<"Hi <@team>," or "<@name> <@name>">
<one sentence: what the doc proposes and for which flow>. <doc link inline>.
<optional: two or three one-line bullets only if the reader must know the shape before opening the doc, for example the endpoint path and one constraint>
<the ask: "Please review whenever time permits." or "Let me know if this makes sense.">
Thanks! :slightly_smiling_face:
cc: <@squad>
```

Cap 100 words. If the reader needs more than three bullets to decide
whether to open the doc, the message is doing the doc's job.

## Pushback or disagreement

The user disagrees in the first sentence and gives the reason in the
second.

```
I dont think query based get APIs should be designed in that manner. With query based fetch there will always be conditional flow. The query parameters act like filters, which is what we are exposing here.
```

```
Honestly given the number of changes planned it seems like a heavy lift on both FE and BE. IMO, with other work planned, this would easily stretch beyond 2-3 quarters. Should we be thinking about chunking it out in a better manner?
```

## Bug triage reply to QA or a PM

```
<"Hi <name>," or "Hey <name>,"> I took a look at the bug. <what was tried and what was observed, one or two sentences>.
<the ask: a repro setup, credentials for the case, or confirmation the bug can close>
```

From the corpus (69 words):

```
Hey <name>, I took a look at the bug. It seems that currently there are no unrefunded purchases, that I can observe the issue on, under the client details mentioned in the repro steps.
Will it be possible for you to provide a purchase setup where we are observing the buggy behavior so that we can check the API responses received by BizApp and root cause the issue.
```

## Status update

```
Yesterday:
• <item>
• <item>

Today:
• <item>
• <item>
```

Items are fragments, not sentences.

## Heads-up or informational post

```
JFYI, <the fact in one sentence>. <one sentence on what it means for the reader or what is being done about it, link inline>.
```

## Outer DM, quick question

```
<"Hi <name>" on first contact of the day, else nothing>
<the question in one or two sentences, link if there is one>
<"Thanks!" only when the ask costs them time>
```

From the corpus (32 words):

```
Hey <name>
I just took a better look at the PR you had sent as well as the current infrastructure.yaml. It seems valkey is being used only for dev and staging. Is there a plan to migrate prod as well?
```

## Core squad DM

One line. Hinglish welcome. No greeting, no thanks.

```
Production mein E2E test fail ho raha hai. Ek baar dekh lena PR to disable it till we debug. <link>
```

# Before and after

Three real 2026 messages and the same content in the user's 2025 voice.

## Cross-team design share, 112 words to 58

Sent:

```
Hi <@team> We're modernizing the new Appointment Details screen on BizApp to read directly from the federated GraphQL graph instead of the legacy SOAP/REST path it uses today — one contract, data coming from the domains that own it, and no BFF in the middle.

On the Clients side that's a small set of additive changes: exposing automatedContactMethod on the client and adding two new resolvers — a progress-note status and forms count for an appointment. Additive-only — no SQL.

We are planning to do this implementation ourselves and are looking for your review and sign-off on the approach, so it fits the Clients subgraph.

:page_facing_up: Doc: <link>

Thanks! :pray:
cc: @<name>
```

Rewritten:

```
Hi <@team>, we are moving the BizApp Appointment Details screen to read from the federated graph instead of the legacy SOAP/REST path. On the Clients subgraph this needs automatedContactMethod on the client plus two new resolvers (progress note status, forms count). Additive only, no SQL changes.
Design doc: <link>
Please review whenever time permits.
Thanks! :slightly_smiling_face:
cc: @<name>
```

## Endpoint proposal, 117 words to 61

Sent:

```
Hi <@team>/team, sharing the design proposal for a new endpoint in the Scheduling domain: Assign Guest Visit as per the discussion in the thread.
This supports the BizApp workflow where a guest booked into a class is converted into a regular client. The endpoint updates the guest visit's ClientId to the newly created client via a direct SQL update within Scheduling — no Booking Service involvement.
Design doc: <link>
Key highlights:
• PUT /v1/subscribers/{SubscriberId}/class-visits/{VisitId}/assign-guest-visit
• Guest-only operation (ClientId = -2) — not a generic reassign
• Atomic SQL update (validation + update in one query)
• Stays entirely within the Scheduling domain

Would appreciate feedback and approval before we move to implementation. Thanks! :slightly_smiling_face:
cc: @<name>
```

Rewritten:

```
Hi <@team>, following up on the thread above, here is the design proposal for the Assign Guest Visit endpoint in Scheduling. It updates a guest visit's ClientId to the newly created client with a single SQL update, guest visits only (ClientId = -2), no Booking Service involvement.
Design doc: <link>
Please take a look and let me know if this makes sense.
Thanks! :slightly_smiling_face:
cc: @<name>
```

## In-thread reply with a preamble, 74 words to 24

Sent:

```
Thanks for the detailed explanation, that clears up a lot. Based on what you described, I think the right approach here would be to go with the first option since it keeps things simple and avoids the extra call. That said, I want to make sure I am not missing anything, so please let me know if you see any concerns with that direction and I will proceed accordingly.
```

Rewritten:

```
Makes sense, thanks. I will go with the first option since it avoids the extra call. Let me know if you see any concern with that.
```
