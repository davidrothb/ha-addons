"""Opening hours, sampling slots and reading the collected CSV."""

import csv
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")
OPEN_MINUTE = 6 * 60
CLOSE_MINUTE = 22 * 60
INTERVAL_MINUTES = 10
SLOTS = list(range(OPEN_MINUTE, CLOSE_MINUTE + 1, INTERVAL_MINUTES))


def minute_of_day(when: datetime) -> int:
    return when.hour * 60 + when.minute


def slot_of(when: datetime) -> int:
    minute = minute_of_day(when)
    return minute - minute % INTERVAL_MINUTES


def is_open(when: datetime) -> bool:
    # Closing time itself counts, so the last sample is taken at 22:00.
    return OPEN_MINUTE <= minute_of_day(when) <= CLOSE_MINUTE


def clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def load(path: Path) -> tuple[dict, int]:
    """Return ({weekday: {date: {slot: count}}}, latest capacity)."""
    days = defaultdict(lambda: defaultdict(dict))
    capacity = 0
    if not path.exists():
        return days, capacity
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            when = datetime.fromisoformat(row["timestamp"])
            slot = slot_of(when)
            if OPEN_MINUTE <= slot <= CLOSE_MINUTE:
                days[when.weekday()][when.date()][slot] = int(row["count"])
                capacity = int(row["capacity"])
    return days, capacity


def average_by_slot(dates: dict, exclude: date | None = None) -> dict:
    """Mean count per slot over the given {date: {slot: count}}, optionally skipping one date."""
    by_slot = defaultdict(list)
    for day, values in dates.items():
        if day == exclude:
            continue
        for slot, count in values.items():
            by_slot[slot].append(count)
    return {slot: mean(counts) for slot, counts in by_slot.items()}
