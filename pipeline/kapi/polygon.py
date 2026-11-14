"""District polygons (geoBoundaries GeoJSON) and a vectorised point-in-polygon test."""
from __future__ import annotations

import json
import pathlib

import numpy as np

from . import grid


def load_feature(path, name: str, key: str = "shapeName") -> dict:
    gj = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    want = name.strip().lower()
    hits = [f for f in gj["features"] if str(f["properties"].get(key, "")).strip().lower() == want]
    if len(hits) != 1:
        raise ValueError(f"expected one feature named {name!r} in {path}, found {len(hits)}")
    return hits[0]


def rings(feature: dict) -> list[np.ndarray]:
    g = feature["geometry"]
    if g["type"] == "Polygon":
        polys = [g["coordinates"]]
    elif g["type"] == "MultiPolygon":
        polys = g["coordinates"]
    else:
        raise ValueError(f"unsupported geometry {g['type']}")
    return [np.asarray(r, float)[:, :2] for poly in polys for r in poly]


def bbox(rs: list[np.ndarray]) -> tuple[float, float, float, float]:
    pts = np.vstack(rs)
    return float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max())


def contains(rs: list[np.ndarray], lon, lat) -> np.ndarray:
    """Even-odd rule over every ring (outer rings and holes), so holes and multipolygons are handled."""
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    inside = np.zeros(lon.shape, bool)
    for r in rs:
        xa, ya = r[:, 0], r[:, 1]
        xb, yb = np.roll(xa, -1), np.roll(ya, -1)
        for x1, y1, x2, y2 in zip(xa, ya, xb, yb):
            if y1 == y2:
                continue
            crosses = (y1 > lat) != (y2 > lat)
            x_at = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            inside ^= crosses & (lon < x_at)
    return inside


def district_mask(feature: dict, h: int, v: int) -> np.ndarray:
    """N x N boolean mask of tile (h, v): True where the pixel centre is inside the district."""
    rs = rings(feature)
    w, s, e, n = bbox(rs)
    lo, la = np.meshgrid(np.linspace(w, e, 60), np.linspace(s, n, 60))
    r, c = grid.pixel_of(lo, la, h, v)
    r0, r1 = max(int(r.min()) - 1, 0), min(int(r.max()) + 1, grid.N - 1)
    c0, c1 = max(int(c.min()) - 1, 0), min(int(c.max()) + 1, grid.N - 1)
    mask = np.zeros((grid.N, grid.N), bool)
    if r0 > r1 or c0 > c1:
        return mask
    lon, lat = grid.pixel_centers(h, v, np.arange(r0, r1 + 1), np.arange(c0, c1 + 1))
    mask[r0:r1 + 1, c0:c1 + 1] = contains(rs, lon, lat)
    return mask
