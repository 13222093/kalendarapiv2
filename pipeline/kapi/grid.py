"""The MODIS/VIIRS sinusoidal 1 km grid shared by MOD14A1, MYD14A1 and VNP14A1 (1200 x 1200 pixels per tile)."""
from __future__ import annotations

import numpy as np

R = 6371007.181                 # sphere radius of the MODIS sinusoidal projection (m)
TILE = 1111950.5197665          # tile width and height (m)
X0, Y0 = -20015109.354, 10007554.677
N = 1200                        # pixels per tile side at 1 km
SIZE = TILE / N                 # about 926.6 m


def lonlat_to_xy(lon, lat):
    lat_r = np.radians(lat)
    return R * np.radians(lon) * np.cos(lat_r), R * lat_r


def xy_to_lonlat(x, y):
    lat_r = np.asarray(y, float) / R
    return np.degrees(np.asarray(x, float) / (R * np.cos(lat_r))), np.degrees(lat_r)


def tile_of(lon: float, lat: float) -> tuple[int, int]:
    x, y = lonlat_to_xy(lon, lat)
    return int((x - X0) // TILE), int((Y0 - y) // TILE)


def pixel_of(lon, lat, h: int, v: int):
    """Row and column of the pixel of tile (h, v) that contains each lon/lat. Values outside 0..N-1 are off the tile."""
    x, y = lonlat_to_xy(np.asarray(lon, float), np.asarray(lat, float))
    col = np.floor((x - (X0 + h * TILE)) / SIZE).astype(int)
    row = np.floor(((Y0 - v * TILE) - y) / SIZE).astype(int)
    return row, col


def pixel_centers(h: int, v: int, rows=None, cols=None):
    """lon, lat (2-D arrays) of the pixel centres for the given rows and columns of tile (h, v)."""
    rows = np.arange(N) if rows is None else np.asarray(rows)
    cols = np.arange(N) if cols is None else np.asarray(cols)
    x = X0 + h * TILE + (cols + 0.5) * SIZE
    y = Y0 - v * TILE - (rows + 0.5) * SIZE
    xx, yy = np.meshgrid(x, y)
    return xy_to_lonlat(xx, yy)


def tiles_for_bbox(west: float, south: float, east: float, north: float, step: float = 0.05) -> list[tuple[int, int]]:
    """Every tile touched by a lon/lat box (sampled every `step` degrees)."""
    lons = np.append(np.arange(west, east, step), east)
    lats = np.append(np.arange(south, north, step), north)
    return sorted({tile_of(float(lo), float(la)) for lo in lons for la in lats})
