# GTA VI launch-day Twitch viewers — hour-by-hour quantile forecaster

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/qianxunbainian/gta6-twitch-ccu-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/qianxunbainian/gta6-twitch-ccu-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Entry for the make.fun bounty `gta6-twitch-ccu-forecast-01`: forecast how
many people watch Grand Theft Auto VI live on Twitch in each hour of its
release day, 2026-11-19 (UTC), after the first hour.

`main.py` (Python 3, standard library only) is run once per case. It reads
the case file in `$MAKEFUN_INPUT_DIR` (else `/input`) — the category's
hour-1 viewer count plus the hourly release days of 38–42 past big game
launches — and writes one forecast per case to `$MAKEFUN_OUTPUT_DIR`
(else `/output`): for hours 2–24, the 0.05 / 0.25 / 0.5 / 0.75 / 0.95
quantiles of that hour's viewer count. It is deterministic (no randomness,
no clock, no network), so repeated runs are byte-identical, and it runs a
case in well under a second.

## Method

Every hour's forecast is the case's hour-1 count times a ratio, and the
ratio distribution is learned at run time from the case's own comparables:

1. **Ratio curves.** For each comparable launch, take its release-day
   hourly viewers (from its `day_start`) and form log(viewers_h / viewers_1)
   for hours 2–24. A comparable is skipped when its hour 1 is missing or
   was still a pre-unlock trickle (under 6% of its day's peak — e.g. a
   single global unlock late in the UTC day), because its ratios explode
   and teach nothing about a rolling-midnight launch.
2. **Similarity weights.** Each remaining comparable is weighted by
   - unlock shape: launches that unlocked everywhere at one instant, or
     that had days of early access, count for less (×0.5 / ×0.6) — GTA VI
     unlocks at midnight local time, region by region;
   - platform: console-only launches count most (×1.0), console+PC less
     (×0.75), PC-only least (×0.5) — GTA VI is PlayStation 5 / Xbox only;
   - scale: a Gaussian kernel on the gap in log10 hour-1 viewers
     (bandwidth 0.7 decades, floored so distant launches still count a
     little);
   - completeness of the comparable's release-day hours.
3. **Per-hour distribution.** For each hour, the weighted mean and
   standard deviation of the log-ratios; the mean curve is lightly
   smoothed across neighbouring hours and shrunk 15% toward flat, and the
   spread is floored (0.28 + 0.012 per hour, capped at 1.1) so quiet
   agreement among comparables cannot make the forecast overconfident.
4. **Quantiles.** q_tau = hour1 × exp(mu + z_tau × sigma), with z from the
   standard normal at the case's levels, clamped to the allowed range and
   forced non-decreasing. If a case carried no usable comparables, the
   fallback is a flat median with a slowly widening spread.

The rolling-unlock waves are inside the comparable curves rather than
modelled separately: New Zealand unlocked 2026-11-18T11:00Z, central
Europe 23:00Z, the UK at 00:00Z (hour 1), the US east coast at 05:00Z
(hour 6) and the west coast at 08:00Z (hour 9), so the US audience arrives
in steps through the UTC day — the same steps the weighted console,
midnight-local comparables (God of War Ragnarök, Spider-Man 2, Red Dead
Redemption 2, …) traced on their own release days.

## Evidence and validation

The biggest single-player launches set the scale: Cyberpunk 2077 peaked
at ~1.14M concurrent Twitch viewers on launch day (Dec 2020), Hogwarts
Legacy at ~1.28–1.3M (Feb 2023, during early access), Elden Ring at ~875k
hourly average. What transfers to GTA VI is not the level — the case's own
hour-1 print sets that — but the *shape* of the day relative to hour 1,
which is what the model extracts.

Validation is leave-one-out over the 38 comparables in the practice
cases: each launch in turn is treated as the target (its hour 1 known,
the other 37 as evidence) and scored with the competition's own metric,
mean pinball loss on the log scale. On the 27 targets whose hour 1 is at
least 20,000 viewers — the class every real target belongs to (practice
hour-1 prints: 23k–270k) — this forecaster scores **0.267** against
**0.321** for a flat-at-hour-1 forecast with the house baseline's spread;
on targets with hour 1 ≥ 100,000 it scores **0.236** against **0.261**.
Small-hour-1 launches (a few hundred viewers in hour 1, unlocking later
in the day) are hopeless for any hour-1-anchored method and are excluded
from those figures.

## Layout

- `main.py` — the forecaster (the entry).
- `LICENSE` — MIT.
- `.makefun/owner.json` — the entrant wallet for the claim check.

Run it locally the way the kit describes:

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=nypxb97t&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
