# Tabletop Exercises and Game Days

## What a drill is for

A drill exists to find out what is **not true** about your incident response.

That framing matters, because the default drill does the opposite. Someone announces an
exercise a week ahead, picks a scenario the team has handled before, walks through the
runbook out loud, everyone agrees the runbook is good, and the exercise is recorded as a
success. Nothing was learned. The organisation now has slightly more confidence than it
did before, backed by no new evidence — which is a worse position than it started in.

A drill that finds nothing is either a drill that was too easy or a drill that nobody was
honest during. Both are failures of design, not proof of readiness.

The useful output of an exercise is a list of gaps with owners. If you finish and cannot
name three things that were harder than expected, run a harder scenario next time.

## The four kinds, and when each is worth it

| Kind | What happens | Cost | Finds |
|---|---|---|---|
| **Tabletop** | Discussion only, no systems touched | 60–90 min, 4–8 people | Decision gaps, unclear ownership, missing information paths |
| **Walkthrough** | Runbook executed against staging | Half a day | Stale commands, missing access, broken docs |
| **Game day** | Real failure injected in production, announced | 1 day + prep | Everything a tabletop finds, plus the gap between plan and reality |
| **Unannounced test** | Real failure, no warning | 1 day + high trust | Detection, paging, escalation — the parts a warned team fakes |

Start at the top and earn your way down. An organisation that cannot get a tabletop to
produce findings has no business injecting faults into production, and one that runs
unannounced tests without a working blameless culture will get one round of them before
people stop cooperating.

The progression is also a good maturity signal on its own. Teams that only ever do
tabletops are usually avoiding something they suspect is broken.

## Designing a scenario that finds gaps

### Pick the failure you have not had

The instinct is to drill the last incident. That is the one thing you have already fixed
and already discussed at length. Drill the *adjacent* failure instead: same system,
different mode.

Good sources of scenarios, in rough order of yield:

1. **Single points of failure nobody has named out loud.** The one database, the one
   engineer who understands billing, the one region.
2. **Dependencies you do not control.** Identity provider down, cloud provider control
   plane degraded (not the data plane — the control plane, so nothing can be changed),
   a payment processor returning success but not settling.
3. **Failures during the worst conditions.** Friday 18:00, half the team at a conference,
   the primary on-call unreachable, a release mid-flight.
4. **Partial and ambiguous failures.** Not "the database is down" — "the database is
   answering, slowly, for 30% of queries." Total failures are the easy case; teams handle
   them well. Ambiguity is where response falls apart.
5. **Failures of the response system itself.** Slack down, the paging provider degraded,
   the status page hosted in the region that is on fire, the runbook wiki behind the SSO
   that just failed.

Number 5 finds more real gaps than the other four combined and is the one most often
skipped, because it feels like cheating. It is not cheating. It happens.

### Make the scenario concrete

A scenario written as "there is a database problem" produces a discussion about databases.
A scenario written as a specific first signal at a specific time produces a response.

Write the opener as the participants would actually receive it:

> **02:14** — You are paged. `HighErrorRate` on `checkout-api`, firing 4 minutes.
> The dashboard shows 5xx at 22% and climbing. `checkout-api` latency p99 is 8s,
> normally 200ms. No deploys in the last 6 hours. The database dashboard looks
> normal. Your phone has one other notification: a customer support escalation
> from 20 minutes ago that nobody acknowledged.
>
> Go.

Everything after that comes from the participants asking questions, and the facilitator
answering as reality would.

### Plan the injects, not the answers

An inject is a new piece of information introduced at a chosen moment. Prepare five or six
and hold them; deliver them based on where the discussion goes, not on a fixed clock.

Injects that reliably produce learning:

- **The obvious hypothesis is wrong.** They suspect the deploy; there was no deploy.
- **A mitigation makes it worse.** The restart clears the connection pool and the thundering
  herd on reconnect takes down the replica too.
- **Someone important is unavailable.** The person who knows this system is on a plane.
- **The clock forces a decision.** "It has been 40 minutes. Support has 200 tickets and
  the CEO is asking in a DM whether to post publicly."
- **The mitigation requires access nobody in the room has.**
- **The second, unrelated thing.** Real incidents rarely arrive alone.

Do not script the resolution. If the team finds a path you did not anticipate, follow it —
that is the exercise working. The facilitator's job is to keep reality consistent, not to
steer toward a predetermined ending.

## Running it

### Roles

- **Facilitator** — presents the scenario, delivers injects, plays every external party
  (the cloud provider, support, the executive asking questions). Should know the systems
  well enough to answer "what does the dashboard show?" plausibly and instantly.
- **Participants** — the people who would actually respond. Not a hand-picked A-team; the
  point is to test the rotation you have, including whoever is new.
- **Scribe** — keeps a timeline of what was decided, when, and what was asked for but not
  available. This record is the exercise's product; without it the findings evaporate by
  the following week.
- **Observers** — welcome, silent. Adjacent teams learn a lot watching, and they
  contaminate the exercise the moment they start helping.

### Facilitation rules that matter

**Answer only what is asked.** If nobody checks the deploy log, do not mention the deploy
log. The gap between "the information was available" and "the responder went and got it"
is exactly what you are measuring.

**Make them say the command.** "I'd check the database" is not a response. "I'd run
`SELECT * FROM pg_stat_activity WHERE state = 'active'` on the primary" is. Vagueness in
a tabletop becomes fumbling at 02:00.

**Track access, not just knowledge.** Every time someone proposes an action, ask whether
they personally can perform it right now. The most common finding in a first tabletop is
that the plan depends on permissions half the rotation does not have.

**Let them fail.** The pull toward rescuing a struggling team is strong and must be
resisted. A team that flounders for fifteen minutes because the runbook link is dead has
produced the single most valuable finding of the session.

**Stop on time.** 90 minutes is the ceiling for a tabletop. Attention collapses after that
and the last half hour teaches nothing.

### What to observe

Keep the assessment behavioural, not scored. Grades invite performance; the goal is
honesty. Watch for:

- How long until someone explicitly took the incident commander role
- How long until a hypothesis was stated out loud rather than assumed
- Whether anyone communicated to customers or business stakeholders unprompted
- What information was wanted and could not be obtained
- What actions were proposed and blocked by access
- Whether the runbook was opened at all, and whether it helped
- Whether anyone said "I don't know" comfortably — a room where nobody does is a room
  where people are guessing confidently

## After: the part that determines whether it was worth doing

Run a debrief immediately, 20 minutes, while it is fresh. Three questions:

1. What surprised you?
2. What did you want and not have?
3. What would you have done differently with unlimited time?

Then write the findings up **within two days**, in the same format as a postmortem action
list — because that is what it is. Every finding gets an owner, a due date, and a place in
the normal backlog. A finding without an owner is a note, and notes do not fix anything.

A short report template:

```markdown
# Exercise: <scenario name> — <date>

**Type:** tabletop / walkthrough / game day
**Participants:** roles, not names
**Scenario summary:** two sentences
**Duration:** planned vs actual

## Timeline
| Time | Event / inject | Team response |
|---|---|---|

## Findings
| # | Finding | Severity | Owner | Due |
|---|---|---|---|---|

## What worked
Worth recording explicitly — it is the part that gets cut when priorities shift,
and next quarter someone will ask why it was there.

## Follow-up exercise
What to drill next, based on what this one exposed.
```

Two weeks later, check the findings. Exercises that never produce closed actions stop
being taken seriously by participants, and the second one is noticeably worse attended
than the first.

## Cadence

- **Tabletop:** quarterly per team, and once for every genuinely new system
- **Runbook walkthrough:** whenever a runbook is written or substantially changed, plus
  an annual pass over all of them — untested runbooks decay silently
- **Game day:** twice a year, tied to something real (a region migration, a dependency
  upgrade, peak-season readiness)
- **Failover test:** on the schedule the RTO promises. A failover path that has not been
  exercised in a year is a hypothesis, not a capability, and the number in the DR document
  is fiction
- **Onboarding drill:** every new on-call engineer runs one scenario before their first
  shift. This is the highest-yield drill in the list and the cheapest

## Anti-patterns

**The scripted success.** Scenario shared in advance, runbook rehearsed, nothing goes
wrong. It is theatre for an auditor, and everyone in the room knows it.

**The gotcha.** A scenario designed to embarrass someone, or to prove a point the
facilitator already wanted to make. One of these poisons the next five exercises.

**Only the experts.** Drilling with the three people who know everything measures those
three people. The rotation is what responds at 02:00.

**No follow-through.** Findings recorded in a doc nobody opens again. This is the most
common failure mode and it is fatal — it converts the exercise into a tax.

**Chaos without hypothesis.** Injecting a failure to see what happens is entertainment.
Injecting a failure to test a specific stated expectation — "we believe the replica is
promoted automatically within 60 seconds" — is engineering. Write the expectation down
before you run it, so the result can contradict you.

**Skipping the boring drill.** Restoring a backup is not an interesting exercise. It is
also the one that most often reveals that the thing you have been backing up for two years
cannot be restored.

## A worked scenario

Useful as a first tabletop for most teams running anything on Kubernetes with a managed
database behind it. Nothing here requires deep familiarity with a specific stack.

**Title:** Partial degradation with an unavailable expert

**Opening (02:14):** as written in the section above.

**Reality behind the scenario (facilitator only):** a certificate used for mTLS between
`checkout-api` and the payment provider expired 14 minutes ago. Connections fail, the
client retries with a 30-second timeout, connection slots exhaust, and the symptom
presents as generalised latency and errors with no deploy correlation. The support
escalation 20 minutes earlier was the first customer noticing failed payments.

**Injects, held in reserve:**

1. *(after ~10 min, or once they suspect the database)* The database team confirms the
   database is healthy. Connection count from `checkout-api` is at its configured maximum.
2. *(when they consider a restart)* Restarting the pods clears errors for 90 seconds, then
   the same pattern returns — worse, because the retry backlog reconnects at once.
3. *(after ~20 min)* Support reports 140 tickets. The status page has nothing on it. A
   product lead asks in a DM whether this is affecting all customers or some.
4. *(if they find the certificate)* Rotating it requires access to the secrets store that
   only the platform team has, and the platform on-call is not answering.
5. *(if they are moving fast and have handled 1–4)* The monitoring for certificate expiry
   exists. It fired 30 days ago into a channel that was archived in a reorganisation.

**Findings this scenario typically produces:** no alert on certificate expiry reaching a
live channel; no dashboard showing connection pool saturation next to error rate; customer
communication starting far too late; a mitigation requiring access held by one team with
no documented escalation path; and, in almost every run, the observation that nobody
declared themselves incident commander for the first ten minutes.

Inject 5 is the one worth designing into your own scenarios. The most uncomfortable
finding in incident response is rarely "we did not have monitoring" — it is "we had the
monitoring, and it told us, and the signal went nowhere."
