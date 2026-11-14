"""Download MOD14A1/MYD14A1 v6.1 FireMask files (8 days each) for one tile and a date range, without reading them.

Downloading is not analysis: it computes nothing, so it is allowed for any period, the registered 2019 season
included. Example (the 2018 water-mask reference for Pulang Pisau):
  python -I pipeline/fetch_modis.py --tile h29v09 --start 2018-01-01 --end 2018-12-31 --cache data-raw/modis14a1
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))   # "python -I" does not add the script folder

from kapi import firemask  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tile", required=True, help="for example h29v09")
    ap.add_argument("--start", required=True, type=dt.date.fromisoformat)
    ap.add_argument("--end", required=True, type=dt.date.fromisoformat)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--platforms", nargs="+", default=["terra", "aqua"])
    a = ap.parse_args(argv)
    m = re.fullmatch(r"h(\d\d)v(\d\d)", a.tile)
    if not m:
        ap.error("--tile must look like h29v09")
    h, v = int(m.group(1)), int(m.group(2))
    modis = firemask.ModisPC(a.cache)
    got, missing = set(), []
    for platform in a.platforms:
        d = a.start
        while d <= a.end:
            item, path = modis.fetch(platform, d, h, v)
            if item is None or path is None:
                missing.append(f"{platform} {d}")
                d += dt.timedelta(days=1)
                continue
            got.add(path.name)
            # jump to the first day after this file's 8 days (from the item's own end date)
            end = dt.date.fromisoformat(item["properties"]["end_datetime"][:10])
            d = max(d + dt.timedelta(days=1), end + dt.timedelta(days=1))
    print(f"{len(got)} files in {a.cache}; days with no item: {len(missing)}")
    for x in missing[:20]:
        print("  missing:", x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
