"""Publish gym sensors to Home Assistant through the Supervisor REST API.

States set this way are not stored in the entity registry, so they disappear
when Home Assistant restarts; the poller re-publishes them every few minutes.
"""

import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from history import CLOSE_MINUTE, INTERVAL_MINUTES, OPEN_MINUTE, TZ, average_by_slot, clock, is_open, load, slot_of

API = "http://supervisor/core/api"
PREFIX = "wsjjsc_gym"
DEVICE_ATTRS = {"attribution": "Data z wsjjsc.com.tw"}
# The quietest time to *start* a workout: skip the opening moment (the counter
# starts at 0) and the last hour, when everyone is leaving.
QUIET_FIRST = OPEN_MINUTE + INTERVAL_MINUTES
QUIET_LAST = CLOSE_MINUTE - 60


def enabled() -> bool:
    """True inside the add-on, where the Supervisor provides a token."""
    return bool(os.environ.get("SUPERVISOR_TOKEN"))


def set_state(entity_id: str, state, attributes: dict) -> None:
    body = json.dumps({
        "state": "unknown" if state is None else str(state),
        "attributes": {**DEVICE_ATTRS, **attributes},
    }).encode()
    request = urllib.request.Request(
        f"{API}/states/{entity_id}",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['SUPERVISOR_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=10):
        pass


def last_row(path: Path) -> dict | None:
    if not path.exists():
        return None
    row = None
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            pass
    return row


def quietest(average: dict, from_slot: int) -> tuple[int, float] | None:
    """(slot, mean count) of the emptiest slot from from_slot on, within QUIET_FIRST..QUIET_LAST."""
    remaining = {
        s: c for s, c in average.items() if max(from_slot, QUIET_FIRST) <= s <= QUIET_LAST
    }
    if not remaining:
        return None
    slot = min(remaining, key=remaining.get)
    return slot, remaining[slot]


def publish(csv_path: Path, now: datetime | None = None) -> None:
    """Compute every sensor from the CSV and push it to Home Assistant."""
    now = now or datetime.now(TZ)
    open_now = is_open(now)
    days, _ = load(csv_path)

    row = last_row(csv_path)
    count = capacity = last_sample = None
    if row:
        sampled = datetime.fromisoformat(row["timestamp"])
        last_sample = sampled.isoformat()
        capacity = int(row["capacity"])
        # A sample from today's opening hours is current; outside them the gym is empty.
        if open_now and sampled.date() == now.date() and now - sampled < timedelta(minutes=30):
            count = int(row["count"])
    if not open_now:
        count = 0
    percent = round(100 * count / capacity) if count is not None and capacity else None

    # Typical numbers come from earlier days of the same weekday, never from today.
    typical_today = average_by_slot(days.get(now.weekday(), {}), exclude=now.date())
    typical_now = typical_today.get(slot_of(now)) if open_now else None

    # Before closing: quietest slot for the rest of today; after closing: for tomorrow.
    if slot_of(now) <= CLOSE_MINUTE:
        quiet_day, quiet_average, from_slot = "dnes", typical_today, slot_of(now)
    else:
        tomorrow = now + timedelta(days=1)
        quiet_day, from_slot = "zítra", QUIET_FIRST
        quiet_average = average_by_slot(days.get(tomorrow.weekday(), {}))
    quiet = quietest(quiet_average, from_slot)

    common = {"last_sample": last_sample}
    states = [
        ("binary_sensor", "open", "on" if open_now else "off", {
            "friendly_name": "Posilovna otevřeno",
            "icon": "mdi:door-open" if open_now else "mdi:door-closed",
            "opens": clock(OPEN_MINUTE),
            "closes": clock(CLOSE_MINUTE),
        }),
        ("sensor", "occupancy", count, {
            "friendly_name": "Posilovna obsazenost",
            "icon": "mdi:weight-lifter",
            "unit_of_measurement": "osob",
            "state_class": "measurement",
            "capacity": capacity,
            **common,
        }),
        ("sensor", "occupancy_percent", percent, {
            "friendly_name": "Posilovna obsazenost %",
            "icon": "mdi:percent",
            "unit_of_measurement": "%",
            "state_class": "measurement",
            **common,
        }),
        ("sensor", "typical", None if typical_now is None else round(typical_now), {
            "friendly_name": "Posilovna obvykle touto dobou",
            "icon": "mdi:chart-bell-curve",
            "unit_of_measurement": "osob",
            "difference": None if typical_now is None or count is None else round(count - typical_now),
        }),
        ("sensor", "quietest_time", clock(quiet[0]) if quiet else None, {
            "friendly_name": "Posilovna nejvolněji",
            "icon": "mdi:clock-check-outline",
            "day": quiet_day,
            "expected": round(quiet[1]) if quiet else None,
        }),
    ]
    errors = []
    for domain, key, state, attributes in states:
        try:
            set_state(f"{domain}.{PREFIX}_{key}", state, attributes)
        except Exception as e:
            errors.append(f"{key}: {e}")
    if errors:
        print(f"{now:%Y-%m-%d %H:%M} Home Assistant update failed: {'; '.join(errors)}",
              file=sys.stderr, flush=True)
