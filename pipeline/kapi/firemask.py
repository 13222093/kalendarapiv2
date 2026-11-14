"""Daily FireMask readers and the per-sensor state of each pixel (PREREGISTRATION.md, section 3.1).

MODIS (MOD14A1 Terra, MYD14A1 Aqua, v6.1) is read from the public Microsoft Planetary Computer copy
(STAC collection modis-14A1-061, no login). Each file holds 8 days; its GDAL "Dates" metadata says which band is
which day. VIIRS (VNP14A1, VJ114A1, v002) is read from .h5 files downloaded from NASA LP DAAC (needs Earthdata Login).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import pathlib
import re

import numpy as np

# Per-sensor state codes
NODATA, CLOUD, CLEAR, FIRE, WATER = 0, 1, 2, 3, 4

_MAP = np.zeros(256, np.uint8)            # 0, 1, 2 (not processed), 6 (unknown) and anything unexpected: NODATA
_MAP[3] = WATER
_MAP[4] = CLOUD
_MAP[5] = CLEAR
_MAP[7] = _MAP[8] = _MAP[9] = FIRE

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token"   # + /<storage account>/<container>
UA = {"User-Agent": "kalenderapi-pipeline/0.1"}


def sensor_state(firemask: np.ndarray) -> np.ndarray:
    """FireMask classes (0..9) to per-sensor states (NODATA, CLOUD, CLEAR, FIRE, WATER)."""
    return _MAP[np.asarray(firemask, np.uint8)]


def class_counts(firemask: np.ndarray, mask: np.ndarray) -> dict[str, int]:
    """Counts of FireMask class groups inside `mask` (the district), for the provenance of each day."""
    vals = np.asarray(firemask)[mask]
    return {
        "fire": int(np.isin(vals, (7, 8, 9)).sum()),
        "clear": int((vals == 5).sum()),
        "cloud": int((vals == 4).sum()),
        "water": int((vals == 3).sum()),
        "unknown": int((vals == 6).sum()),
        "not_processed": int(np.isin(vals, (0, 1, 2)).sum()),
    }


def parse_dates(gdal_metadata_xml: str) -> list[dt.date]:
    m = re.search(r'<Item name="Dates">([^<]+)</Item>', gdal_metadata_xml)
    if not m:
        raise ValueError("no Dates item in GDAL metadata")
    return [dt.date.fromisoformat(s) for s in m.group(1).split()]


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ModisPC:
    """MOD14A1/MYD14A1 v6.1 daily FireMask from the Planetary Computer copy, cached on disk."""

    PLATFORMS = {"terra": "MOD14A1", "aqua": "MYD14A1"}

    def __init__(self, cache_dir, session=None):
        import requests                          # only needed for downloads
        self.cache = pathlib.Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.http = session or requests.Session()
        self._items: dict[tuple, list[dict]] = {}
        self._files: dict[pathlib.Path, tuple[list[dt.date], np.ndarray]] = {}

    def _search(self, day: dt.date, h: int, v: int) -> list[dict]:
        key = (day, h, v)
        if key not in self._items:
            from . import grid
            lon, lat = grid.pixel_centers(h, v, [grid.N // 2], [grid.N // 2])
            lo, la = float(lon[0, 0]), float(lat[0, 0])
            # a tiny box at the tile centre, so the search returns this tile's items and not 50 tiles from elsewhere
            body = {"collections": ["modis-14A1-061"], "limit": 50, "bbox": [lo - 0.01, la - 0.01, lo + 0.01, la + 0.01],
                    "datetime": f"{day.isoformat()}T00:00:00Z/{day.isoformat()}T23:59:59Z"}
            r = self._send("post", STAC, json=body, timeout=60)
            tile = f"h{h:02d}v{v:02d}"
            self._items[key] = [f for f in r.json()["features"] if tile in f["id"]]
        return self._items[key]

    KEEP_FILES = 4   # decoded 8-day files kept in memory (about 11.5 MB each); days are read in order

    def _read(self, path: pathlib.Path) -> tuple[list[dt.date], np.ndarray]:
        if path not in self._files:
            import tifffile
            with tifffile.TiffFile(path) as t:
                dates = parse_dates(t.pages[0].tags["GDAL_METADATA"].value)
                arr = t.asarray()
            self._files[path] = (dates, arr)
            while len(self._files) > self.KEEP_FILES:
                self._files.pop(next(iter(self._files)))
        return self._files[path]

    def fetch(self, platform: str, day: dt.date, h: int, v: int) -> tuple[dict | None, pathlib.Path | None]:
        """Download (once) the 8-day file that holds this day, without reading it. Returns (STAC item, path)."""
        prefix = self.PLATFORMS[platform]
        items = [f for f in self._search(day, h, v) if f["id"].startswith(prefix)]
        if not items:
            return None, None
        item = items[0]
        path = self.cache / f"{item['id']}_FireMask.tif"
        if not path.exists():
            import time
            import requests
            href = item["assets"]["FireMask"]["href"]
            tmp = path.with_suffix(".part")
            for attempt in range(5):
                try:
                    with self._get(f"{href}?{self._token(href)}", stream=True, timeout=300) as r:
                        with open(tmp, "wb") as f:
                            for chunk in r.iter_content(1 << 20):
                                f.write(chunk)
                    tmp.replace(path)
                    break
                except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError,
                        requests.exceptions.Timeout):
                    tmp.unlink(missing_ok=True)
                    if attempt == 4:
                        raise
                    time.sleep(2 ** (attempt + 1))
        return item, path

    def _get(self, url: str, **kw):
        return self._send("get", url, **kw)

    def _send(self, method: str, url: str, **kw):
        """A request with retries on HTTP 429 and 5xx (waits Retry-After, or 2, 4, 8... seconds)."""
        import time
        import requests
        for attempt in range(7):
            try:
                r = getattr(self.http, method)(url, headers=UA, **kw)
            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.Timeout):
                if attempt == 6:
                    raise
                time.sleep(min(2 ** (attempt + 1), 60))
                continue
            if r.status_code != 429 and r.status_code < 500:
                r.raise_for_status()
                return r
            wait = float(r.headers.get("Retry-After") or 2 ** (attempt + 1))
            r.close()
            time.sleep(min(wait, 60))
        r.raise_for_status()
        return r

    def _token(self, href: str) -> str:
        """One read token per storage account and container (asked again after 30 minutes), instead of one signed URL
        per file: Planetary Computer limits how often its signing endpoint may be called."""
        import time
        from urllib.parse import urlparse
        u = urlparse(href)
        key = (u.netloc.split(".")[0], u.path.lstrip("/").split("/")[0])
        toks = self.__dict__.setdefault("_toks", {})
        if key not in toks or time.time() > toks[key][1]:
            t = self._get(f"{TOKEN}/{key[0]}/{key[1]}", timeout=60).json()
            toks[key] = (t["token"], time.time() + 30 * 60)
        return toks[key][0]

    def day(self, platform: str, day: dt.date, h: int, v: int):
        """(FireMask array or None, provenance dict) for one platform, day and tile."""
        item, path = self.fetch(platform, day, h, v)
        if item is None or path is None:
            return None, {"platform": platform, "has_data": False, "reason": "no item"}
        dates, arr = self._read(path)
        if day not in dates:
            return None, {"platform": platform, "has_data": False, "reason": "day not in file", "item": item["id"]}
        band = dates.index(day)
        layer = arr[..., band] if arr.ndim == 3 and arr.shape[-1] == len(dates) else arr[band]
        return layer, {"platform": platform, "has_data": True, "item": item["id"], "file": path.name,
                       "sha256": sha256(path), "bytes": path.stat().st_size, "band": band}


def viirs_h5_firemask(path) -> np.ndarray:
    """The FireMask dataset of a VNP14A1/VJ114A1 v002 .h5 file (found by name, wherever it sits in the file)."""
    import h5py
    found: list[str] = []

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset) and name.split("/")[-1] == "FireMask":
            found.append(name)

    with h5py.File(path, "r") as f:
        f.visititems(visit)
        if len(found) != 1:
            raise ValueError(f"expected one FireMask dataset in {path}, found {found}")
        return np.asarray(f[found[0]][()])


def viirs_file(directory, product: str, day: dt.date, h: int, v: int) -> pathlib.Path | None:
    """The local .h5 file of a VIIRS product for one day and tile, or None."""
    if not directory:
        return None
    pattern = f"{product}.A{day.year}{day.timetuple().tm_yday:03d}.h{h:02d}v{v:02d}.*.h5"
    hits = sorted(pathlib.Path(directory).glob(pattern))
    return hits[-1] if hits else None
