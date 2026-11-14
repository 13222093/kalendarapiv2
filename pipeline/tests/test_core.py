"""Unit tests for the FireMask cell-day pipeline (no network).

Run from the repository root:  python -I pipeline/tests/test_core.py -v
"""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kapi import firemask, grid, guard, polygon, states  # noqa: E402

SQUARE = [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]
HOLE = [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5], [0.5, 0.5]]


def feature(coords, kind="Polygon", name="Test"):
    return {"type": "Feature", "properties": {"shapeName": name}, "geometry": {"type": kind, "coordinates": coords}}


class GridTests(unittest.TestCase):
    def test_pulang_pisau_is_in_h29v09(self):
        self.assertEqual(grid.tile_of(114.0, -2.8), (29, 9))

    def test_pixel_centre_round_trip(self):
        lon, lat = grid.pixel_centers(29, 9, [500], [700])
        r, c = grid.pixel_of(lon, lat, 29, 9)
        self.assertEqual((int(r[0, 0]), int(c[0, 0])), (500, 700))

    def test_tiles_for_small_box(self):
        self.assertEqual(grid.tiles_for_bbox(113.6, -3.4, 114.4, -2.0), [(29, 9)])

    def test_pixel_size(self):
        self.assertAlmostEqual(grid.SIZE, 926.625433, places=4)


class PolygonTests(unittest.TestCase):
    def test_square(self):
        rs = polygon.rings(feature([SQUARE]))
        got = polygon.contains(rs, np.array([1.0, 3.0, -0.1]), np.array([1.0, 1.0, 1.0]))
        self.assertEqual(got.tolist(), [True, False, False])

    def test_hole(self):
        rs = polygon.rings(feature([SQUARE, HOLE]))
        got = polygon.contains(rs, np.array([1.0, 0.25]), np.array([1.0, 0.25]))
        self.assertEqual(got.tolist(), [False, True])

    def test_multipolygon(self):
        far = [[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]
        rs = polygon.rings(feature([[SQUARE], [far]], kind="MultiPolygon"))
        got = polygon.contains(rs, np.array([1.0, 10.5, 5.0]), np.array([1.0, 10.5, 5.0]))
        self.assertEqual(got.tolist(), [True, True, False])

    def test_district_mask_area(self):
        # a 0.1 x 0.1 degree box at 2.8 S is about 123 km2, i.e. about 143 pixels of 0.8586 km2
        box = [[113.9, -2.85], [114.0, -2.85], [114.0, -2.75], [113.9, -2.75], [113.9, -2.85]]
        n = int(polygon.district_mask(feature([box]), 29, 9).sum())
        self.assertTrue(125 <= n <= 160, n)

    def test_load_feature_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "b.geojson"
            p.write_text(json.dumps({"type": "FeatureCollection", "features": [feature([SQUARE], name="Pulang Pisau")]}))
            self.assertEqual(polygon.load_feature(p, "pulang pisau")["properties"]["shapeName"], "Pulang Pisau")
            with self.assertRaises(ValueError):
                polygon.load_feature(p, "Kapuas")


class FireMaskTests(unittest.TestCase):
    def test_class_mapping(self):
        got = firemask.sensor_state(np.arange(10)).tolist()
        n, c, k, f, w = firemask.NODATA, firemask.CLEAR, firemask.CLOUD, firemask.FIRE, firemask.WATER
        self.assertEqual(got, [n, n, n, w, k, c, n, f, f, f])

    def test_class_counts(self):
        fm = np.array([[0, 3, 4, 5, 6, 7, 8, 9]])
        got = firemask.class_counts(fm, np.ones_like(fm, bool))
        self.assertEqual(got, {"fire": 3, "clear": 1, "cloud": 1, "water": 1, "unknown": 1, "not_processed": 1})

    def test_parse_dates(self):
        xml = '<GDALMetadata><Item name="Dates">2019-12-11 2019-12-12 2019-12-13</Item></GDALMetadata>'
        self.assertEqual(firemask.parse_dates(xml)[2], dt.date(2019, 12, 13))

    def test_viirs_h5_reader_finds_nested_firemask(self):
        try:
            import h5py
        except ImportError:
            self.skipTest("h5py not installed")
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "VNP14A1.A2018258.h29v09.002.0000000000000.h5"
            with h5py.File(p, "w") as f:
                f.create_dataset("HDFEOS/GRIDS/VIIRS_Grid/Data Fields/FireMask", data=np.full((4, 4), 5, np.uint8))
            self.assertEqual(int(firemask.viirs_h5_firemask(p).sum()), 80)
            self.assertEqual(firemask.viirs_file(d, "VNP14A1", dt.date(2018, 9, 15), 29, 9), p)
            self.assertIsNone(firemask.viirs_file(d, "VNP14A1", dt.date(2018, 9, 16), 29, 9))


S = firemask


class StateTests(unittest.TestCase):
    def cells(self, *sensor_values, k=1, firms=None, water=None):
        sensors = [np.array([v], np.uint8) for v in sensor_values]
        fm = None if firms is None else np.array([firms])
        wm = None if water is None else np.array([water])
        return int(states.combine(sensors, k, fm, wm)[0])

    def test_rules(self):
        self.assertEqual(self.cells(S.FIRE, S.CLEAR), states.F_)               # fire wins
        self.assertEqual(self.cells(S.CLOUD, S.CLOUD), states.U_)              # all cloud
        self.assertEqual(self.cells(S.CLOUD, S.NODATA), states.U_)             # cloud, no clear
        self.assertEqual(self.cells(S.CLEAR, S.CLOUD), states.T_)              # k = 1: one clear is enough
        self.assertEqual(self.cells(S.CLEAR, S.CLOUD, k=2), states.N_)         # k = 2: one clear is not enough
        self.assertEqual(self.cells(S.CLEAR, S.CLEAR, k=2), states.T_)
        self.assertEqual(self.cells(S.NODATA, S.NODATA), states.N_)
        self.assertEqual(self.cells(S.WATER, S.NODATA), states.N_)             # per-sensor water is not "clear"
        self.assertEqual(self.cells(S.CLEAR, water=True), states.W_)           # static water cell
        self.assertEqual(self.cells(S.FIRE, water=True), states.F_)            # fire evidence wins over water
        self.assertEqual(self.cells(S.CLOUD, firms=True), states.F_)           # FIRMS point makes it fire

    def test_k_must_be_positive(self):
        with self.assertRaises(ValueError):
            states.combine([np.zeros(1, np.uint8)], 0)

    def test_counts_and_blind_share(self):
        cells = np.array([states.F_, states.T_, states.T_, states.U_, states.N_, states.W_], np.uint8)
        c = states.counts(cells)
        self.assertEqual(c, {"F": 1, "T": 2, "U": 1, "N": 1, "W": 1})
        self.assertAlmostEqual(states.blind_share(c), 1 / 3)
        self.assertIsNone(states.blind_share({"F": 0, "T": 0, "U": 0, "N": 3, "W": 0}))
        self.assertEqual(states.letters(cells), "FTTUNW")

    def test_water_mask(self):
        wm = states.WaterMask((3,))
        for day in ([3, 5, 4], [3, 5, 3], [5, 5, 5]):
            wm.add(np.array(day))
        # cell 0: water 2x, clear 1x -> water; cell 1: never water; cell 2: water 1x, clear 1x (tie) -> water
        self.assertEqual(wm.mask().tolist(), [True, False, True])

    def test_water_mask_tie_counts_as_water(self):
        wm = states.WaterMask((1,))
        wm.add(np.array([3]))
        wm.add(np.array([5]))
        self.assertEqual(wm.mask().tolist(), [True])


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = pathlib.Path(self.tmp.name) / "REGISTRATION.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_unregistered_year_passes(self):
        self.assertIsNone(guard.check(dt.date(2018, 9, 1), dt.date(2018, 9, 30), self.reg, lambda u: None))

    def test_2019_refused_without_registration(self):
        with self.assertRaises(guard.NotRegisteredError):
            guard.check(dt.date(2019, 9, 1), dt.date(2019, 9, 30), self.reg, lambda u: None)

    def test_period_touching_2019_refused(self):
        with self.assertRaises(guard.NotRegisteredError):
            guard.check(dt.date(2018, 12, 30), dt.date(2019, 1, 2), self.reg, lambda u: None)

    def test_2019_allowed_after_published_release(self):
        self.reg.write_text(json.dumps({"repo": "owner/repo", "tag": "prereg-v1"}))
        rel = guard.check(dt.date(2019, 9, 1), dt.date(2019, 9, 30), self.reg,
                          lambda u: {"draft": False, "published_at": "2026-11-14T12:00:00Z", "html_url": "x"})
        self.assertEqual(rel["published_at"], "2026-11-14T12:00:00Z")

    def test_draft_or_unreachable_release_refused(self):
        self.reg.write_text(json.dumps({"repo": "owner/repo"}))
        for fake in (lambda u: {"draft": True, "published_at": None}, lambda u: None):
            with self.assertRaises(guard.NotRegisteredError):
                guard.check(dt.date(2019, 9, 1), dt.date(2019, 9, 30), self.reg, fake)


if __name__ == "__main__":
    unittest.main()
