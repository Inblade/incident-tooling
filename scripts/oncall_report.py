#!/usr/bin/env python3
"""Summarise alert volume per service from a local Prometheus/Alertmanager JSON export.

Turns a raw alert dump into the two tables an on-call handover actually needs: which
services generated the most alerts, and which individual alerts fired most often. The
second table is the one that finds the noise — a single alert accounting for 40% of a
rotation's pages is a tuning problem, not an on-call problem.

Design constraints, deliberately:
  * Standard library only.
  * Read-only and offline. Takes a file you exported; never queries an API. Alert
    payloads carry hostnames, customer identifiers and internal topology.
  * Deterministic output, so two runs over the same export diff cleanly.

Accepted input shapes (auto-detected):
  * Alertmanager /api/v2/alerts   -> a JSON array of alert objects
  * Alertmanager /api/v1/alerts   -> {"status": "success", "data": [...]}
  * Prometheus /api/v1/alerts     -> {"status": "success", "data": {"alerts": [...]}}
  * Prometheus /api/v1/query_range over ALERTS -> {"data": {"result": [...]}}
  * JSON Lines, one alert object per line

Usage:
    python3 oncall_report.py alerts.json
    python3 oncall_report.py alerts.json --group-by team --top 30
    python3 oncall_report.py alerts.json --severity critical --format json
    python3 oncall_report.py alerts.json --since 2026-07-25T00:00 --output handover.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

__version__: Final = "1.0.0"

# Label keys tried in order when deriving the service a given alert belongs to.
SERVICE_LABEL_CANDIDATES: Final[tuple[str, ...]] = (
    "service",
    "job",
    "app",
    "application",
    "namespace",
    "component",
    "instance",
)

SEVERITY_ORDER: Final[tuple[str, ...]] = ("critical", "warning", "info", "none", "unknown")


class ReportError(Exception):
    """Raised for input problems the user can fix."""


@dataclass(frozen=True, slots=True)
class Alert:
    """One alert occurrence, reduced to the fields the report needs."""

    name: str
    service: str
    severity: str
    starts_at: datetime | None
    ends_at: datetime | None
    labels: dict[str, str]

    @property
    def duration(self) -> timedelta | None:
        if self.starts_at is None or self.ends_at is None:
            return None
        delta = self.ends_at - self.starts_at
        return delta if delta.total_seconds() >= 0 else None


@dataclass(slots=True)
class ServiceSummary:
    """Aggregated counters for one grouping key."""

    key: str
    total: int = 0
    by_severity: Counter[str] = field(default_factory=Counter)
    alert_names: Counter[str] = field(default_factory=Counter)
    durations: list[timedelta] = field(default_factory=list)

    @property
    def distinct_alerts(self) -> int:
        return len(self.alert_names)

    @property
    def median_duration(self) -> timedelta | None:
        if not self.durations:
            return None
        ordered = sorted(self.durations)
        mid = len(ordered) // 2
        if len(ordered) % 2 == 1:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2

    @property
    def top_alert(self) -> tuple[str, int] | None:
        common = self.alert_names.most_common(1)
        return common[0] if common else None


def load_json(path: Path) -> Any:
    """Load JSON or JSON Lines from a local path."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReportError(f"cannot read {path}: {exc}") from exc

    if not raw.strip():
        raise ReportError(f"{path} is empty")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        records: list[Any] = []
        for lineno, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ReportError(
                    f"{path}:{lineno} is neither valid JSON nor valid JSON Lines: {exc}"
                ) from exc
        if not records:
            raise ReportError(f"{path} contains no JSON records")
        return records


def extract_raw_alerts(payload: Any) -> list[dict[str, Any]]:
    """Normalise the supported export shapes into a flat list of alert dicts."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        raise ReportError(f"unsupported top-level JSON type: {type(payload).__name__}")

    data = payload.get("data", payload)

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        # Prometheus /api/v1/alerts
        alerts = data.get("alerts")
        if isinstance(alerts, list):
            return [item for item in alerts if isinstance(item, dict)]

        # Prometheus range query over the ALERTS series: each result is one series with
        # a metric label set. Expand it to one record per sample so counts reflect how
        # long the alert was firing rather than how many series exist.
        result = data.get("result")
        if isinstance(result, list):
            expanded: list[dict[str, Any]] = []
            for series in result:
                if not isinstance(series, dict):
                    continue
                metric = series.get("metric")
                if not isinstance(metric, dict):
                    continue
                samples = series.get("values") or ([series["value"]] if "value" in series else [])
                if not isinstance(samples, list) or not samples:
                    expanded.append({"labels": metric})
                    continue
                for sample in samples:
                    if isinstance(sample, (list, tuple)) and sample:
                        expanded.append({"labels": metric, "startsAt": sample[0]})
                    else:
                        expanded.append({"labels": metric})
            return expanded

    # A single alert object.
    if "labels" in payload or "annotations" in payload:
        return [payload]

    raise ReportError(
        "could not find an alert array — expected an Alertmanager or Prometheus "
        "alerts export, or JSON Lines"
    )


def parse_time(value: Any) -> datetime | None:
    """Parse RFC-3339, ISO-8601, or epoch-seconds timestamps."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None

    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    # Alertmanager uses "0001-01-01T00:00:00Z" as the zero value for endsAt.
    if text.startswith("0001-01-01"):
        return None

    try:
        return datetime.fromtimestamp(float(text), tz=timezone.utc)
    except ValueError:
        pass

    # Trim sub-second precision beyond microseconds, which fromisoformat rejects
    # on some Python versions.
    normalised = text.replace("Z", "+00:00")
    if "." in normalised:
        head, _, tail = normalised.partition(".")
        digits = "".join(c for c in tail if c.isdigit())[:6]
        offset = tail[len(digits) :] if len(tail) > len(digits) else ""
        offset = "".join(c for c in offset if c in "+-:0123456789Z")
        normalised = f"{head}.{digits or '0'}{offset}"

    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def normalise(raw: dict[str, Any], service_labels: Sequence[str]) -> Alert | None:
    """Reduce one raw alert object to an Alert, or None if it is unusable."""
    labels_raw = raw.get("labels")
    labels: dict[str, str] = {}
    if isinstance(labels_raw, dict):
        labels = {str(k): str(v) for k, v in labels_raw.items()}

    name = labels.get("alertname") or str(raw.get("alertname") or "").strip()
    if not name:
        # Some exports put the name at the top level under a different key.
        for key in ("name", "alert"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                name = value.strip()
                break
    if not name:
        return None

    service = "unknown"
    for candidate in service_labels:
        value = labels.get(candidate)
        if value:
            service = value
            break

    severity = (labels.get("severity") or "unknown").lower()

    starts = parse_time(raw.get("startsAt") or raw.get("activeAt") or raw.get("startTime"))
    ends = parse_time(raw.get("endsAt") or raw.get("endTime"))

    return Alert(
        name=name,
        service=service,
        severity=severity,
        starts_at=starts,
        ends_at=ends,
        labels=labels,
    )


def group_key(alert: Alert, group_by: str, service_labels: Sequence[str]) -> str:
    if group_by == "service":
        return alert.service
    return alert.labels.get(group_by) or "unknown"


def summarise(
    alerts: Sequence[Alert],
    *,
    group_by: str,
    service_labels: Sequence[str],
) -> dict[str, ServiceSummary]:
    summaries: dict[str, ServiceSummary] = defaultdict(lambda: ServiceSummary(key=""))
    for alert in alerts:
        key = group_key(alert, group_by, service_labels)
        summary = summaries[key]
        summary.key = key
        summary.total += 1
        summary.by_severity[alert.severity] += 1
        summary.alert_names[alert.name] += 1
        duration = alert.duration
        if duration is not None:
            summary.durations.append(duration)
    return dict(summaries)


def humanise(delta: timedelta | None) -> str:
    if delta is None:
        return "-"
    total = int(delta.total_seconds())
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m"
    if total < 86400:
        return f"{total // 3600}h{(total % 3600) // 60:02d}m"
    return f"{total // 86400}d{(total % 86400) // 3600:02d}h"


def render_markdown(
    summaries: dict[str, ServiceSummary],
    alerts: Sequence[Alert],
    *,
    group_by: str,
    top: int,
    window: tuple[datetime | None, datetime | None],
) -> str:
    lines: list[str] = ["# On-call alert summary", ""]

    start, end = window
    if start or end:
        lines.append(
            f"Window: {start.isoformat() if start else 'start of data'}"
            f" to {end.isoformat() if end else 'end of data'}"
        )
        lines.append("")

    total = sum(s.total for s in summaries.values())
    severity_totals: Counter[str] = Counter()
    for summary in summaries.values():
        severity_totals.update(summary.by_severity)

    noun = group_by if len(summaries) == 1 else f"{group_by}s"
    lines.append(f"**{total} alerts** across **{len(summaries)}** {noun}.")
    if severity_totals:
        parts = [
            f"{severity_totals[sev]} {sev}"
            for sev in SEVERITY_ORDER
            if severity_totals.get(sev)
        ]
        extra = sorted(set(severity_totals) - set(SEVERITY_ORDER))
        parts.extend(f"{severity_totals[sev]} {sev}" for sev in extra)
        lines.append("Severity breakdown: " + ", ".join(parts) + ".")
    lines.extend(["", f"## By {group_by}", ""])

    lines.append(
        f"| {group_by.capitalize()} | Alerts | % | Critical | Warning | Distinct | "
        "Median duration | Top alert |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |")

    # Sort by volume, then name, so equal counts produce a stable diff.
    ranked = sorted(summaries.values(), key=lambda s: (-s.total, s.key))
    for summary in ranked[:top]:
        share = (summary.total / total * 100) if total else 0.0
        top_alert = summary.top_alert
        top_text = f"{top_alert[0]} ({top_alert[1]})" if top_alert else "-"
        lines.append(
            f"| {summary.key} | {summary.total} | {share:.1f}% | "
            f"{summary.by_severity.get('critical', 0)} | "
            f"{summary.by_severity.get('warning', 0)} | "
            f"{summary.distinct_alerts} | {humanise(summary.median_duration)} | "
            f"{top_text} |"
        )

    if len(ranked) > top:
        remainder = sum(s.total for s in ranked[top:])
        lines.append(f"| _({len(ranked) - top} more)_ | {remainder} | | | | | | |")

    # The noisiest individual alerts, which is where tuning effort pays off.
    lines.extend(["", "## Noisiest alerts", ""])
    lines.append("| Alert | Count | % of all | Severity | Services affected |")
    lines.append("| --- | ---: | ---: | --- | ---: |")

    per_alert: dict[str, Counter[str]] = defaultdict(Counter)
    alert_services: dict[str, set[str]] = defaultdict(set)
    alert_counts: Counter[str] = Counter()
    for alert in alerts:
        alert_counts[alert.name] += 1
        per_alert[alert.name][alert.severity] += 1
        alert_services[alert.name].add(alert.service)

    for name, count in sorted(alert_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]:
        share = (count / total * 100) if total else 0.0
        severities = ", ".join(
            f"{sev}:{n}" for sev, n in sorted(per_alert[name].items(), key=lambda kv: -kv[1])
        )
        lines.append(
            f"| {name} | {count} | {share:.1f}% | {severities} | "
            f"{len(alert_services[name])} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "Read the second table first. A single alert accounting for a large share of",
            "the total is a tuning problem — fix the threshold or the alert, and the",
            "rotation gets quieter without anyone working harder.",
            "",
        ]
    )
    return "\n".join(lines)


def render_json(summaries: dict[str, ServiceSummary], group_by: str) -> str:
    payload = {
        "group_by": group_by,
        "total": sum(s.total for s in summaries.values()),
        "groups": [
            {
                "key": s.key,
                "total": s.total,
                "by_severity": dict(s.by_severity),
                "distinct_alerts": s.distinct_alerts,
                "median_duration_seconds": (
                    int(s.median_duration.total_seconds())
                    if s.median_duration is not None
                    else None
                ),
                "alerts": dict(s.alert_names.most_common()),
            }
            for s in sorted(summaries.values(), key=lambda s: (-s.total, s.key))
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def parse_boundary(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = parse_time(value)
    if parsed is None:
        raise ReportError(f"cannot parse {value!r} as a timestamp (e.g. 2026-07-25T00:00)")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarise alert counts per service from a local alerts export.",
        epilog="Reads only local files and makes no network calls.",
    )
    parser.add_argument("export", type=Path, help="path to the JSON or JSONL alerts export")
    parser.add_argument(
        "--group-by",
        default="service",
        help="label to group by; 'service' tries several common labels (default: service)",
    )
    parser.add_argument(
        "--service-label",
        action="append",
        dest="service_labels",
        default=None,
        help=(
            "label to try when deriving the service, repeatable and order-sensitive "
            f"(default: {' '.join(SERVICE_LABEL_CANDIDATES)})"
        ),
    )
    parser.add_argument(
        "--severity",
        action="append",
        default=None,
        help="keep only these severities; repeatable",
    )
    parser.add_argument("--since", default=None, help="drop alerts starting before this time")
    parser.add_argument("--until", default=None, help="drop alerts starting after this time")
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        metavar="ALERTNAME",
        help="drop this alertname; repeatable (e.g. Watchdog)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="rows per table (default: 20)",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="output format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write to this path instead of stdout",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress the stderr summary")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        since = parse_boundary(args.since)
        until = parse_boundary(args.until)
        service_labels = tuple(args.service_labels or SERVICE_LABEL_CANDIDATES)
        severities = {s.lower() for s in args.severity} if args.severity else None
        excluded = {name for name in (args.exclude or [])}

        raw_alerts = extract_raw_alerts(load_json(args.export))

        alerts: list[Alert] = []
        dropped_unparsed = 0
        dropped_filtered = 0
        for raw in raw_alerts:
            alert = normalise(raw, service_labels)
            if alert is None:
                dropped_unparsed += 1
                continue
            if alert.name in excluded:
                dropped_filtered += 1
                continue
            if severities is not None and alert.severity not in severities:
                dropped_filtered += 1
                continue
            if alert.starts_at is not None:
                if since is not None and alert.starts_at < since:
                    dropped_filtered += 1
                    continue
                if until is not None and alert.starts_at > until:
                    dropped_filtered += 1
                    continue
            alerts.append(alert)

        if not alerts:
            print(
                "error: no alerts matched — check the filters and the export shape",
                file=sys.stderr,
            )
            return 1

        summaries = summarise(
            alerts, group_by=args.group_by, service_labels=service_labels
        )

        if args.format == "json":
            rendered = render_json(summaries, args.group_by)
        else:
            observed = [a.starts_at for a in alerts if a.starts_at is not None]
            window = (
                since or (min(observed) if observed else None),
                until or (max(observed) if observed else None),
            )
            rendered = render_markdown(
                summaries,
                alerts,
                group_by=args.group_by,
                top=max(1, args.top),
                window=window,
            )

    except ReportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output is not None:
        try:
            args.output.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write {args.output}: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(rendered)

    if not args.quiet:
        print(
            f"{len(raw_alerts)} records read; {len(alerts)} counted; "
            f"{dropped_filtered} filtered; {dropped_unparsed} unparsable",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
