# Status Page Strategy

The status page is a product decision that engineers end up owning. The questions below
are much easier to answer at 11am on a Tuesday than during an incident, which is the whole
argument for writing them down in advance.

## What the status page is for

One job: **reduce the cost of the incident to the people affected by it.**

Concretely, a customer hitting an error wants to know three things, in this order:

1. Is it me or is it you?
2. Are you aware?
3. When can I stop checking?

That is the entire content model. Everything else — root cause narratives, architecture
diagrams, apologies — belongs in the postmortem, not the incident update.

Secondary benefits that follow from doing the primary job well: fewer support tickets
(often dramatically fewer), account managers who are not guessing, and a record that
matters during a contract renewal.

Non-goals, worth stating explicitly because they cause bad decisions:

- It is not a marketing surface. Uptime percentages that nobody believes damage trust more
  than a candid incident log builds it.
- It is not a legal document. Careful phrasing is fine; evasive phrasing is obvious.
- It is not a real-time debugging feed. Updates are for customers, not for engineers.

## When to post

Two failure modes, and one is much worse than the other.

**Posting too much** produces alert fatigue on the customer side. People stop reading, and
the page loses its signal.

**Posting too little** — or too late — produces support tickets, angry escalations, and a
credibility problem that outlasts the incident by months. The sentence you never want to
hear is "we found out from our customers before we found out from your status page."

Between those, err toward posting. The cost is asymmetric.

### A workable trigger rule

Post publicly when **any** of these is true:

- Customer-visible functionality is degraded or unavailable for **more than 5 minutes**.
- Any customer-visible error rate exceeds normal for **more than 10 minutes**.
- Data is delayed beyond its normal freshness in a way customers can observe.
- Support has received **two or more** independent reports of the same symptom.
- The fix will require a maintenance window or customer action.
- You are about to do something that might make it worse (a risky mitigation).

Do **not** post for:

- Internal-only degradation with no customer impact — even if it was terrifying.
- Anything already resolved in under 5 minutes with no support contact. Posting a
  five-minute blip after the fact mostly generates questions.
- Single-customer issues. Those are support conversations, not status page posts.
- Near misses. Those go in the internal record.

### Automate the trigger, not the content

The decision to post should not depend on someone remembering. Wire the alert that fires
on customer-visible impact to also create a **draft** incident, and make publishing a
one-click confirmation. The bottleneck during an incident is attention, and this removes
one demand on it.

Do not auto-publish content. See `automation-opportunities.md` — this is the clearest
example of the automation boundary.

## Who writes it

The incident commander decides *whether* to post. Someone who is not doing hands-on
mitigation writes the words. If the person debugging is also drafting customer
communications, both are being done badly.

On a small team where those are the same person: write the initial post, then set a timer
for the next update and go back to fixing. A short post now is worth more than a
well-crafted one in forty minutes.

**In whose words** — the voice question, which matters more than it sounds:

- **Not the engineer's.** "The Redis cluster failed over and the connection pool did not
  recover" is accurate and useless to a customer. Nobody outside knows what depends on
  Redis.
- **Not marketing's.** "We are experiencing a service interruption and apologise for any
  inconvenience" says nothing, and everyone can tell.
- **The affected user's.** Describe the symptom the way someone hitting it would describe
  it: "Uploading files is failing", "The dashboard shows stale data", "Login is timing
  out for some users."

The test: could a customer read this and immediately tell whether it explains what they
are seeing? If they have to infer, rewrite it.

## What to publish

### Always

- **What is affected**, in user-facing terms. Name the feature, not the service.
- **What the user experiences.** Errors? Slowness? Wrong data? Silent failure?
- **Scope.** All users, a region, a subset, one plan tier. "Some users" is acceptable when
  true; be more specific when you can.
- **Status.** Investigating / Identified / Monitoring / Resolved.
- **When the next update is coming.** This is the single most valuable line in the post
  and the most commonly omitted one. It converts "should I keep refreshing" into "I will
  check back in 30 minutes."
- **A workaround**, if one exists.

### Never

- **Internal hostnames, service names, or infrastructure detail.** It leaks architecture
  and helps nobody.
- **Named individuals.** Not the person who ran the command, not the vendor's engineer.
- **Blame directed at a vendor**, even when accurate. "Our upstream provider is
  experiencing an outage" is fine. "AWS broke us again" is not — you chose the dependency.
- **Speculation about cause.** Early theories are wrong at a high rate, and a retracted
  cause is worse than no cause.
- **Recovery times you are not confident in.** See below.
- **Anything you would not want quoted in a news article**, because it may be.

### The ETA problem

Customers want an ETA. You usually cannot give one honestly.

A missed ETA is far more damaging than no ETA — it converts "they are working on it" into
"they do not know what they are doing." So:

- **When the cause is unknown:** do not give one. Give an update cadence instead: "We do
  not have an estimate yet. Next update within 30 minutes."
- **When the fix is known and its duration is predictable** (a deploy, a failover, a
  restore with a measured restore time): give a range with margin. "We expect recovery
  within 30–60 minutes."
- **When you have given an ETA and will miss it:** post *before* the ETA passes, not
  after. Missing an ETA silently is the specific behaviour that destroys trust.

## Update cadence

Set it explicitly and hold to it.

| Severity | Cadence | Notes |
|---|---|---|
| Full outage | Every 20–30 minutes | Even with nothing new. "Still investigating, next update in 30 minutes" is a valid update. |
| Partial degradation | Every 45–60 minutes | |
| Resolved, monitoring | One post, then final | |

The hardest discipline is posting an update with no new information. It feels like
admitting failure. It is the opposite: silence reads as "they have gone home", and the
support queue reflects that within the hour.

## Status levels

Keep them few and mean something distinct by each:

- **Investigating** — we know something is wrong; we do not yet know what.
- **Identified** — we know the cause and are working on the fix.
- **Monitoring** — the fix is applied and metrics look correct; we are watching before
  declaring it done.
- **Resolved** — confirmed recovered.

Two rules that matter:

- Do not skip **Monitoring**. Declaring "Resolved" and then reopening is worse than a
  longer monitoring window. Hold it for at least one full cycle of the affected traffic
  pattern.
- Do not move backwards without saying so plainly. If it recurs, that is a new update on
  the same incident with an explicit "the issue has recurred", not a silent status change.

Component-level status ("API: degraded, Dashboard: operational") is worth the setup cost
if your product has parts that fail independently. If everything fails together, one
overall status is more honest.

## Structural decisions to make in advance

- **Host it off your own infrastructure.** A status page that goes down with the product
  is worse than none — it is a second outage during the first. Use a third-party provider
  or, at minimum, a separate account, region, and DNS zone.
- **Subscriptions.** Let customers subscribe by email, RSS, webhook, or Slack. Removes a
  large share of "is it fixed yet" contacts. Test the subscription delivery path regularly
  — a status page whose notifications silently stopped working is a common and quiet
  failure.
- **Access.** Everyone who might be an incident commander needs publish access *before*
  the incident. Credentials in a shared vault, tested. The number of times a status page
  update has been delayed by a password reset is not small.
- **A template library** in the tool itself, so posting is filling in blanks rather than
  composing under pressure. See `../templates/customer-comms.md`.
- **Scheduled maintenance** posted at least 72 hours ahead, with the window in UTC *and*
  the customer's likely local time.

## Historical record

Keep incidents visible after resolution. The instinct to hide them is understandable and
wrong: a status page with no history reads as either "nothing ever breaks here" (nobody
believes it) or "they delete the evidence" (worse).

What a good history buys:

- Credibility. A candid record of real incidents, handled well, is evidence of competence.
- Procurement. Enterprise security reviews ask for it. Having it ready shortens the sale.
- Internal honesty. A public record is a forcing function against quietly reclassifying an
  outage as a "brief degradation".

Link the public postmortem from the incident entry for anything significant. Publishing
postmortems is a strong trust signal and costs little — a public version can omit internal
detail while keeping the substance.

## Uptime numbers

If you publish a percentage, publish how it is calculated. An unexplained "99.99%" next to
an incident log showing four outages last month is worse than publishing nothing, because
it invites the reader to work out that the number is measured in a way that excludes what
they experienced.

If the SLA and the status page disagree, someone will notice, and it will be during a
renewal negotiation.

## Checklist to prepare before you need it

- [ ] Status page hosted independently of production infrastructure
- [ ] Publish access granted and tested for everyone who can be incident commander
- [ ] Templates loaded into the tool (initial, update, resolved, maintenance)
- [ ] Trigger criteria written down and agreed with support and leadership
- [ ] Subscription delivery tested end to end, on a schedule
- [ ] Components defined to match how the product actually fails
- [ ] A named non-responder role that owns communications during an incident
- [ ] Draft-creation automated from the customer-impact alert
- [ ] Someone has actually posted a test incident, in the real tool, at least once
