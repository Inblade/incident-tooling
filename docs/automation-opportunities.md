# What to Automate in Incident Response — and What Never To

## The principle

Automate **the work that competes for attention**, not the work that requires it.

During an incident the scarce resource is human attention, and it is scarcest exactly when
it is most valuable. Every task that can be done without judgement — gathering context,
opening channels, notifying, timestamping, formatting — is stealing attention from the
diagnosis. Those are the automation targets.

The tasks that *require* judgement — deciding what is happening, choosing a mitigation,
deciding to fail over, writing to customers — are not automation targets, and attempts to
automate them tend to produce confident wrongness at machine speed.

## Automate first (highest value, lowest risk)

Ranked by value delivered per unit of effort.

### 1. Incident channel bootstrap

One command or one click creates: a dedicated channel, a numbered incident record, a video
bridge link, the roles table pinned, and links to the relevant dashboards and runbooks.

**Why it is first.** It happens in every single incident, takes 5–10 minutes of someone's
attention, and requires zero judgement. It also standardises the starting state, which
makes everything downstream (timeline extraction, postmortems, metrics) tractable.

**What it removes:** the first ten minutes of an incident being logistics.

### 2. Automatic context gathering

When an incident opens, a bot posts into the channel:

- Recent deploys to the affected service, with links and authors
- Recent config/feature-flag changes
- Current error rate, latency, saturation graphs as images
- Related alerts firing right now
- Recent infrastructure events (node terminations, failovers, cloud provider status)
- Links to the service's runbook and dependency map

**Why it is high value.** "What changed recently?" is the first question in most incidents
and answering it manually means someone context-switching to a deploy dashboard. Having it
already in the channel routinely saves the first ten minutes.

**Caveat:** post it once, as a compact summary. A bot that floods the channel with graphs
every two minutes is actively harmful — it buries the human conversation.

### 3. Timeline capture

Every status change, deploy, alert, and marked message is timestamped and recorded
automatically. Humans mark significant moments with a convention (`!detected`, `!impact`,
`!action`, `!mitigated`) that costs nothing at the time.

**Why.** Reconstructing a timeline from 400 Slack messages three days later is the most
tedious part of writing a postmortem, and it is where postmortems die. It is also the part
most vulnerable to memory distortion — people misremember when they knew things.

See `../scripts/incident_timeline.py` for the extraction half of this.

### 4. Status page draft creation

The alert that fires on customer-visible impact also creates a **draft** status page
incident, pre-filled with the affected component and a template. A human reviews and
publishes with one click.

**Why.** The most common status page failure is not bad writing — it is nobody remembering
to post at all, or posting 40 minutes late. Removing the "someone must remember" step is
most of the value.

**The boundary:** draft, never publish. See below.

### 5. Escalation and paging

Automatic escalation when an incident is unacknowledged, when severity increases, or when
it exceeds a duration threshold. Automatic notification of the right secondary on-call
based on the affected service.

**Why.** Waiting for a human to decide to escalate is how a 20-minute incident becomes a
two-hour one. Paging is a mechanical decision that a rule expresses better than a tired
person.

### 6. Postmortem scaffolding

When an incident closes, generate a document pre-populated with: timeline, participants,
duration, affected services, related alerts, deploys during the window, and the standard
section headings.

**Why.** Reduces the postmortem from "write a document" to "fill in the analysis", which
is the part that has value. The completion rate for postmortems rises substantially when
the blank-page problem is removed.

### 7. Alert noise reporting

A weekly automated report: alerts per service, noisiest individual alerts, alerts that
fired and auto-resolved without action, alerts nobody acknowledged.

**Why.** Alert noise is the slow poison of on-call. It is invisible without measurement
because each individual alert seems reasonable — the problem is only visible in aggregate.

See `../scripts/oncall_report.py`.

### 8. Runbook link injection

Every alert carries a link to its runbook, and alerts without a runbook are flagged in
review. Trivial to implement, and it removes the "where is the documentation" step from
every page.

## Automate carefully (real value, real risk)

### Auto-remediation for known, bounded failures

Restarting a hung process, clearing a stuck queue consumer, scaling out on saturation,
failing over a replica, rotating a leaked credential.

**When it is right:** the failure mode is well understood, the remediation is idempotent
and bounded, and it has been performed manually enough times to be confident.

**Requirements before enabling any of these:**

- **A rate limit.** Restart at most N times in M minutes, then stop and page. Without this,
  auto-remediation masks a worsening problem until it is much bigger — the classic pattern
  is a memory leak that gets restarted 200 times a day for six weeks and then takes the
  fleet down during a traffic peak.
- **Loud logging.** Every automated action announces itself in the incident channel with
  what it did and why. Silent automation makes systems incomprehensible during an
  incident: engineers debug a system that is changing underneath them for reasons they
  cannot see.
- **A kill switch** that any responder can use without a deploy.
- **Visible counters.** If auto-remediation fires 40 times this week, that number needs to
  be in front of someone.

### Automatic rollback on deploy failure

Genuinely valuable — most incidents are deploy-caused, and fast rollback is the highest-
leverage mitigation there is.

**But:** rollback is only safe if it is actually safe. Database migrations that are not
backwards compatible make rollback a data-loss event. Automatic rollback requires a
deployment discipline (expand/contract migrations, backwards-compatible schema changes)
that must exist first. Automating rollback without that discipline is automating a new
class of incident.

### Automatic scaling in response to load

Standard practice and usually correct. The failure mode to guard against: scaling in
response to a problem that scaling makes worse. More replicas hammering a saturated
database is a self-amplifying outage. Cap the maximum, and alert when the cap is reached
rather than raising it automatically.

### Chatbot-driven actions

`/incident restart-consumer orders-processor` from the channel. Good: auditable, visible to
everyone, no SSH, works from a phone.

Requires: the same authorisation as doing it directly (not weaker because it is
convenient), confirmation for destructive actions, and every invocation logged to the
channel.

## Never automate

### Publishing customer communications

Draft automatically. Never publish automatically.

An automatically published status page post will eventually announce an outage that is not
happening, or describe the wrong scope, or use wording that is technically true and
commercially catastrophic. Every one of these has happened somewhere, and the reputational
cost of one wrong public post exceeds the time saved by a hundred right ones.

The human step is small — read three sentences and click publish. Keep it.

### The severity decision

Severity determines who gets woken, whether customers are told, and how much money the
response costs. It depends on business context that monitoring does not have: which
customer is affected, what contractual commitment applies, what is happening in the
business this week.

Suggest a severity automatically. Let a human set it.

### Declaring an incident resolved

Metrics returning to normal is necessary and not sufficient. A queue that stopped growing
because the producer died looks identical to a queue that drained because the consumer
recovered. A human must confirm that the thing that was broken is working, for the reason
they think it is working.

Auto-resolving incidents also destroys the monitoring period, which is where you catch
incomplete fixes.

### Root cause determination

Automated correlation ("this incident is probably caused by deploy X") is a useful
*hypothesis generator* and a terrible *conclusion*. Presented as an answer, it anchors the
investigation on the first plausible story and makes people stop looking. The real cause is
frequently the second or third thing you consider.

Present correlations as "here is what changed recently", never as "here is the cause".

### Anything destructive without confirmation

Deleting data, terminating instances, dropping traffic, failing over a primary database.
The blast radius of a wrong automated destructive action exceeds the cost of a human
confirmation, always.

The specific trap: automation written for one context, invoked in another. A "clean up
stale resources" job that is correct in staging and catastrophic in production.

### Postmortem analysis

Generate the scaffolding. Never generate the conclusions. The value of a postmortem is the
thinking, and a document full of plausible auto-generated analysis produces the *artifact*
of learning without the learning. It also actively suppresses the useful discussion,
because the document already has answers.

## Judging a candidate

Before automating anything in incident response:

1. **How often does this happen?** Automating a once-a-year task is a hobby.
2. **Does it require judgement?** If a human must think, it is a checklist, not a script.
3. **What happens when it is wrong?** Not if — when. Bound the damage before shipping.
4. **Is it observable?** Automation that acts silently makes incidents harder, not easier.
5. **Can it be stopped?** By whoever is on call, without a deploy, within seconds.
6. **Has a human done it enough times to know the edge cases?** Automating a procedure
   nobody has performed manually is encoding assumptions, not experience.
7. **Does it degrade the skill?** If automation handles a failure so completely that nobody
   learns to handle it, the day the automation fails is much worse. Occasional manual
   exercise of automated paths is part of the cost.

## The failure mode nobody plans for

Automation becomes load-bearing quietly. The runbook says "the system handles this", the
people who remember the manual procedure leave, and then the automation fails — during an
incident, because that is when it is exercised.

Mitigations:

- Keep the manual procedure documented alongside the automation, and mark it as the
  fallback rather than as history.
- Exercise it in drills. See `tabletop-exercises.md` — "the automation is down" is one of
  the more valuable scenarios you can run.
- Treat automation as production code: reviewed, tested, versioned, monitored, and owned
  by a named team.
- Alert when automation *does not* fire when expected, not only when it fails. Silent
  non-execution is the hardest failure to notice.

## A reasonable order of implementation

For a team starting from nothing:

1. Runbook links on every alert (one afternoon, immediate value)
2. Incident channel bootstrap (one day)
3. Automatic context gathering (a few days, highest value per hour spent)
4. Timeline capture and postmortem scaffolding (a few days)
5. Weekly alert noise report (an afternoon; drives the next six months of tuning)
6. Status page draft creation (a day)
7. Escalation rules (depends on the paging tool)
8. Auto-remediation for one specific, well-understood, rate-limited failure

Stop and evaluate after each. The first five deliver most of the available value, and none
of them can cause an outage.
