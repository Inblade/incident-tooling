#!/usr/bin/env python3
"""Build a postmortem timeline table from a local Slack channel export.

Reads a JSON export of an incident channel and emits a Markdown timeline suitable for
pasting into a postmortem document. Optionally emits JSON for further processing.

Design constraints, deliberately:
  * Standard library only. Runs anywhere Python 3.11 is available, including a locked-down
    jump host during an incident.
  * No network calls. The input is a file you already have. Incident channels routinely
    contain customer names, credentials pasted in a panic, and internal hostnames — this
    tool must never transmit any of it.
  * Read-only. Nothing is written except to stdout or an explicit --output path.

Accepted input shapes (auto-detected):
  * Slack workspace export: a JSON array of message objects, as produced per-day by
    Slack's export, or a concatenation of those arrays.
  * conversations.history API response: an object with a "messages" key.
  * A JSON Lines file with one message object per line.

Usage:
    python3 incident_timeline.py export.json
    python3 incident_timeline.py export.json --tz Europe/Kyiv --start 2026-08-01T09:00
    python3 incident_timeline.py export.json --users users.json --format json
    python3 incident_timeline.py export.json --only-tagged --relative-to first
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

__version__: Final = "1.0.0"

# Messages carrying one of these markers are treated as timeline-worthy. Teams that adopt
# a convention of prefixing significant messages ("!detected", "!action", "!impact") get a
# clean timeline for free; without the convention, use --all to include everything.
DEFAULT_MARKERS: Final[tuple[str, ...]] = (
    "!detected",
    "!impact",
    "!action",
    "!finding",
    "!mitigated",
    "!resolved",
    "!decision",
)

# Slack decorations to strip so the table stays readable.
_USER_MENTION: Final = re.compile(r"<@([A-Z0-9]+)(?:\|([^>]+))?>")
_CHANNEL_MENTION: Final = re.compile(r"<#[A-Z0-9]+\|([^>]+)>")
_LINK_WITH_LABEL: Final = re.compile(r"<(https?://[^|>]+)\|([^>]+)>")
_BARE_LINK: Final = re.compile(r"<(https?://[^>]+)>")
_SPECIAL_MENTION: Final = re.compile(r"<!(here|channel|everyone)>")
_WHITESPACE: Final = re.compile(r"\s+")

# Subtypes that are channel noise rather than incident content.
_SKIP_SUBTYPES: Final[frozenset[str]] = frozenset(
    {
        "channel_join",
        "channel_leave",
        "channel_topic",
        "channel_purpose",
        "channel_name",
        "channel_archive",
        "channel_unarchive",
        "bot_add",
        "bot_remove",
        "pinned_item",
        "unpinned_item",
    }
)


class TimelineError(Exception):
    """Raised for input problems that the user can fix."""


@dataclass(frozen=True, slots=True)
class Entry:
    """One timeline row."""

    timestamp: datetime
    author: str
    text: str
    markers: tuple[str, ...] = ()
    thread_parent: str | None = None
    is_bot: bool = False

    def offset_from(self, origin: datetime) -> str:
        """Format the elapsed time since `origin` as +HH:MM."""
        delta: timedelta = self.timestamp - origin
        total_seconds = int(delta.total_seconds())
        sign = "-" if total_seconds < 0 else "+"
        total_seconds = abs(total_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        return f"{sign}{hours:02d}:{minutes:02d}"


@dataclass(slots=True)
class ParseStats:
    """Counters reported to stderr so silent drops are visible."""

    seen: int = 0
    skipped_subtype: int = 0
    skipped_no_text: int = 0
    skipped_bad_ts: int = 0
    skipped_window: int = 0
    skipped_untagged: int = 0
    kept: int = 0
    unresolved_users: set[str] = field(default_factory=set)

    def report(self) -> str:
        parts = [
            f"{self.seen} messages read",
            f"{self.kept} kept",
        ]
        for label, value in (
            ("subtype", self.skipped_subtype),
            ("empty", self.skipped_no_text),
            ("bad timestamp", self.skipped_bad_ts),
            ("outside window", self.skipped_window),
            ("untagged", self.skipped_untagged),
        ):
            if value:
                parts.append(f"{value} skipped ({label})")
        if self.unresolved_users:
            parts.append(f"{len(self.unresolved_users)} unresolved user IDs")
        return "; ".join(parts)


def load_json(path: Path) -> Any:
    """Load JSON or JSON Lines from a local path."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TimelineError(f"cannot read {path}: {exc}") from exc

    stripped = raw.lstrip()
    if not stripped:
        raise TimelineError(f"{path} is empty")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fall back to JSON Lines before giving up.
        records: list[Any] = []
        for lineno, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise TimelineError(
                    f"{path}:{lineno} is neither valid JSON nor valid JSON Lines: {exc}"
                ) from exc
        if not records:
            raise TimelineError(f"{path} contains no JSON records")
        return records


def extract_messages(payload: Any) -> list[dict[str, Any]]:
    """Normalise the supported input shapes into a flat list of message dicts."""
    if isinstance(payload, dict):
        for key in ("messages", "events"):
            value = payload.get(key)
            if isinstance(value, list):
                return [m for m in value if isinstance(m, dict)]
        raise TimelineError(
            "object input has no 'messages' array — expected a Slack "
            "conversations.history response or a message array"
        )

    if isinstance(payload, list):
        messages: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                # A concatenation of per-day export files nests arrays one level deeper.
                if "messages" in item and isinstance(item["messages"], list):
                    messages.extend(m for m in item["messages"] if isinstance(m, dict))
                else:
                    messages.append(item)
        return messages

    raise TimelineError(f"unsupported top-level JSON type: {type(payload).__name__}")


def load_user_map(path: Path | None) -> dict[str, str]:
    """Build a user-ID to display-name map from a Slack users.json export."""
    if path is None:
        return {}

    payload = load_json(path)
    users = payload.get("members") if isinstance(payload, dict) else payload
    if not isinstance(users, list):
        raise TimelineError(f"{path} does not look like a Slack users export")

    mapping: dict[str, str] = {}
    for user in users:
        if not isinstance(user, dict):
            continue
        uid = user.get("id")
        if not isinstance(uid, str):
            continue
        profile = user.get("profile") if isinstance(user.get("profile"), dict) else {}
        name = (
            profile.get("display_name")
            or profile.get("real_name")
            or user.get("real_name")
            or user.get("name")
            or uid
        )
        mapping[uid] = str(name)
    return mapping


def clean_text(text: str, users: dict[str, str]) -> str:
    """Strip Slack markup and collapse the message onto a single line."""
    text = _LINK_WITH_LABEL.sub(r"\2", text)
    text = _BARE_LINK.sub(r"\1", text)
    text = _CHANNEL_MENTION.sub(r"#\1", text)
    text = _SPECIAL_MENTION.sub(r"@\1", text)

    def _user(match: re.Match[str]) -> str:
        uid, inline_name = match.group(1), match.group(2)
        return "@" + (inline_name or users.get(uid, uid))

    text = _USER_MENTION.sub(_user, text)

    # Unescape the three entities Slack encodes.
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

    # Code fences and pipes would break the Markdown table.
    text = text.replace("```", " ").replace("|", "\\|")
    return _WHITESPACE.sub(" ", text).strip()


def message_text(message: dict[str, Any]) -> str:
    """Recover text from a message, including bot messages that use attachments/blocks."""
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return text

    # Alertmanager and similar bots put the useful content in attachments.
    fragments: list[str] = []
    attachments = message.get("attachments")
    if isinstance(attachments, list):
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            for key in ("title", "text", "fallback", "pretext"):
                value = attachment.get(key)
                if isinstance(value, str) and value.strip():
                    fragments.append(value.strip())
                    break

    blocks = message.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_text = block.get("text")
            if isinstance(block_text, dict):
                value = block_text.get("text")
                if isinstance(value, str) and value.strip():
                    fragments.append(value.strip())

    return " ".join(fragments)


def author_name(message: dict[str, Any], users: dict[str, str], stats: ParseStats) -> str:
    """Best available human-readable author for a message."""
    profile = message.get("user_profile")
    if isinstance(profile, dict):
        for key in ("display_name", "real_name", "name"):
            value = profile.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    uid = message.get("user")
    if isinstance(uid, str):
        if uid in users:
            return users[uid]
        stats.unresolved_users.add(uid)
        return uid

    for key in ("username", "bot_id"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return "unknown"


def parse_ts(value: Any, tz: timezone | ZoneInfo) -> datetime | None:
    """Parse a Slack `ts` (epoch seconds with microsecond suffix) or an ISO-8601 string."""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(tz)

    if not isinstance(value, str) or not value:
        return None

    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(tz)
    except (ValueError, OverflowError, OSError):
        pass

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(tz)


def find_markers(text: str, markers: Sequence[str]) -> tuple[str, ...]:
    lowered = text.lower()
    return tuple(m for m in markers if m.lower() in lowered)


def build_entries(
    messages: list[dict[str, Any]],
    *,
    users: dict[str, str],
    tz: timezone | ZoneInfo,
    markers: Sequence[str],
    only_tagged: bool,
    include_bots: bool,
    start: datetime | None,
    end: datetime | None,
    stats: ParseStats,
) -> list[Entry]:
    entries: list[Entry] = []

    for message in messages:
        stats.seen += 1

        subtype = message.get("subtype")
        if isinstance(subtype, str) and subtype in _SKIP_SUBTYPES:
            stats.skipped_subtype += 1
            continue

        is_bot = bool(message.get("bot_id")) or subtype == "bot_message"
        if is_bot and not include_bots:
            stats.skipped_subtype += 1
            continue

        raw_text = message_text(message)
        if not raw_text.strip():
            stats.skipped_no_text += 1
            continue

        when = parse_ts(message.get("ts") or message.get("timestamp"), tz)
        if when is None:
            stats.skipped_bad_ts += 1
            continue

        if (start is not None and when < start) or (end is not None and when > end):
            stats.skipped_window += 1
            continue

        found = find_markers(raw_text, markers)
        if only_tagged and not found:
            stats.skipped_untagged += 1
            continue

        thread_ts = message.get("thread_ts")
        parent = (
            str(thread_ts)
            if isinstance(thread_ts, str) and thread_ts != message.get("ts")
            else None
        )

        entries.append(
            Entry(
                timestamp=when,
                author=author_name(message, users, stats),
                text=clean_text(raw_text, users),
                markers=found,
                thread_parent=parent,
                is_bot=is_bot,
            )
        )
        stats.kept += 1

    entries.sort(key=lambda e: e.timestamp)
    return entries


def render_markdown(
    entries: Sequence[Entry],
    *,
    relative_to: datetime | None,
    truncate: int,
) -> str:
    if not entries:
        return "_No timeline entries matched the given filters._\n"

    lines: list[str] = []
    if relative_to is not None:
        lines.append(f"T0 = {relative_to.isoformat()}\n")
        lines.append("| Time | Elapsed | Who | What |")
        lines.append("| --- | --- | --- | --- |")
    else:
        lines.append("| Time | Who | What |")
        lines.append("| --- | --- | --- |")

    for entry in entries:
        text = entry.text
        if truncate and len(text) > truncate:
            text = text[: truncate - 1].rstrip() + "…"
        if entry.markers:
            # Strip the marker tokens from the body — they are rendered as tags instead.
            for marker in entry.markers:
                text = re.sub(re.escape(marker), "", text, flags=re.IGNORECASE)
            text = _WHITESPACE.sub(" ", text).strip()
            tags = " ".join(f"**{m.lstrip('!').upper()}**" for m in entry.markers)
            text = f"{tags} {text}"
        clock = entry.timestamp.strftime("%H:%M:%S")
        if relative_to is not None:
            lines.append(
                f"| {clock} | {entry.offset_from(relative_to)} | {entry.author} | {text} |"
            )
        else:
            lines.append(f"| {clock} | {entry.author} | {text} |")

    return "\n".join(lines) + "\n"


def render_json(entries: Sequence[Entry]) -> str:
    payload = [
        {
            "timestamp": e.timestamp.isoformat(),
            "author": e.author,
            "text": e.text,
            "markers": list(e.markers),
            "thread_parent": e.thread_parent,
            "is_bot": e.is_bot,
        }
        for e in entries
    ]
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def resolve_tz(name: str) -> timezone | ZoneInfo:
    if name.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise TimelineError(f"unknown timezone {name!r}") from exc


def parse_boundary(value: str | None, tz: timezone | ZoneInfo) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TimelineError(
            f"cannot parse {value!r} as ISO-8601 (e.g. 2026-08-01T09:00)"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a postmortem timeline from a local Slack/JSON export.",
        epilog="Reads only local files and makes no network calls.",
    )
    parser.add_argument("export", type=Path, help="path to the JSON or JSONL export")
    parser.add_argument(
        "--users",
        type=Path,
        default=None,
        help="Slack users.json export, to resolve user IDs to names",
    )
    parser.add_argument(
        "--tz",
        default="UTC",
        help="IANA timezone for rendered times (default: UTC)",
    )
    parser.add_argument("--start", default=None, help="drop entries before this ISO-8601 time")
    parser.add_argument("--end", default=None, help="drop entries after this ISO-8601 time")
    parser.add_argument(
        "--marker",
        action="append",
        dest="markers",
        default=None,
        help=f"marker token to highlight; repeatable (default: {' '.join(DEFAULT_MARKERS)})",
    )
    parser.add_argument(
        "--only-tagged",
        action="store_true",
        help="keep only messages containing a marker",
    )
    parser.add_argument(
        "--include-bots",
        action="store_true",
        help="include bot messages (alerts, deploy notifications)",
    )
    parser.add_argument(
        "--relative-to",
        default=None,
        metavar="WHEN",
        help="add an elapsed column relative to 'first' or an ISO-8601 time",
    )
    parser.add_argument(
        "--truncate",
        type=int,
        default=200,
        metavar="N",
        help="truncate message text to N characters, 0 to disable (default: 200)",
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
        tz = resolve_tz(args.tz)
        start = parse_boundary(args.start, tz)
        end = parse_boundary(args.end, tz)
        users = load_user_map(args.users)
        messages = extract_messages(load_json(args.export))

        stats = ParseStats()
        entries = build_entries(
            messages,
            users=users,
            tz=tz,
            markers=tuple(args.markers) if args.markers else DEFAULT_MARKERS,
            only_tagged=args.only_tagged,
            include_bots=args.include_bots,
            start=start,
            end=end,
            stats=stats,
        )

        origin: datetime | None = None
        if args.relative_to == "first":
            origin = entries[0].timestamp if entries else None
        elif args.relative_to is not None:
            origin = parse_boundary(args.relative_to, tz)

        if args.format == "json":
            rendered = render_json(entries)
        else:
            rendered = render_markdown(
                entries, relative_to=origin, truncate=max(0, args.truncate)
            )

    except TimelineError as exc:
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
        print(stats.report(), file=sys.stderr)
        if stats.unresolved_users:
            sample = ", ".join(sorted(stats.unresolved_users)[:5])
            print(
                f"hint: pass --users to resolve IDs such as {sample}",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
