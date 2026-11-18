#!/usr/bin/env python3
"""Forecast a game launch day's Twitch category viewers, hour by hour.

The program is run once per case. A case file says how many viewers the
category had in hour 1 of its release day and carries the hourly release
days of dozens of past big launches ("comparables"). The forecast for
each later hour is the case's hour-1 count times a ratio, and the ratio's
distribution comes from those comparables: how each past launch's hour h
compared with its own hour 1, weighted toward the launches most like
this one (console launches that unlocked at midnight local time, at a
similar scale), with the unlock waves of a rolling midnight launch --
New Zealand and Asia first, Europe next, the United States last --
already inside the comparable curves.

Only the Python standard library is used, there is no randomness and no
clock reading, so two runs of a case give byte-identical output.
"""

import json
import math
import os
import re
import sys
from datetime import datetime
from statistics import NormalDist

NORMAL = NormalDist()
DEFAULT_LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
FIRST_FORECAST_HOUR = 2
LAST_HOUR = 24

# Model constants, chosen on the practice comparables (see README).
MU_SHRINK = 0.85        # pull the empirical log-ratio toward flat by this
SCALE_BANDWIDTH = 0.7   # decades of hour-1 scale over which matches fade
SIGMA_FLOOR_BASE = 0.28
SIGMA_FLOOR_SLOPE = 0.012
SIGMA_CAP = 1.1


def parse_instant(text):
    """Parse an ISO 8601 UTC timestamp into an aware datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def release_day_hours(comparable):
    """Map hour-of-release-day (1..24) to viewers for one comparable.

    The comparable's hourly points are whole-hour averages starting at
    each point's `from`; the release day starts at its `day_start`.
    Points outside the day, and hours with no positive count, are left
    out.
    """
    start = parse_instant(comparable["day_start"])
    hours = {}
    for point in comparable.get("hourly") or []:
        viewers = point.get("viewers")
        if viewers is None or viewers <= 0:
            continue
        delta = parse_instant(point["from"]) - start
        hour = int(delta.total_seconds() // 3600) + 1
        if 1 <= hour <= LAST_HOUR:
            hours[hour] = float(viewers)
    return hours


def unlock_factor(comparable):
    """Down-weight launches whose unlock shape differs from this one.

    The target unlocks at midnight local time, region by region. A past
    launch that unlocked everywhere at one instant, or that had already
    been playable for days through an early-access edition, traces a
    differently shaped day, so its curve counts for less.
    """
    text = (comparable.get("unlock") or "").lower()
    factor = 1.0
    if "simultaneous" in text or "single global unlock" in text:
        factor *= 0.5
    if "early access" in text or "early-access" in text:
        factor *= 0.6
    return factor


def platform_factor(comparable):
    """Down-weight launches that did not lead on consoles.

    The target is console-only (PlayStation 5 and Xbox Series). A launch
    that also shipped on PC the same day mixes a PC audience wave into
    its curve; a PC-only launch is a poorer match still.
    """
    text = (comparable.get("platforms") or "").lower()
    tokens = re.split(r"[^a-z0-9]+", text)
    has_pc = "pc" in tokens
    has_console = any(
        token in tokens for token in ("ps4", "ps5", "playstation", "xbox", "switch")
    )
    if has_console and not has_pc:
        return 1.0
    if has_console and has_pc:
        return 0.75
    if has_pc:
        return 0.5
    return 0.7


def usable_day(comparable):
    """Return (hours, weight) for a comparable, or None if unusable.

    A comparable teaches nothing about ratios to hour 1 when its own
    hour 1 is missing, or when that hour was still a pre-unlock trickle
    (a small fraction of its day's peak): its ratios would explode.
    """
    hours = release_day_hours(comparable)
    first = hours.get(1)
    if not first:
        return None
    peak = max(hours.values())
    if first < 0.06 * peak:
        return None
    present = sum(1 for h in range(FIRST_FORECAST_HOUR, LAST_HOUR + 1) if h in hours)
    if present < 12:
        return None
    completeness = 0.5 + 0.5 * (present / (LAST_HOUR - 1))
    return hours, completeness


def comparable_weight(comparable, hours, target_log10_first):
    """How much one comparable's curve should count for this case."""
    weight = unlock_factor(comparable) * platform_factor(comparable)
    gap = math.log10(hours[1]) - target_log10_first
    weight *= max(0.15, math.exp(-0.5 * (gap / SCALE_BANDWIDTH) ** 2))
    return weight


def weighted_mean_sd(pairs):
    """Weighted mean and standard deviation of (value, weight) pairs."""
    total = sum(w for _, w in pairs)
    if total <= 0:
        return 0.0, 0.0
    mean = sum(v * w for v, w in pairs) / total
    var = sum(w * (v - mean) ** 2 for v, w in pairs) / total
    return mean, math.sqrt(var)


def smooth(values):
    """One pass of a (0.25, 0.5, 0.25) moving average over the hours."""
    out = {}
    for h in sorted(values):
        acc = 0.5 * values[h]
        norm = 0.5
        for other in (h - 1, h + 1):
            if other in values:
                acc += 0.25 * values[other]
                norm += 0.25
        out[h] = acc / norm
    return out


def hour1_print(case):
    """The case's hour-1 viewer count, from its `known` row(s)."""
    known = case.get("known") or []
    if isinstance(known, dict):
        known = [known]
    for row in known:
        if row.get("hour") == 1 and row.get("viewers"):
            return float(row["viewers"])
    for row in known:
        if row.get("viewers"):
            return float(row["viewers"])
    return 1.0


def forecast_case(case):
    """Return the 23 output rows for one parsed case."""
    levels = case.get("levels") or DEFAULT_LEVELS
    zscores = [NORMAL.inv_cdf(level) for level in levels]
    first = max(1.0, hour1_print(case))
    target_log10_first = math.log10(first)

    prepared = []
    for comparable in case.get("comparables") or []:
        got = usable_day(comparable)
        if got is None:
            continue
        hours, completeness = got
        weight = comparable_weight(comparable, hours, target_log10_first)
        prepared.append((hours, weight * completeness))

    means = {}
    sds = {}
    for h in range(FIRST_FORECAST_HOUR, LAST_HOUR + 1):
        pairs = [
            (math.log(hours[h] / hours[1]), weight)
            for hours, weight in prepared
            if h in hours
        ]
        if pairs:
            means[h], sds[h] = weighted_mean_sd(pairs)
    if means:
        means = smooth(means)

    rows = []
    for h in range(FIRST_FORECAST_HOUR, LAST_HOUR + 1):
        if h in means:
            mu = MU_SHRINK * means[h]
            sigma = sds.get(h, 0.4)
            sigma = min(
                SIGMA_CAP,
                max(sigma, SIGMA_FLOOR_BASE + SIGMA_FLOOR_SLOPE * (h - FIRST_FORECAST_HOUR)),
            )
        else:
            mu = 0.0
            sigma = 0.16 * math.sqrt(h - 1) + 0.05
        quantiles = []
        for z in zscores:
            q = first * math.exp(mu + z * sigma)
            q = min(q, 1_000_000_000.0)
            if quantiles and q < quantiles[-1]:
                q = quantiles[-1]
            quantiles.append(round(q, 2))
        rows.append({"hour": h, "q": quantiles})
    return rows


def main():
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(output_dir, exist_ok=True)
    names = sorted(name for name in os.listdir(input_dir) if name.endswith(".in"))
    for name in names:
        with open(os.path.join(input_dir, name), "r", encoding="utf-8") as handle:
            case = json.load(handle)
        rows = forecast_case(case)
        out_name = name[: -len(".in")] + ".out"
        with open(os.path.join(output_dir, out_name), "w", encoding="utf-8") as handle:
            json.dump({"hours": rows}, handle)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
