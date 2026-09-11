import unittest

import granulation_qc as g


class Rounding(unittest.TestCase):
    def test_round_half_up_two_decimal(self):
        self.assertEqual(g.fmt(71.749999999, 2), "71.75")

    def test_round_half_up_one_decimal(self):
        self.assertEqual(g.fmt(1.34, 1), "1.3")
        self.assertEqual(g.fmt(14.66, 1), "14.7")
        self.assertEqual(g.fmt(63.0, 1), "63.0")

    def test_whole_round_half_up(self):
        self.assertEqual(g._rhu(14.66, 0), 15)
        self.assertEqual(g._rhu(8.17, 0), 8)
        self.assertEqual(g._rhu(62.98, 0), 63)


class SieveAnalysis(unittest.TestCase):
    def setUp(self):
        self.ret = {"above20": 1.34, "above40": 14.66, "above60": 8.17,
                    "above80": 6.29, "above100": 2.48, "below100": 62.98}

    def test_individual_pct(self):
        r = g.sieve_analysis(100.00, self.ret)
        self.assertEqual(r["individual"]["above20"]["pct1"], 1.3)
        self.assertEqual(r["individual"]["above20"]["whole"], 1)
        self.assertEqual(r["individual"]["above40"]["pct1"], 14.7)
        self.assertEqual(r["individual"]["above40"]["whole"], 15)
        self.assertEqual(r["individual"]["above60"]["pct1"], 8.2)
        self.assertEqual(r["individual"]["above60"]["whole"], 8)
        self.assertEqual(r["individual"]["above80"]["pct1"], 6.3)
        self.assertEqual(r["individual"]["above80"]["whole"], 6)
        self.assertEqual(r["individual"]["above100"]["pct1"], 2.5)
        self.assertEqual(r["individual"]["above100"]["whole"], 2)
        self.assertEqual(r["individual"]["below100"]["pct1"], 63.0)
        self.assertEqual(r["individual"]["below100"]["whole"], 63)

    def test_above_60_cumulative_uses_rounded_wholes(self):
        r = g.sieve_analysis(100.00, self.ret)
        self.assertEqual(r["above60"], 24)
        self.assertEqual(r["below60"], 71)

    def test_precise_sums(self):
        r = g.sieve_analysis(100.00, self.ret)
        self.assertEqual(r["above60_precise"], 24.2)
        self.assertEqual(r["below60_precise"], 71.8)

    def test_D_and_loss(self):
        r = g.sieve_analysis(100.00, self.ret)
        self.assertEqual(r["D"], 95.92)
        self.assertEqual(r["loss"], 4.08)

    def test_fines_box(self):
        r = g.sieve_analysis(100.00, self.ret)
        self.assertEqual(r["C"], 71.75)
        self.assertEqual(r["fines_pct"], 71.8)
        self.assertFalse(r["fines_diff_note"])

    def test_flags_pass(self):
        r = g.sieve_analysis(100.00, self.ret)
        self.assertTrue(r["flags"]["above20"])
        self.assertTrue(r["flags"]["above60"])
        self.assertTrue(r["flags"]["below60"])

    def test_above_20_fail(self):
        ret = dict(self.ret); ret["above20"] = 15.5
        r = g.sieve_analysis(100.00, ret)
        self.assertFalse(r["flags"]["above20"])

    def test_above_60_fail(self):
        ret = dict(self.ret); ret["above20"] = 30.0
        r = g.sieve_analysis(100.00, ret)
        self.assertFalse(r["flags"]["above60"])

    def test_below_60_out_of_range(self):
        ret = dict(self.ret); ret["below100"] = 130.0
        r = g.sieve_analysis(150.0, ret)
        self.assertFalse(r["flags"]["below60"])

    def test_retained_more_than_sample_flags_loss(self):
        ret = {"above20": 10, "above40": 10, "above60": 10,
               "above80": 10, "above100": 10, "below100": 60}
        r = g.sieve_analysis(90.0, ret)
        self.assertEqual(r["loss"], -20.0)

    def test_bad_sample_rejected(self):
        with self.assertRaises(ValueError):
            g.sieve_analysis(0, self.ret)

    def test_fines_note_when_roundings_diverge(self):
        ret = {"above20": 0.0, "above40": 0.0, "above60": 0.0,
               "above80": 6.49, "above100": 2.49, "below100": 49.49}
        r = g.sieve_analysis(100.00, ret)
        self.assertTrue(r["fines_diff_note"])


class Physical(unittest.TestCase):
    def test_carr_and_hausner(self):
        r = g.physical(0.52, 0.74)
        self.assertEqual(r["carr"], 29.73)
        self.assertEqual(r["hausner"], 1.42)

    def test_ratings_usp(self):
        r = g.physical(0.52, 0.74)
        self.assertEqual(r["rating_carr"], "Poor")
        self.assertEqual(r["rating_hausner"], "Poor")
        self.assertEqual(r["worse"], "Poor")

    def test_excellent(self):
        r = g.physical(0.60, 0.70)
        self.assertEqual(r["rating_carr"], "Good")
        self.assertEqual(r["rating_hausner"], "Good")
        self.assertEqual(r["worse"], "Good")

    def test_excellent_band(self):
        r = g.physical(0.62, 0.66)
        self.assertEqual(r["rating_carr"], "Excellent")
        self.assertEqual(r["rating_hausner"], "Excellent")

    def test_bad_density_rejected(self):
        with self.assertRaises(ValueError):
            g.physical(0, 0.7)


class Verdict(unittest.TestCase):
    def test_worked_example_poor(self):
        v = g.verdict("Poor", "Poor", 71.8, 1)
        self.assertEqual(v["level"], 4)
        self.assertEqual(v["rating"], "Poor")
        self.assertIn("capping", v["outlook"])

    def test_fines_below_50_downgrades(self):
        v = g.verdict("Good", "Good", 49.0, 0)
        self.assertEqual(v["rating"], "Fair")

    def test_fines_above_90_downgrades(self):
        v = g.verdict("Good", "Good", 91.0, 0)
        self.assertEqual(v["rating"], "Fair")

    def test_above_20_downgrades(self):
        v = g.verdict("Good", "Good", 70.0, 16)
        self.assertEqual(v["rating"], "Fair")

    def test_clamp_at_bottom(self):
        v = g.verdict("Very, very poor", "Very, very poor", 10.0, 30)
        self.assertEqual(v["rating"], "Very, very poor")

    def test_clamp_at_top(self):
        v = g.verdict("Excellent", "Excellent", 70.0, 0)
        self.assertEqual(v["rating"], "Excellent")

    def test_worse_of_two_drives(self):
        v = g.verdict("Good", "Passable", 70.0, 0)
        self.assertEqual(v["rating"], "Passable")


if __name__ == "__main__":
    unittest.main()