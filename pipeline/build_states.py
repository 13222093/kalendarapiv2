"""Build daily cell-day states for one district (PREREGISTRATION.md, sections 3.1 to 3.3).

Development example (2018 is not a registered year):
  python -I pipeline/build_states.py --district "Pulang Pisau" \
      --boundaries data-raw/boundaries/geoBoundaries-IDN-ADM2_simplified.geojson \
      --start 2018-09-14 --end 2018-09-21 --water-ref 2018-09-14:2018-09-21 \
      --cache data-raw/modis14a1 --out public/data

Writes
  <out>/d/<slug>/grid.json         tile and the district's cells (row, col, lon, lat) in index order
  <out>/d/<slug>/water.json        the static water mask: reference period and water cell indices
  <out>/d/<slug>/m/<YYYY-MM>.json  one entry per day: cell counts (k = 1 and k = 2), blind share, states
                                   (one letter per cell: F T U N, W for static water) and per-sensor provenance

It writes no season statistic. Those go to numbers.json, and only after the plan is registered.
Any day of 2019 is refused until the GitHub Release prereg-v1 exists (kapi/guard.py).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))   # "python -I" does not add the script folder

from kapi import firemask, grid, guard, polygon, states  # noqa: E402

SENSORS = [("terra_modis", "terra"), ("aqua_modis", "aqua")]
VIIRS = [("snpp_viirs", "VNP14A1")]          # NOAA-20 (VJ114A1) is sensitivity only and is not combined here


def days(a: dt.date, b: dt.date):
    d = a
    while d <= b:
        yield d
        d += dt.timedelta(days=1)


def period(text: str) -> tuple[dt.date, dt.date]:
    a, b = text.split(":")
    return dt.date.fromisoformat(a), dt.date.fromisoformat(b)


def load_firms(paths: list[str]) -> dict[dt.date, tuple[np.ndarray, np.ndarray]]:
    """FIRMS archive CSVs (columns latitude, longitude, acq_date) grouped by day."""
    by_day: dict[dt.date, list[tuple[float, float]]] = {}
    for p in paths:
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                d = dt.date.fromisoformat(row["acq_date"][:10])
                by_day.setdefault(d, []).append((float(row["longitude"]), float(row["latitude"])))
    return {d: (np.array([p[0] for p in v]), np.array([p[1] for p in v])) for d, v in by_day.items()}


def firms_mask(points, h: int, v: int) -> np.ndarray:
    m = np.zeros((grid.N, grid.N), bool)
    if points is None:
        return m
    r, c = grid.pixel_of(points[0], points[1], h, v)
    ok = (r >= 0) & (r < grid.N) & (c >= 0) & (c < grid.N)
    m[r[ok], c[ok]] = True
    return m


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--district", required=True)
    ap.add_argument("--boundaries", required=True, help="geoBoundaries IDN ADM2 GeoJSON")
    ap.add_argument("--start", required=True, type=dt.date.fromisoformat)
    ap.add_argument("--end", required=True, type=dt.date.fromisoformat)
    ap.add_argument("--water-ref", required=True, type=period, help="START:END of the water-mask reference period")
    ap.add_argument("--cache", required=True, help="folder for downloaded MODIS FireMask files")
    ap.add_argument("--viirs-dir", default=None, help="folder with VNP14A1 .h5 files (optional)")
    ap.add_argument("--firms", nargs="*", default=[], help="FIRMS archive CSV files (optional)")
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    for s, e in ((a.start, a.end), a.water_ref):
        try:
            guard.check(s, e)
        except guard.NotRegisteredError as err:
            print(f"refused: {err}", file=sys.stderr)
            return 2

    feature = polygon.load_feature(a.boundaries, a.district)
    rs = polygon.rings(feature)
    tiles = grid.tiles_for_bbox(*polygon.bbox(rs))
    if len(tiles) != 1:
        print(f"refused: {a.district} spans tiles {tiles}; multi-tile districts are not supported yet", file=sys.stderr)
        return 3
    h, v = tiles[0]
    inside = polygon.district_mask(feature, h, v)
    idx = np.flatnonzero(inside)
    rows, cols = np.unravel_index(idx, inside.shape)
    lon, lat = grid.pixel_centers(h, v)
    slug = a.district.strip().lower().replace(" ", "-")
    out = pathlib.Path(a.out) / "d" / slug
    (out / "m").mkdir(parents=True, exist_ok=True)

    boundary_bytes = pathlib.Path(a.boundaries).read_bytes()
    (out / "grid.json").write_text(json.dumps({
        "district": a.district, "tile": [h, v], "n_cells": int(idx.size),
        "boundary": {"file": pathlib.Path(a.boundaries).name, "sha256": hashlib.sha256(boundary_bytes).hexdigest(),
                     "shapeID": feature["properties"].get("shapeID")},
        "cells": [[int(r), int(c), round(float(lon[r, c]), 5), round(float(lat[r, c]), 5)] for r, c in zip(rows, cols)],
    }), encoding="utf-8")

    modis = firemask.ModisPC(a.cache)

    water = states.WaterMask((grid.N, grid.N))
    for d in days(*a.water_ref):
        for _, platform in SENSORS:
            layer, _ = modis.day(platform, d, h, v)
            if layer is not None:
                water.add(layer)
    water_mask = water.mask()
    (out / "water.json").write_text(json.dumps({
        "reference": [a.water_ref[0].isoformat(), a.water_ref[1].isoformat()], "sensor_days": water.days,
        "rule": "water if FireMask said water (3) at least as often as clear land (5), and at least once",
        "water_cells": [int(i) for i in np.flatnonzero(water_mask[inside])],
    }), encoding="utf-8")

    firms = load_firms(a.firms)
    months: dict[str, list[dict]] = {}
    for d in days(a.start, a.end):
        sensor_states, sensor_info, any_fire_sensor = [], [], np.zeros((grid.N, grid.N), bool)
        for sid, platform in SENSORS:
            layer, prov = modis.day(platform, d, h, v)
            info = {"id": sid, **prov}
            if layer is not None:
                st = firemask.sensor_state(layer)
                sensor_states.append(st)
                any_fire_sensor |= st == firemask.FIRE
                info["firemask"] = firemask.class_counts(layer, inside)
            sensor_info.append(info)
        for sid, product in VIIRS:
            path = firemask.viirs_file(a.viirs_dir, product, d, h, v)
            if path is None:
                sensor_info.append({"id": sid, "has_data": False, "reason": "no local file"})
                continue
            layer = firemask.viirs_h5_firemask(path)
            st = firemask.sensor_state(layer)
            sensor_states.append(st)
            any_fire_sensor |= st == firemask.FIRE
            sensor_info.append({"id": sid, "has_data": True, "file": path.name, "sha256": firemask.sha256(path),
                                "firemask": firemask.class_counts(layer, inside)})
        fm = firms_mask(firms.get(d), h, v)
        if sensor_states:
            cells = states.combine(sensor_states, a.k, fm, water_mask)
            cells_k2 = states.combine(sensor_states, 2, fm, water_mask)
        else:
            cells = np.full((grid.N, grid.N), states.N_, np.uint8)
            cells_k2 = cells
        c = states.counts(cells[inside])
        months.setdefault(d.strftime("%Y-%m"), []).append({
            "date": d.isoformat(), "k": a.k, "cells": c, "blind_share": states.blind_share(c),
            "cells_k2": states.counts(cells_k2[inside]),
            "firms_only_fire": int(((cells == states.F_) & fm & ~any_fire_sensor)[inside].sum()),
            "states": states.letters(cells[inside]),
            "sensors": sensor_info,
        })

    for ym, entries in months.items():
        (out / "m" / f"{ym}.json").write_text(json.dumps({"district": a.district, "month": ym, "days": entries}),
                                             encoding="utf-8")
    print(json.dumps({"district": a.district, "tile": [h, v], "cells": int(idx.size),
                      "water_cells": int(water_mask[inside].sum()), "days": sum(len(x) for x in months.values()),
                      "out": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
