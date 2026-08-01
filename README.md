# Incident Tooling

Reference material and small, dependency-light tools for the operational side of incident
response: what to publish on a status page and when, customer communication templates,
scripts that turn raw exports into the artifacts a postmortem needs, an honest view of
what to automate first, and how to run drills that find real gaps.

Distilled from running and reviewing incidents in production environments. The templates
and scripts are generic by design — no employer names, no internal systems, nothing that
assumes a particular vendor stack.

## Contents

```
.
├── docs
│   ├── status-page-strategy.md      # what to publish, when, in whose words
│   ├── automation-opportunities.md  # what to automate first, what never to
│   └── tabletop-exercises.md        # running incident drills that find real gaps
├── templates
│   └── customer-comms.md            # initial / update / resolved, with tone guidance
├── scripts
│   ├── incident_timeline.py         # Slack/JSON export -> postmortem timeline table
│   └── oncall_report.py             # alerts export -> per-service summary table
├── LICENSE
└── README.md
```

## Scripts

Python 3.11+, standard library only, no network calls, read-only. Both are deliberately
offline: incident channels and alert payloads carry customer identifiers, internal
hostnames, and occasionally credentials pasted in a hurry. A tool that transmits any of
that is a tool nobody should run.

### `incident_timeline.py`

Turns a Slack channel export into a Markdown timeline for the postmortem document.

```bash
# Basic run.
python3 scripts/incident_timeline.py export.json

# Resolve user IDs, render in local time, add an elapsed-since-T0 column.
python3 scripts/incident_timeline.py export.json \
  --users users.json --tz Europe/Kyiv --relative-to first

# Keep only messages tagged with a marker (!detected, !impact, !action, ...).
python3 scripts/incident_timeline.py export.json --only-tagged

# Include bot messages (alerts, deploy notifications) and bound the window.
python3 scripts/incident_timeline.py export.json \
  --include-bots --start 2026-08-01T09:00 --end 2026-08-01T12:00 \
  --output timeline.md
```

Accepts a Slack workspace export, a `conversations.history` API response, or JSON Lines.
Reports what it skipped to stderr so silent drops are visible.

The `--only-tagged` mode pays off if the team adopts a convention of prefixing significant
messages during the incident (`!detected`, `!impact`, `!action`, `!mitigated`). Doing that
costs nothing at the time and produces a clean timeline afterwards, when reconstructing
one from 400 messages is the tedious part of writing the postmortem.

### `oncall_report.py`

Summarises alert volume per service from a Prometheus or Alertmanager JSON export, for
on-call handovers and noise reviews.

```bash
python3 scripts/oncall_report.py alerts.json --exclude Watchdog

# Group by team instead of service, over a specific window.
python3 scripts/oncall_report.py alerts.json \
  --group-by team --since 2026-07-25T00:00 --top 30

# Machine-readable, for tracking noise over time.
python3 scripts/oncall_report.py alerts.json --format json --quiet > week.json
```

Accepts Alertmanager `/api/v2/alerts`, Prometheus `/api/v1/alerts`, a range query over the
`ALERTS` series, or JSON Lines. Output is deterministic so successive weeks diff cleanly.

The second table — noisiest individual alerts — is the one that matters. A single alert
producing a large share of a rotation's pages is a tuning problem, and fixing it makes the
rotation quieter without anyone working harder.

## Docs

- **`docs/status-page-strategy.md`** — the public communication decisions, made before you
  need them: what qualifies as an incident worth posting, who writes, what goes in and
  what stays out.
- **`templates/customer-comms.md`** — fill-in templates for the initial post, updates, and
  resolution, with notes on why each phrasing choice is made.
- **`docs/automation-opportunities.md`** — a ranked view of what to automate in incident
  response, and a shorter list of what to leave to humans.
- **`docs/tabletop-exercises.md`** — how to run drills that surface real gaps rather than
  confirming that the runbook exists.

## License

MIT — see [LICENSE](LICENSE).
