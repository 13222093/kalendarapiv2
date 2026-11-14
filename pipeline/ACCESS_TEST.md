# FireMask access test (14 November 2026)

This test checks that the daily FireMask products can be found, downloaded, and decoded for Pulang Pisau. It is listed in `PREREGISTRATION.md`, section 9. **It computes no season-level statistic.**

- **Script:** `pipeline/firemask_access_test.py`.
- **Downloads:** `data-raw/firemask_access/` (not committed).

## 1. Granules exist (NASA CMR, no login)

All four products have one granule over Pulang Pisau on 2019-09-15, all on **tile h29v09**:

| Product | Granule |
|---|---|
| MOD14A1.061 | MOD14A1.A2019257.h29v09.061.2020310063527 (8-day file, 14 to 21 Sep) |
| MYD14A1.061 | MYD14A1.A2019257.h29v09.061.2020310093500 (8-day file, 14 to 21 Sep) |
| VNP14A1.002 | VNP14A1.A2019258.h29v09.002.2022360200155 (one day) |
| VJ114A1.002 | VJ114A1.A2019258.h29v09.002.2022353030932 (one day) |

The LP DAAC download links are under `lp-prod-protected`, so they need a NASA Earthdata Login.

## 2. MODIS FireMask decoded (Planetary Computer, no login)

Microsoft Planetary Computer hosts MOD14A1/MYD14A1 v6.1 (`modis-14A1-061`) as cloud-optimized GeoTIFFs:
- the FireMask asset is 1200 × 1200 × 8, `uint8`, one layer per day;
- the item's start date gives the layer order (layer 1 = 2019-09-15).

Class counts inside the approximate box below cover 26,898 pixels. The box is lon 113.5 to 114.6, lat −3.6 to −1.9; the analysis itself uses the district polygon.

| Day | Sensor | 3 water | 4 cloud | 5 clear land | 7 fire low | 8 fire nominal | 9 fire high |
|---|---|---|---|---|---|---|---|
| 2019-09-15 | Aqua | 3,703 | 0 | 22,932 | 44 | 163 | 56 |
| 2019-09-15 | Terra | 4,403 | 0 | 22,278 | 29 | 99 | 89 |
| 2019-12-15 (decoder check, outside every registered period) | Aqua | 277 | 15,243 | 11,378 | 0 | 0 | 0 |
| 2019-12-15 (decoder check) | Terra | 1,253 | 19,787 | 5,858 | 0 | 0 | 0 |

File checksums (sha256):
- MYD14A1 A2019257: `cfd3bf586fb6ff9f30e417b078d0d51cf6311995e165279032961351343c2628`
- MOD14A1 A2019257: `7ed5ca8b462dd5394033bcec69352b1af7df62096b92fe6ebf2b531540c4dbe1`

## 3. What this means for the design

**Decoding works.** Classes 3, 4, 5, and 7 to 9 are read as expected. The cloud class appears on the wet-season check day.

**Open design question for the team, to settle before Release `prereg-v1`:**
- On 2019-09-15, a smoky peak-season day, no box pixel was cloud in either Terra or Aqua.
- This one day is **not** a season statistic, but the mechanism is general:
  - the daily composite keeps the **highest** class of all passes that day, including the night pass;
  - one clear pass therefore makes the cell-day "clear";
  - thick smoke is largely transparent in the thermal channels used at night.
- So with daily composites, `U` (untrusted zero) may be rarer during smoky dry-season weeks than the "smoke hides the ground" story assumes.

Options:
1. **Keep the registered daily-composite definition.** Report `X_season` whatever it is; the plan already sets no expected value. This is the honest default.
2. **Add a per-pass analysis** from swath products (VNP14IMG fire mask per granule, MOD14/MYD14 per granule). Day and night passes would then be scored separately. More work, but it shows when daytime smoke is flagged as cloud.
3. **Shift the story weight** from smoke to cloud, toward the months and districts where whole-day cloud is common.

Whichever option is chosen, it is written into `PREREGISTRATION.md` **before** the Release, not after seeing season results.

**Decision (14 November 2026): option 1.** The daily-composite definition is kept and recorded in `PREREGISTRATION.md`, section 9.

## 4. VIIRS (VNP14A1 / VJ114A1): not yet tested

- **Not tested yet.** Both are only on LP DAAC, which needs a NASA Earthdata Login. A team member signs in themselves, either with an `earthaccess.login()` prompt or a `.netrc` file on their own machine, or uses Google Earth Engine (`NASA/VIIRS/002/VNP14A1`).
- **Reading the files:** the `.h5` format can be read with `h5py`, which is already installed on this machine.
- **Next step:** one VNP14A1 file for 2019-09-15, h29v09, decoded with the same class table.
