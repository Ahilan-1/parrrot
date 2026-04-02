"""
Parrrot — Calendar tools (iCal-based, works with Google/Outlook/Apple exported calendars)
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from parrrot.tools.registry import registry
from parrrot import config as cfg


def _parse_ical(path: str) -> list[dict]:
    """Parse an .ics file, return list of events."""
    try:
        # icalendar is optional
        import icalendar  # type: ignore[import]
        cal = icalendar.Calendar.from_ical(Path(path).read_bytes())
        events = []
        for component in cal.walk():
            if component.name == "VEVENT":
                dtstart = component.get("DTSTART")
                dtend = component.get("DTEND")
                events.append({
                    "title": str(component.get("SUMMARY", "(no title)")),
                    "start": str(dtstart.dt) if dtstart else "",
                    "end": str(dtend.dt) if dtend else "",
                    "description": str(component.get("DESCRIPTION", "")),
                    "location": str(component.get("LOCATION", "")),
                })
        return events
    except ImportError:
        return []


def _get_today_events(calendar_path: Optional[str] = None) -> str:
    conf = cfg.load()
    path = calendar_path or conf.get("calendar", {}).get("ical_path", "")
    if not path:
        return (
            "No calendar configured. Export your calendar as .ics and add to config:\n\n"
            "[calendar]\nical_path = '~/calendar.ics'"
        )
    events = _parse_ical(path)
    today = datetime.date.today().isoformat()
    today_events = [e for e in events if e["start"].startswith(today)]
    if not today_events:
        return f"No events today ({today})."
    lines = [f"Today's events ({today}):"]
    for e in today_events:
        lines.append(f"• {e['start'][11:16]} — {e['title']}{' @ ' + e['location'] if e['location'] else ''}")
    return "\n".join(lines)


def _get_upcoming_events(days: int = 7, calendar_path: Optional[str] = None) -> str:
    conf = cfg.load()
    path = calendar_path or conf.get("calendar", {}).get("ical_path", "")
    if not path:
        return "No calendar configured."
    events = _parse_ical(path)
    today = datetime.date.today()
    end = today + datetime.timedelta(days=days)
    upcoming = [
        e for e in events
        if e["start"][:10] >= today.isoformat() and e["start"][:10] <= end.isoformat()
    ]
    upcoming.sort(key=lambda x: x["start"])
    if not upcoming:
        return f"No events in the next {days} days."
    lines = [f"Events for next {days} days:"]
    for e in upcoming:
        lines.append(f"• {e['start'][:16]} — {e['title']}")
    return "\n".join(lines)


registry.register("get_today_events", "Get today's calendar events", {"calendar_path": "optional path to .ics file"})(_get_today_events)
registry.register("get_upcoming_events", "Get upcoming calendar events", {"days": "days ahead to look (default 7)", "calendar_path": "optional path to .ics file"})(_get_upcoming_events)
