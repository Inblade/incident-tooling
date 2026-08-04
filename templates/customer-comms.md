# Customer Communication Templates

Fill-in templates for incident communication, with notes on why each phrasing choice is
made. Load them into your status page tool so that posting is filling blanks rather than
composing under pressure.

## Tone: five rules

1. **Lead with the symptom, not the system.** The reader is trying to match your post
   against what they are seeing. "Uploads are failing" lets them do that instantly;
   "elevated error rates in the ingestion pipeline" does not.
2. **Plain, ordinary words.** Not "degradation of service availability" — "the site is
   slow". Not "remediation" — "fix". Formality reads as distance, and distance reads as
   evasion.
3. **Active voice, first person plural.** "We are investigating." Passive voice ("an issue
   has been identified") is the register of someone avoiding responsibility, and readers
   hear it that way even when it is unintentional.
4. **Say what you know and what you do not.** "We do not yet know the cause" is a
   perfectly good sentence. It is far better than an implied confidence you do not have.
5. **Never speculate about cause in a customer-facing update.** Early theories are wrong
   often enough that the retraction costs more than the reassurance was worth.

Two things to avoid that are easy to do accidentally:

- **Minimising language.** "A small number of users", "brief", "minor" — if the reader is
  one of the affected users, this reads as being told their problem does not count. Use
  neutral scoping instead: "some users", "users in the EU region".
- **Apologising in every sentence.** One sincere apology in the resolution note is worth
  more than an apology in each update. Repeated apology reads as filler.

---

## 1. Initial post

Post within 5–10 minutes of confirming customer impact. Do not wait to understand the
cause — the purpose of this post is to answer "is it me or is it you", and you can answer
that immediately.

```
Title: [Component] — [plain-language symptom]

We are investigating [symptom, described the way an affected user would describe it].

Affected: [feature or product area], for [scope: all users / users in <region> /
some users of <plan>].

What you may see: [concrete observable — errors, timeouts, stale data, failed logins].

[Workaround, if one exists — otherwise omit this line entirely.]

We do not yet know the cause. Our next update will be within [N] minutes.
```

### Worked example

```
Title: File uploads — failures for some users

We are investigating failures when uploading files.

Affected: file uploads, for some users. Other parts of the product appear to be
working normally.

What you may see: uploads that stall at 100% and then return an error. Files that
were already uploaded are not affected.

We do not yet know the cause. Our next update will be within 30 minutes.
```

### Notes

- The title carries most of the value. Many people see only the title, in an email subject
  or a Slack notification.
- "Other parts of the product appear to be working normally" is worth including when true.
  It stops people from assuming a total outage.
- "Files that were already uploaded are not affected" answers the question the reader has
  not asked yet — is my existing data safe. Pre-empting it saves support contacts.
- Committing to a next-update time in the first post sets the contract for the rest of the
  incident.

---

## 2. Update — investigating, no new information

The hardest one to post and the most valuable. Silence is read as abandonment.

```
We are still investigating [symptom]. We do not have a cause yet.

[Optional: what you have ruled out, if it is meaningful to a customer.]

[Restate scope if it has changed.]

Next update within [N] minutes.
```

### Worked example

```
We are still investigating the upload failures. We have not identified the cause yet.

We have confirmed that no uploaded data has been lost.

Next update within 30 minutes.
```

Note the substance: even with no progress on the cause, "no data has been lost" is a real
answer to a real worry. Look for something true and reassuring to include; if there is
nothing, post anyway.

---

## 3. Update — cause identified

```
We have identified the cause of [symptom] and are working on a fix.

[One sentence of cause, in customer-relevant terms. No internal system names.]

[Current impact, restated — it may have changed since the initial post.]

[ETA if genuinely confident, phrased as a range. Otherwise: the next update time.]
```

### Worked example

```
We have identified the cause of the upload failures and are deploying a fix.

A configuration change made earlier today caused our storage layer to reject
uploads above a certain size.

Uploads under 10 MB are working normally. Uploads above 10 MB are still failing.

We expect the fix to be live within 30 minutes. Next update by 15:20 UTC.
```

### Notes

- "A configuration change made earlier today" is honest without being self-flagellating,
  and without naming a person or a system.
- The refined scope ("under 10 MB working, above 10 MB failing") is genuinely useful — some
  readers can now unblock themselves.
- ETA and next-update time together. If the ETA slips, the next-update commitment still
  stands, which means you post before the ETA passes rather than after.

---

## 4. Update — fix applied, monitoring

```
We have applied a fix and [symptom] has stopped. We are monitoring to confirm the
issue is fully resolved.

[Anything the customer needs to do — retry, refresh, reconnect. Say "no action is
needed" explicitly if that is the case.]

[Any residual effects — a backlog draining, delayed data catching up.]

We will confirm resolution within [N] minutes.
```

### Worked example

```
We have applied a fix and uploads are succeeding again. We are monitoring to
confirm the issue is fully resolved.

No action is needed. Uploads that failed during the incident were not saved and
will need to be retried.

We will confirm resolution within 60 minutes.
```

"No action is needed" and "will need to be retried" are the two sentences customers
actually act on. Be unambiguous about which applies — an ambiguous instruction here
generates more support load than the outage did.

---

## 5. Resolved

```
This incident is resolved. [Symptom] has been fixed and [feature] has been operating
normally since [time, with timezone].

Duration: [start] – [end] [timezone].
Impact: [what was affected, for whom, in one sentence].

[Any lasting effects and what the customer should do about them.]

We are sorry for the disruption. [If publishing a postmortem: "We will publish a
full postmortem within N business days."]
```

### Worked example

```
This incident is resolved. Uploads have been operating normally since 15:42 UTC.

Duration: 14:05 – 15:42 UTC (1h 37m).
Impact: file uploads above 10 MB failed for all users. No existing data was
affected or lost.

Files that failed to upload during this window were not saved and will need to be
uploaded again.

We are sorry for the disruption. We will publish a postmortem within five business
days.
```

### Notes

- Explicit start and end times with a timezone. Customers reconciling their own logs need
  them, and vague durations invite disputes later.
- One apology, at the end, plainly stated.
- Only promise a postmortem if you will publish one. An unfulfilled promise here is worse
  than never having made it.

---

## 6. Scheduled maintenance

Post at least 72 hours ahead.

```
Title: Scheduled maintenance — [component] — [date]

We will be performing maintenance on [component] on [date] from [start] to [end]
[timezone] ([duration]).

Expected impact: [what will be unavailable or degraded, and for how long].

[Action the customer should take, if any.]

We will post here when the maintenance begins and when it is complete.
```

Then post at the start, and at the end. A maintenance window that opens silently and
closes silently generates support tickets from people who did not see the advance notice.

---

## 7. Recurrence

If the incident comes back, say so plainly rather than quietly changing the status.

```
The issue has recurred. [Symptom] is affecting [scope] again.

We are treating this as ongoing and investigating further. [If the previous fix was
insufficient, say so.]

Next update within [N] minutes.
```

Hiding a recurrence behind a status change is the fastest way to lose the credibility the
rest of this process builds.

---

## 8. Vendor-caused incident

```
[Symptom] is caused by an ongoing incident at one of our infrastructure providers.

Affected: [scope].
[Workaround, if any.]

We are monitoring their status and will update here as we learn more. Their status
page: [link].

Next update within [N] minutes.
```

Name the provider only if it is public knowledge or already obvious. Do not editorialise —
you chose the dependency, and the customer's contract is with you, not with them. "We are
monitoring" is also a commitment: check that someone actually is.

---

## Internal announcement (not customer-facing)

Different audience, different content. Internal updates should be more specific and are
where speculation belongs.

```
:rotating_light: INCIDENT — [severity] — [one-line symptom]

Status: [investigating / identified / monitoring / resolved]
IC: [name]
Comms: [name]
Channel: #incident-[id]
Customer impact: [yes/no — what, for whom]
Status page: [posted at HH:MM / not posted, because ...]

Current understanding: [what we think is happening, including uncertainty]
Current action: [what is being tried right now]
Next update: [time]
```

Explicitly recording whether the status page has been posted — and if not, why — closes
the most common gap in incident communication: everyone assumed someone else had done it.

---

## Reusable phrasings

| Instead of | Write |
|---|---|
| "A small number of users" | "Some users" (or a specific scope) |
| "An issue has been identified" | "We have identified the cause" |
| "Service degradation" | "The site is slow" / "Uploads are failing" |
| "We apologise for any inconvenience" | "We are sorry for the disruption" (once, at resolution) |
| "Elevated error rates" | "Some requests are returning errors" |
| "We are working diligently" | "We are working on it" |
| "Root cause analysis is underway" | "We will publish a postmortem within N business days" |
| "The incident has been remediated" | "This is fixed" |
| "Partial availability" | "[Feature] is working; [feature] is not" |
