"""Monthly cell-day summary for the district calendar (PRD v1.1, section 6.3).

For each month: fire cell-days (F), trusted (T), untrusted (U) and no-data (N) cell-days, the blind share U / (T + U),
and the number of days each sensor had data. Same rules as build_states.py (PREREGISTRATION.md, section 3).

Months inside a pre-registered window are written as locked, with no numbers, until the plan's Release exists
(kapi/guard.py). This summary is exploratory: it is not one of the pre-registered tests.

Example:
  python -I pipeline/build_calendar.py --district "Pulang Pisau" \
      --boundaries data-raw/boundaries/geoBoundaries-IDN-ADM2_simplified.geojson \
      --years 2014-2023 --water-ref 2018-01-01:2018-12-31 --cache data-raw/modis14a1 --out public/ka-data/states
"""
from __future__ import annotations

import argparse
import calendar as cal
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))   # "python -I" does not add the script folder

from build_states import SENSORS, VIIRS, days, period  # noqa: E402
from kapi import firemask, grid, guard, polygon, states  # noqa: E402


def years(text: str) -> list[int]:
    a, _, b = text.partition("-")
    return list(range(int(a), int(b or a) + 1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--district", required=True)
    ap.add_argument("--boundaries", required=True)
    ap.add_argument("--years", required=True, type=years, help="for example 2014-2023")
    ap.add_argument("--water-ref", required=True, type=period)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--viirs-dir", default=None)
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--hold-years", type=int, nargs="*", default=[],
                    help="years written as locked even when allowed: their numbers come from the registered analysis")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    try:
        guard.check(*a.water_ref)
    except guard.NotRegisteredError as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2

    feature = polygon.load_feature(a.boundaries, a.district)
    tiles = grid.tiles_for_bbox(*polygon.bbox(polygon.rings(feature)))
    if len(tiles) != 1:
        print(f"refused: {a.district} spans tiles {tiles}", file=sys.stderr)
        return 3
    h, v = tiles[0]
    inside = polygon.district_mask(feature, h, v)
    modis = firemask.ModisPC(a.cache)

    water = states.WaterMask((grid.N, grid.N))
    for d in days(*a.water_ref):
        for _, platform in SENSORS:
            layer, _ = modis.day(platform, d, h, v)
            if layer is not None:
                water.add(layer)
    water_mask = water.mask()

    months, release = [], None
    for y in a.years:
        for m in range(1, 13):
            start, end = dt.date(y, m, 1), dt.date(y, m, cal.monthrange(y, m)[1])
            ym = f"{y}-{m:02d}"
            if y in a.hold_years:
                months.append({"ym": ym, "locked": True, "reason": "registered analysis"})
                continue
            try:
                rel = guard.check(start, end)
                release = release or rel
            except guard.NotRegisteredError:
                months.append({"ym": ym, "locked": True})
                continue
            tot = {"F": 0, "T": 0, "U": 0, "N": 0}
            sensor_days = {sid: 0 for sid, _ in SENSORS + VIIRS}
            n_days = 0
            for d in days(start, end):
                sts = []
                for sid, platform in SENSORS:
                    layer, _ = modis.day(platform, d, h, v)
                    if layer is not None:
                        sts.append(firemask.sensor_state(layer))
                        sensor_days[sid] += 1
                for sid, product in VIIRS:
                    path = firemask.viirs_file(a.viirs_dir, product, d, h, v)
                    if path is not None:
                        sts.append(firemask.sensor_state(firemask.viirs_h5_firemask(path)))
                        sensor_days[sid] += 1
                n_days += 1
                if not sts:
                    tot["N"] += int(inside.sum() - water_mask[inside].sum())
                    continue
                c = states.counts(states.combine(sts, a.k, None, water_mask)[inside])
                for key in tot:
                    tot[key] += c[key]
            months.append({"ym": ym, "locked": False, "days": n_days, **tot,
                           "blind_share": states.blind_share({**tot, "W": 0}), "sensor_days": sensor_days})
            print(ym, "F", tot["F"], "blind", months[-1]["blind_share"], flush=True)

    slug = a.district.strip().lower().replace(" ", "-")
    out = pathlib.Path(a.out) / "d" / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "calendar.json").write_text(json.dumps({
        "district": a.district, "tile": [h, v], "k": a.k, "years": a.years,
        "water_ref": [a.water_ref[0].isoformat(), a.water_ref[1].isoformat()],
        "water_cells": int(water_mask[inside].sum()), "cells": int(inside.sum()),
        "fire_unit": "fire cell-days from MODIS Terra and Aqua daily FireMask (and VIIRS where available); not harmonized",
        "exploratory": True, "registered_release": release,
        "months": months,
    }), encoding="utf-8")
    print(f"wrote {out / 'calendar.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
