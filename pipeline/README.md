# FireMask cell-day pipeline

This pipeline builds the daily cell-day states `F`, `T`, `U`, `N` (and `W` for static water) for one district. The rules are in [`../PREREGISTRATION.md`](../PREREGISTRATION.md), section 3.

| File | What it does |
|---|---|
| `kapi/grid.py` | MODIS/VIIRS sinusoidal 1 km grid: tiles, pixels, pixel centres |
| `kapi/polygon.py` | geoBoundaries district polygon and a point-in-polygon test that handles holes and multipolygons |
| `kapi/firemask.py` | Reads MODIS FireMask from the public Planetary Computer copy (no login) and VIIRS FireMask from local `.h5` files. Maps each FireMask class to a per-sensor state |
| `kapi/states.py` | Combines the sensors into cell-day states with threshold k, and builds the static water mask |
| `kapi/guard.py` | **Refuses any day of 2019 until the Release `prereg-v1` is published** |
| `build_states.py` | Command line: one district and a date range, writing JSON files |
| `fetch_modis.py` | Command line: download (only) the MODIS FireMask files of one tile and a date range. It computes nothing, so it may fetch any period, 2019 included |
| `tests/test_core.py` | Unit tests (no network) |
| `firemask_access_test.py`, `ACCESS_TEST.md` | The access test done before registration |

## Setup

```bash
python -m pip install -r pipeline/requirements.txt
```

## Run

**Tests:**

```bash
python -I pipeline/tests/test_core.py -v
```

**Download first** (the 2018 water-mask reference for both districts: 184 files, about 121 MB):

```bash
python -I pipeline/fetch_modis.py --tile h29v09 --start 2018-01-01 --end 2018-12-31 --cache data-raw/modis14a1
python -I pipeline/fetch_modis.py --tile h28v09 --start 2018-01-01 --end 2018-12-31 --cache data-raw/modis14a1
```

Files come from Planetary Computer with one read token per storage container. Requests that hit its rate limit (HTTP 429) wait and retry.

**Development run on 2018,** a year the plan does not use:

```bash
python -I pipeline/build_states.py --district "Pulang Pisau" --boundaries data-raw/boundaries/geoBoundaries-IDN-ADM2_simplified.geojson --start 2018-09-14 --end 2018-09-21 --water-ref 2018-09-14:2018-09-21 --cache data-raw/modis14a1 --out data-raw/dev-out
```

**Registered run,** which only works after `prereg-v1` is published:

1. Write `pipeline/REGISTRATION.json` containing `{"repo": "<owner>/<repo>", "tag": "prereg-v1"}`.
2. Run:

```bash
python -I pipeline/build_states.py --district "Pulang Pisau" --boundaries data-raw/boundaries/geoBoundaries-IDN-ADM2_simplified.geojson --start 2019-08-01 --end 2019-10-31 --water-ref 2018-01-01:2018-12-31 --cache data-raw/modis14a1 --viirs-dir data-raw/vnp14a1 --out public/data
```

## Inputs

- **MODIS MOD14A1 / MYD14A1 v6.1:** downloaded automatically from Microsoft Planetary Computer (`modis-14A1-061`) into `--cache`. The day of each layer comes from the file's GDAL `Dates` metadata.
- **VIIRS VNP14A1 v002:** `.h5` files in `--viirs-dir`, named `VNP14A1.AYYYYDDD.h29v09.*.h5`.
  - They come from NASA LP DAAC, which needs a free NASA Earthdata Login. A team member signs in themselves, for example with `earthaccess.login()` or a `.netrc` file on their own machine.
  - **If no file is found, the day is built from Terra and Aqua only, and the output says so** (`"has_data": false`).
- **District polygons:** geoBoundaries gbOpen IDN ADM2, simplified (`IDN-ADM2-22746128`, CC BY 3.0 IGO; source BPS, WFP, OCHA ROAP). They come from `https://www.geoboundaries.org/api/current/gbOpen/IDN/ADM2/`.
- **FIRMS fire points (optional):** archive CSVs with `latitude`, `longitude`, `acq_date`, passed with `--firms`.

## Outputs (`<out>/d/<district-slug>/`)

| File | Contents |
|---|---|
| `grid.json` | Tile, number of cells, the boundary file and its sha256, and every cell as `[row, col, lon, lat]` in index order |
| `water.json` | Reference period, the rule, and the indices of static water cells |
| `boundary.geojson` | The district polygon used (for drawing its outline) |
| `index.json` | District, dates, k, list of months, and the registered Release (`null` = development data outside every registered period; the app shows a ribbon) |
| `m/<YYYY-MM>.json` | One entry per day (described below) |

Each day entry holds:
- `cells` (counts for k = 1) and `cells_k2` (counts for k = 2);
- `blind_share` = U / (T + U);
- `firms_only_fire`;
- `states`: one letter per cell, in index order;
- `sensors`: for each sensor, whether it has data, the file, sha256, band, and FireMask class counts inside the district.

The pipeline writes **no season statistic**. `numbers.json` is produced only after registration.

## Known limits

- Districts spanning more than one tile are refused for now. Pulang Pisau (h29v09) and OKI (h28v09) are single-tile.
- Pixel membership uses the simplified boundary and the pixel centre. The 2018 test gives 11,400 cells for Pulang Pisau, about 9,800 km².
- FIRMS `acq_date` is in UTC, and so are the daily FireMask composites.
