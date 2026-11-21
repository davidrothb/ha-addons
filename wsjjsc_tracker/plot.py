#!/usr/bin/env python3
"""Plot gym occupancy for Monday to Sunday, from opening to closing time."""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from history import CLOSE_MINUTE, INTERVAL_MINUTES, OPEN_MINUTE, SLOTS, average_by_slot, clock, load
from poll import DEFAULT_CSV

DAY_NAMES = ["Pondělí", "Úterý", "Středa", "Čtvrtek", "Pátek", "Sobota", "Neděle"]
DEFAULT_OUT = Path(__file__).parent / "data" / "gym_occupancy.png"

SURFACE = "#fcfcfb"
PRIMARY_INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
GRID = "#e1e0d9"
SINGLE_DAY = "#c3c2b7"
AVERAGE = "#2a78d6"


def series(values: dict) -> list[float]:
    """Align {slot: value} to all slots; gaps become NaN so the line breaks."""
    return [values.get(slot, float("nan")) for slot in SLOTS]


def isolated_slots(values: dict) -> list[int]:
    """Slots with no neighbour on either side, which a line alone would not draw."""
    return [
        slot
        for slot in values
        if slot - INTERVAL_MINUTES not in values and slot + INTERVAL_MINUTES not in values
    ]


def draw_day(ax, weekday: int, dates: dict, capacity: int) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=SECONDARY_INK, length=0, labelsize=9)
    ax.set_title(DAY_NAMES[weekday], loc="left", fontsize=11, fontweight="bold", color=PRIMARY_INK)

    if not dates:
        ax.text(
            0.5, 0.5, "zatím bez dat", transform=ax.transAxes,
            ha="center", va="center", fontsize=10, color=SECONDARY_INK,
        )
        return

    for values in dates.values():
        ax.plot(SLOTS, series(values), color=SINGLE_DAY, linewidth=0.8)

    average = average_by_slot(dates)
    ax.plot(SLOTS, series(average), color=AVERAGE, linewidth=2)
    lone = isolated_slots(average)
    ax.plot(lone, [average[s] for s in lone], "o", color=AVERAGE, markersize=4)

    peak_slot = max(average, key=average.get)
    summary = f"špička {average[peak_slot]:.0f} lidí v {clock(peak_slot)}  ·  dnů v datech: {len(dates)}"
    ax.set_title(summary, loc="right", fontsize=9, color=SECONDARY_INK)


def plot(csv_path: Path, out_path: Path) -> None:
    days, capacity = load(csv_path)
    fig, axes = plt.subplots(7, 1, figsize=(11, 15), sharex=True, sharey=True, facecolor=SURFACE)

    for weekday, ax in enumerate(axes):
        draw_day(ax, weekday, days.get(weekday, {}), capacity)

    hours = range(OPEN_MINUTE, CLOSE_MINUTE + 1, 120)
    axes[-1].set_xlim(OPEN_MINUTE, CLOSE_MINUTE)
    axes[-1].set_xticks(list(hours), [clock(h) for h in hours])
    axes[0].set_ylim(0, capacity or None)

    fig.suptitle(
        "Obsazenost posilovny: Taipei Zhongzheng Sports Center",
        x=0.06, ha="left", fontsize=15, fontweight="bold", color=PRIMARY_INK,
    )
    fig.text(
        0.06, 0.945,
        f"Počet lidí, osa Y do kapacity {capacity}. Modře průměr pro daný den v týdnu, šedě jednotlivé dny.",
        fontsize=10, color=SECONDARY_INK,
    )
    fig.subplots_adjust(left=0.06, right=0.98, top=0.915, bottom=0.03, hspace=0.38)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Write next to the target and rename, so nobody ever reads a half-written PNG.
    tmp = out_path.with_name(out_path.name + ".tmp")
    fig.savefig(tmp, dpi=150, format="png")
    plt.close(fig)
    tmp.replace(out_path)
    print(f"Saved {out_path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    plot(args.csv, args.out)


if __name__ == "__main__":
    main()
