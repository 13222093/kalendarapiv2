"""FireMask access test (PREREGISTRATION.md, section 9).

Reads ONE day (2019-09-15) of the MODIS daily FireMask for tile h29v09 from the public Microsoft Planetary
Computer copy of MOD14A1/MYD14A1 v6.1 (no login needed), cuts an approximate Pulang Pisau box and prints the
count of each FireMask class. It checks that the data can be read and decoded. It computes no season statistic.

Usage:  python -I pipeline/firemask_access_test.py <download_dir> [YYYY-MM-DD]
        The optional day is only for decoder checks on days outside every pre-registered period.
Needs:  numpy, requests, tifffile
"""
import datetime as dt
import hashlib
import json
import pathlib
import sys

import numpy as np
import requests
import tifffile

DAY = dt.date(2019, 9, 15)
BBOX = (113.5, -3.6, 114.6, -1.9)        # lon_min, lat_min, lon_max, lat_max. Approximate; the analysis uses the polygon.
TILE_H, TILE_V = 29, 9
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
UA = {"User-Agent": "firemask-access-test/0.1"}

# MODIS sinusoidal grid constants
R = 6371007.181
TILE = 1111950.5197665
X0, Y0 = -20015109.354, 10007554.677
CLASSES = {0: "not processed (missing input)", 1: "not processed (obsolete)", 2: "not processed (other)",
           3: "non-fire water", 4: "cloud", 5: "non-fire land", 6: "unknown",
           7: "fire (low)", 8: "fire (nominal)", 9: "fire (high)"}


def search(collection: str) -> list[dict]:
    body = {"collections": [collection], "bbox": list(BBOX),
            "datetime": f"{DAY.isoformat()}T00:00:00Z/{DAY.isoformat()}T23:59:59Z", "limit": 20}
    r = requests.post(STAC, json=body, headers=UA, timeout=60)
    r.raise_for_status()
    return r.json()["features"]


def sign(href: str) -> str:
    r = requests.get(SIGN, params={"href": href}, headers=UA, timeout=60)
    r.raise_for_status()
    return r.json()["href"]


def box_mask(n: int) -> np.ndarray:
    """True for pixels of tile h29v09 whose centre is inside BBOX."""
    size = TILE / n
    cols = np.arange(n) + 0.5
    rows = np.arange(n) + 0.5
    x = X0 + TILE_H * TILE + cols * size
    y = Y0 - TILE_V * TILE - rows * size
    xx, yy = np.meshgrid(x, y)
    lat = np.degrees(yy / R)
    lon = np.degrees(xx / (R * np.cos(np.radians(lat))))
    return (lon >= BBOX[0]) & (lon <= BBOX[2]) & (lat >= BBOX[1]) & (lat <= BBOX[3])


def main(out_dir: pathlib.Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tile = f"h{TILE_H:02d}v{TILE_V:02d}"
    report = {"day": DAY.isoformat(), "bbox": BBOX, "tile": tile, "items": []}
    for item in search("modis-14A1-061"):
        if tile not in item["id"]:
            continue
        p = item["properties"]
        asset = item["assets"].get("FireMask")
        entry = {"id": item["id"], "platform": p.get("platform"), "start": p.get("start_datetime"),
                 "end": p.get("end_datetime"), "assets": sorted(item["assets"].keys())}
        if not asset:
            entry["error"] = "no FireMask asset"
            report["items"].append(entry)
            continue
        dest = out_dir / f"{item['id']}_FireMask.tif"
        if not dest.exists():
            with requests.get(sign(asset["href"]), headers=UA, timeout=300, stream=True) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
        data = dest.read_bytes()
        entry["file"] = dest.name
        entry["bytes"] = len(data)
        entry["sha256"] = hashlib.sha256(data).hexdigest()
        arr = tifffile.imread(dest)
        entry["shape"] = list(arr.shape)
        entry["dtype"] = str(arr.dtype)
        start = dt.date.fromisoformat(p["start_datetime"][:10]) if p.get("start_datetime") else None
        if arr.ndim == 3:
            # layers are either (day, y, x) or (y, x, day)
            day_axis = 0 if arr.shape[0] <= 16 else 2
            idx = (DAY - start).days if start else None
            entry["day_axis"] = day_axis
            entry["day_index"] = idx
            layer = np.take(arr, idx, axis=day_axis)
        else:
            layer = arr
            entry["note"] = "single layer: check that it is the 2019-09-15 layer"
        m = box_mask(layer.shape[0])
        vals, counts = np.unique(layer[m], return_counts=True)
        entry["box_pixels"] = int(m.sum())
        entry["class_counts"] = {f"{int(v)} {CLASSES.get(int(v), '?')}": int(c) for v, c in zip(vals, counts)}
        report["items"].append(entry)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 2:
        DAY = dt.date.fromisoformat(sys.argv[2])
    main(pathlib.Path(sys.argv[1]))
