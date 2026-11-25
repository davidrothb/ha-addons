#!/usr/bin/env python3
"""Every 10 minutes during opening hours, append the gym head count to a CSV.

Inside the Home Assistant add-on it also publishes sensors after every sample
and, with --plot-out, redraws the weekly chart once a day after closing time.
"""

import argparse
import csv
import re
import signal
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import ha
from history import CLOSE_MINUTE, TZ, is_open, minute_of_day, slot_of

URL = "https://wsjjsc.com.tw/"
USER_AGENT = "wsjjsc-tracker/1.0"
CHECK_EVERY_SECONDS = 20
# States pushed through the REST API vanish when Home Assistant restarts.
REPUBLISH_EVERY_SECONDS = 5 * 60
# Worst case (every attempt hits the 30 s timeout) is ~4 minutes, well inside one slot.
MAX_ATTEMPTS = 5
RETRY_DELAYS_SECONDS = [10, 20, 30, 30]
DEFAULT_CSV = Path(__file__).parent / "data" / "gym_occupancy.csv"

# The page renders the counter in two layouts:
#   健身房<div class="notice">80</div>人/160人
#   健身房<div class="notice">80</div>人 <span>容留160人</span>
COUNTER = re.compile(
    r'健身房\s*<div class="notice">\s*(\d+)\s*</div>\s*人\s*(?:<span>\s*容留|/)\s*(\d+)\s*人'
)


class CounterNotFound(ValueError):
    def __init__(self, status: int, final_url: str, html: str):
        self.html = html
        title = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        title = title[1].strip()[:100] if title else "-"
        super().__init__(
            f"gym counter not found in page (HTTP {status}, {final_url}, "
            f"{len(html)} chars, title: {title!r})"
        )


def fetch_counts() -> tuple[int, int]:
    """Return (people in the gym, capacity)."""
    request = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")
        status, final_url = response.status, response.url
    match = COUNTER.search(html)
    if match is None:
        raise CounterNotFound(status, final_url, html)
    return int(match[1]), int(match[2])


def save_failed_page(csv_path: Path, html: str) -> Path:
    """Keep the page that did not parse next to the CSV, for debugging."""
    out = csv_path.with_name("last_failed_page.html")
    out.write_text(html, encoding="utf-8")
    return out


def append_row(path: Path, when: datetime, count: int, capacity: int) -> None:
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "count", "capacity"])
        writer.writerow([when.isoformat(timespec="seconds"), count, capacity])


def poll_once(path: Path) -> None:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        now = datetime.now(TZ)
        try:
            count, capacity = fetch_counts()
        except Exception as e:  # keep running through network errors and page changes
            if isinstance(e, CounterNotFound):
                try:
                    saved = save_failed_page(path, e.html)
                    print(f"{now:%Y-%m-%d %H:%M} saved page to {saved}", file=sys.stderr, flush=True)
                except OSError:
                    pass
            if attempt == MAX_ATTEMPTS:
                print(f"{now:%Y-%m-%d %H:%M} ERROR: {e} (gave up after {attempt} attempts)",
                      file=sys.stderr, flush=True)
                return
            delay = RETRY_DELAYS_SECONDS[min(attempt, len(RETRY_DELAYS_SECONDS)) - 1]
            print(f"{now:%Y-%m-%d %H:%M} attempt {attempt}/{MAX_ATTEMPTS} failed: {e}; "
                  f"retrying in {delay}s", file=sys.stderr, flush=True)
            time.sleep(delay)
            continue
        append_row(path, now, count, capacity)
        print(f"{now:%Y-%m-%d %H:%M} {count}/{capacity}", flush=True)
        return


def current_slot(now: datetime) -> tuple | None:
    """Return an id for the current 10-minute slot, or None when the gym is closed."""
    if not is_open(now):
        return None
    return now.date(), slot_of(now)


def publish(path: Path) -> None:
    if ha.enabled():
        try:
            ha.publish(path)
        except Exception as e:
            print(f"Home Assistant update failed: {e}", file=sys.stderr, flush=True)


def draw(csv_path: Path, out_path: Path) -> None:
    try:
        import plot  # matplotlib is heavy and only needed here
        plot.plot(csv_path, out_path)
    except Exception as e:
        print(f"Plot failed: {e}", file=sys.stderr, flush=True)


def run(path: Path, plot_out: Path | None) -> None:
    print(f"Writing to {path} (Ctrl+C to stop)", flush=True)
    if ha.enabled():
        print("Publishing sensors to Home Assistant", flush=True)
    if plot_out:
        print(f"Drawing chart to {plot_out} every day after closing", flush=True)
        if not plot_out.exists():
            draw(path, plot_out)
    last_slot = None
    last_publish = 0.0
    last_plot_day = None
    # Compare wall-clock slots instead of sleeping 10 minutes, so that the
    # schedule stays aligned to :00, :10, ... and survives the laptop sleeping.
    while True:
        now = datetime.now(TZ)
        slot = current_slot(now)
        if slot is not None and slot != last_slot:
            last_slot = slot
            poll_once(path)
            publish(path)
            last_publish = time.monotonic()
        elif time.monotonic() - last_publish >= REPUBLISH_EVERY_SECONDS:
            publish(path)
            last_publish = time.monotonic()
        # After the 22:00 sample: redraw once per day.
        if plot_out and minute_of_day(now) > CLOSE_MINUTE and last_plot_day != now.date():
            last_plot_day = now.date()
            draw(path, plot_out)
        time.sleep(CHECK_EVERY_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--once", action="store_true", help="take one sample now and exit")
    parser.add_argument("--plot-out", type=Path, help="PNG redrawn every day after closing")
    args = parser.parse_args()
    # Home Assistant stops the add-on with SIGTERM; exit cleanly with code 0.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    if args.once:
        poll_once(args.csv)
        publish(args.csv)
        return
    try:
        run(args.csv, args.plot_out)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
