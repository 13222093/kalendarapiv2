# KalenderApi: pre-registration

**Status: FINAL DRAFT (14 November 2026). All thresholds confirmed by the team. Not yet registered.**

This plan becomes binding when it is published as the GitHub Release `prereg-v1`. The Release's server timestamp is the proof that the plan came before the results.

What is left before that Release: put this folder in a GitHub repository, publish the Release, and change this status line to "Registered as Release `prereg-v1` on {date}".

Until the Release exists, this project computes no season-level statistic. Section 9, "Access tests before registration", lists everything opened before then. It also discloses a season-level visibility layer that the team's separate v1.0 project had already built.

Spec: the team's internal product spec, PRD v1.1 (sections 5, 6.6, 6.7, 9, 10). It is not part of this repository.

---

## 1. Questions and hypotheses

**Main question.** During Pulang Pisau's 2019 peat-fire season (1 August to 31 October 2019), how many of the satellite record's zero-fire cell-days were actually observed, and how much fire did the record likely miss?

| ID | Hypothesis or quantity | Type |
|---|---|---|
| Q1 | Share of zero-fire cell-days that no satellite saw clearly (`X_season`) | Descriptive. No expected value is set, and the number is reported whatever it is |
| H2 | Our cell-day estimator recovers artificially hidden fire better than simple baselines, with calibrated 90% intervals | Pass/fail (section 5) |
| H3 | Our MODIS-to-VIIRS harmonization beats one global factor on held-out years | Pass/fail (section 6) |
| H4 | Fire re-appears near earlier fire after cloud/smoke gaps more often than after equally long clear gaps | Pass/fail (section 7). A claim is shown only if it passes |

---

## 2. Data

| Product | Version | DOI | Use |
|---|---|---|---|
| MOD14A1 (Terra) | 6.1 | 10.5067/MODIS/MOD14A1.061 | Daily FireMask, 1 km |
| MYD14A1 (Aqua) | 6.1 | 10.5067/MODIS/MYD14A1.061 | Daily FireMask, 1 km |
| VNP14A1 (Suomi NPP) | 2 | 10.5067/VIIRS/VNP14A1.002 | Daily FireMask, 1 km |
| VJ114A1 (NOAA-20) | 2 | 10.5067/VIIRS/VJ114A1.002 | Sensitivity only, if obtained |
| MCD14ML | 6.1 | 10.5067/FIRMS/MODIS/MCD14ML | Fire points, harmonization |
| VNP14IMG | 2 | 10.5067/VIIRS/VNP14IMG.002 | 375 m fire points |
| MCD19A2 (MAIAC AOD) | 6.1 | 10.5067/MODIS/MCD19A2.061 | Smoke-day rule (section 5.4) |

- **Area:** Pulang Pisau regency, Central Kalimantan, using the geoBoundaries IDN ADM2 polygon (version and download date recorded in the data contract). MODIS/VIIRS sinusoidal tile **h29v09**. Replication: Ogan Komering Ilir (OKI), September 2019, Q1 statistics only.
- **Period:** 1 August to 31 October 2019. Section 5.5 also uses 1 January to 31 March 2019, and section 6 uses 2002 to 2022.
- **Provenance:** for every file, the data contract records the product, version, file name, download date, row or pixel count, and sha256.

---

## 3. Definitions

### 3.1 Cells and FireMask classes

- **Cell:** one pixel of the 1 km sinusoidal grid shared by MOD14A1, MYD14A1, and VNP14A1, whose centre falls inside the district polygon.
- **Cell-day:** one cell on one calendar day. Per sensor, each daily FireMask class maps as follows:

| FireMask class | Meaning | Per-sensor state |
|---|---|---|
| 7, 8, 9 | fire (low, nominal, high) | fire |
| 5 | non-fire land | clear |
| 4 | cloud | cloud |
| 3 | non-fire water | **excluded from all denominators** |
| 6 | unknown | no data (its share is reported) |
| 0, 1, 2 | not processed | no data |

- **Composites:** daily FireMask composites keep the highest class of the day and include night passes. This is stated wherever pass times are shown.

### 3.2 Cell-day state, sensors Terra, Aqua, and S-NPP

| State | Rule |
|---|---|
| `F` | at least one sensor is *fire*, or a FIRMS fire point (MCD14ML or VNP14IMG) falls in the cell that day |
| `T` | not `F`, and at least **k** sensors are *clear* |
| `U` | not `F`, no sensor is *clear*, and at least one sensor is *cloud* |
| `N` | everything else |

- **Threshold:** **k = 1** is primary; **k = 2** is reported as sensitivity.
- **FIRMS-only fires:** the share of `F` cell-days that come only from FIRMS points (no FireMask fire class) is reported.

### 3.3 Statistics (all written to `numbers.json`)

- **`X_season`** = U / (T + U), pooled over all cell-days in the district from 1 August to 31 October 2019. Reported with the daily median and IQR of the same ratio, for k = 1 and k = 2. **This is the headline number.**
- **`X_day`:** the "least-seen day" is the day with the highest daily U / (T + U) among days with at least one `F` cell within ±3 days. It is always labelled "the day with the least ground seen (chosen as the maximum)" and never shown without `X_season`.
- **`Y` (co-visibility):** among cell-days with a usable observation from at least one MODIS and one VIIRS sensor, the share where exactly one of {MODIS, VIIRS} was *clear*.

---

## 4. Order of work

1. Publish this plan as Release `prereg-v1`.
2. Build cell-day states and compute Q1 for Pulang Pisau and OKI.
3. Run the tests in sections 5 to 7.
4. Publish every result, including failures.

---

## 5. H2: artificial-cloud test of the hidden-fire estimator

The design follows Schroeder et al. 2008 (doi 10.1016/j.rse.2007.05.004), which is cited wherever results are shown.

### 5.1 Pairs

- **Target day:** a district-day in August to October 2019 with U / (T + U) < **0.20**.
- **Donor mask:** the set of `U` cells on any other day of 2019 (any month) on which `U` covers at least **10%** of the district's non-water cells. Only the shape of the mask is borrowed. Donors are not limited to the fire season because the access test (section 9) showed that daily composites can have almost no `U` cells in the dry season.
- **Pair:** pasting a donor mask onto a target day hides the target's states in those cells. The truth is the number of `F` cell-days hidden by the mask.
- **Sample:** **500** random target × donor pairs with seed **2026**, sampled without replacement. If fewer pairs exist, all of them are used.

### 5.2 Methods compared

| ID | Method | Estimate of hidden `F` |
|---|---|---|
| `zero` | Treat as zero | 0 |
| `area_scale` | Scale by clear area (kiln-watch legacy) | visible F × (masked cells / visible non-N cells) |
| `giglio2006` | Giglio et al. 2006, at its native 0.5° monthly scale | counts scaled by 1 / (1 − cloud fraction) per 0.5° cell, apportioned to the masked cells |
| `era5_factor` | ERA5-based factor (flare-chronos) | run only if ERA5 is obtained in time; otherwise reported as "not run" |
| `cellday` | Ours | see below |

The `cellday` model is a logistic regression, fit leave-one-day-out on August to October 2019 cell-days. Its features are:
- number of `F` days in the same cell within ±3 days, excluding the target day;
- number of visible `F` cells among the 8 neighbours on the target day;
- peat flag (Miettinen 2016);
- day of season.

The point estimate is the sum of the predicted probabilities over the masked cells. The 90% interval comes from the Poisson-binomial distribution of those probabilities, combined with a bootstrap over days (200 replicates, seed 2026).

### 5.3 Metrics and pass rule

- **Metrics:** per pair, the error (estimate − truth). Per method: MAE and bias. For methods that give intervals: coverage90, the share of pairs whose truth lies inside the 90% interval.
- **H2 passes in a stratum** if both hold:
  - **Accuracy:** `cellday` MAE is lower than the MAE of **every** baseline that was run (`zero`, `area_scale`, `giglio2006`, and `era5_factor` if run). Against the best of those baselines, the 95% paired bootstrap interval of the difference (baseline MAE − `cellday` MAE) lies above 0. The bootstrap resamples target days, so pairs that share a day stay together (2,000 replicates, seed 2026). The percentage improvement is reported.
  - **Calibration:** `cellday` coverage90 is between **0.85 and 0.95**.
- **Strata:**
  - (a) all pairs;
  - (b) smoke days, meaning the target day is a smoke day (section 5.4);
  - (c) clear-neighbour cells, meaning masked cells with at least one visible neighbour.
- **Consequence:** if `cellday` fails in a stratum, the app shows "Estimate withheld: failed pre-registered test" for that stratum. If another method wins a stratum, that is shown.

### 5.4 Smoke-day rule

- **Rule:** a day is a smoke day if both hold:
  - at least **10%** of the district's cells have a valid best-quality MAIAC AOD retrieval at 550 nm (MCD19A2, Optical_Depth_055);
  - the mean of those valid retrievals is at least **1.0**.
- **Days with valid retrievals in fewer than 10% of cells are "unclassified".** They are left out of stratum (b), and their number is reported. MAIAC often fails under the thickest smoke, so this count is part of the result.
- **If MCD19A2 cannot be obtained before the run,** stratum (b) is dropped. The claim "smoke days scored separately" is then removed from every text. No substitute date range is used.
- **Known limitation, always stated:** pasted clouds fall at random with respect to fire (missing at random). Real cloud and smoke over peat do not.

### 5.5 Placebo checks

- **Primary:** pairs whose masked area contains no `F` cells (known zeros). Passes if the `cellday` 90% interval contains 0 in at least **90%** of those pairs.
- **Supporting:** run the estimator on the wet season, 1 January to 31 March 2019. The result is reported as a sanity check, not as pass/fail.

---

## 6. H3: harmonization held-out test

**Model** (PRD M6, as built by the team pipeline):
- monthly fire cell-days on a 0.1° grid per district;
- MODIS (Terra + Aqua) converted to the VIIRS S-NPP scale;
- fitted on February 2012 to December 2022.

**Held-out design:** leave-one-year-out over 2012 to 2022. For each held-out year, the model is fit on the other years and predicts that year's monthly VIIRS-scale counts from MODIS. The predictions are compared with observed S-NPP counts.

**Baselines:**
- one global factor (total VIIRS ÷ total MODIS over the training years);
- raw MODIS.

**Metric:** MAE of monthly district counts, over all districts shown in the calendar.

**H3 passes if** both hold:
- the pooled MAE across all held-out years is lower for our model than for the global factor;
- our MAE is lower than the global factor's in each of the two fire years, 2015 and 2019.

**Before 2012:** values from 2002 to 2011 are labelled "extrapolated". Their 90% range is widened by the spread (5th to 95th percentile) of the annual VIIRS/MODIS ratios in the training years.

**Comparison:** the Fire Harmony v1.0 series is shown as a labelled comparison line. It is not part of the test.

---

## 7. H4: re-appearance after gaps

- **Event:** cell *c* is `F` on day *d0*. On days *d0+1 … d0+L* (L ≥ 1), cell *c* is not `F` and is `U` on every day of the run.
- **Re-appearance:** any cell within Chebyshev distance 2 of *c* is `F` on day *d0+L+1*.
- **Null:** the same definition with `T` runs instead of `U` runs.
- **Test:** the re-appearance rate after `U` runs is compared with the rate after `T` runs. Runs are matched by L (1, 2, 3, 4 or more). The test is a one-sided permutation test that shuffles labels within strata of L (1,000 permutations, seed 2026).
- **H4 passes** if p < **0.05**.
- **If H4 fails:** the "re-appeared" rings and the count `r` are not shown; "Play the season" plays the data without them. Whatever the result, `r` and `r_clear` are recorded in `numbers.json`.

---

## 8. Reporting rules

- **All results are published,** including every FAIL and every "not run".
- **Any change after the Release** is logged under "Deviations" below, with date, reason, and the commit that made it. The registered text itself is never edited.
- **Words never used for these results:** "first", "predict", "real-time", "the fire never went out", "spread" (as a claim).

---

## 9. Access tests before registration

These were done to check that the data can be read. None of them computes a season-level statistic.

| Date | What | Result |
|---|---|---|
| 2026-11-14 | NASA CMR metadata search for MOD14A1.061, MYD14A1.061, VNP14A1.002, and VJ114A1.002 over Pulang Pisau on 2019-09-15 | One granule each, all on tile h29v09. LP DAAC files require Earthdata Login |
| 2026-11-14 | Decode the MOD14A1 and MYD14A1 FireMask for one day (2019-09-15) from the public Planetary Computer copy, plus one decoder check day outside every registered period (2019-12-15) | Decoding works. Details in `pipeline/ACCESS_TEST.md` |
| 2026-11-14 | VNP14A1 / VJ114A1 | Not tested: needs NASA Earthdata Login |

**Disclosure: an earlier season-level visibility layer exists.**
- On 14 November 2026 at about 02:12 UTC, before this plan was registered, the team's separate v1.0 project (`kalenderapi/`, built from PRD v1.0) ran `kalenderapi/scripts/build_visibility.py`.
- That script computed a MODIS-only (Terra + Aqua) visibility layer for the 14 districts of Central Kalimantan, 1 August to 31 October 2019, including season totals and per-district totals. Pulang Pisau is one of those districts.
- Its outputs are `visibility_kalteng_2019.json` and `vis2019/*.png`. They were copied into this folder with the rest of the v1.0 app, and they are added to this repository only **after** the registration commit.
- The authors of this plan had access to that layer before registration. This plan differs from it: it adds S-NPP, uses the district polygon on the 1 km grid, and defines `T`, `U`, `N` with k sensors. Q1 is descriptive and has no pass/fail rule.
- The thresholds for H2, H3, and H4 were set on 14 November 2026. The rule for donor masks (section 5.1) was based on the one-day access test above, not on that layer's totals.

**Design question raised by the access test, to settle before the Release** (details in `pipeline/ACCESS_TEST.md`, section 3):
- Daily FireMask composites keep the highest class of all passes, including night.
- On the one peak-season day decoded, no box pixel was cloud.
**Decision (14 November 2026, before registration): keep the daily-composite definition of `U` (section 3.2).**
- No per-pass analysis is added.
- `X_season` is reported whatever it turns out to be.
- `U` means the ground was unseen on every pass that day, whether because of cloud or smoke. Texts therefore say "cloud or smoke", and say "smoke" alone only where the true-colour image of that day shows smoke.

---

## Deviations

None yet.
