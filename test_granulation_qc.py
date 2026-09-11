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


class Risk(unittest.TestCase):
    def test_worked_example_sticking_low(self):
        # QK260454; LOD 0.96 is dry so one point, everything else quiet.
        r = g.sticking_risk(0.96, 71.8, "Poor", 1, 80.0)
        self.assertEqual(r["level"], "Low")
        self.assertEqual(r["score"], 1)
        self.assertTrue(any("LOD below 1%" in x for x in r["reasons"]))

    def test_worked_example_capping_low(self):
        r = g.capping_risk(0.96, 71.8, "Poor", 1, 60.0)
        self.assertEqual(r["level"], "Low")

    def test_sticking_high_when_all_factors_pile(self):
        r = g.sticking_risk(0.5, 95.0, "Very poor", 16, 90.0)
        self.assertEqual(r["level"], "High")

    def test_sticking_moderate_boundary(self):
        r = g.sticking_risk(0.96, 71.8, "Poor", 1, 90.0)
        self.assertEqual(r["level"], "Moderate")

    def test_sticking_wet_high_lod(self):
        r = g.sticking_risk(2.6, 71.8, "Good", 1, 50.0)
        self.assertEqual(r["score"], 1)
        self.assertTrue(any("LOD above 2.5%" in x for x in r["reasons"]))

    def test_capping_high_when_oversized(self):
        r = g.capping_risk(0.96, 40.0, "Very poor", 16, 5.0)
        self.assertEqual(r["level"], "High")

    def test_capping_oversize_is_double_point(self):
        r = g.capping_risk(1.5, 60.0, "Good", 16, 50.0)
        self.assertEqual(r["score"], 2)

    def test_capping_force_margin_trip(self):
        r = g.capping_risk(1.5, 60.0, "Good", 1, 8.0)
        self.assertEqual(r["level"], "Low")
        self.assertEqual(r["score"], 1)

    def test_risk_levels(self):
        self.assertEqual(g._risk_level(0), "Low")
        self.assertEqual(g._risk_level(2), "Moderate")
        self.assertEqual(g._risk_level(5), "High")


class Recommendations(unittest.TestCase):
    def test_press_profile_dlt(self):
        p = g.PRESSES["DLT 50/300/300"]
        self.assertEqual(p["max_force_kn"], 50.0)
        self.assertEqual(p["rated_output_tph"], 300000.0)

    def test_speed_poor_flow_halves_output(self):
        s = g.speed_recommendation("Poor", 300000)
        self.assertEqual(s["percent_of_rating"], 50)
        self.assertEqual(s["tpm"], 2500)
        self.assertEqual(s["tpm_low"], 2250)
        self.assertEqual(s["tpm_high"], 2750)

    def test_speed_excellent_flow_full_output(self):
        s = g.speed_recommendation("Excellent", 300000)
        self.assertEqual(s["tpm"], 5000)
        self.assertEqual(s["percent_of_rating"], 100)

    def test_lod_low_moisture_advice(self):
        a = g.lod_advisory(0.96)
        self.assertIn("Low moisture", a["level"])
        self.assertTrue(any("capping" in d for d in a["defects"]))
        self.assertTrue(any("humidify" in x for x in a["actions"]))

    def test_lod_in_window(self):
        a = g.lod_advisory(1.5)
        self.assertIn("window", a["level"])
        self.assertEqual(a["defects"], [])

    def test_lod_high_moisture_advice(self):
        a = g.lod_advisory(3.0)
        self.assertIn("High moisture", a["level"])
        self.assertTrue(any("sticking" in d for d in a["defects"]))
        self.assertTrue(any("re dry" in x for x in a["actions"]))

    def test_recommendations_bundle_poor(self):
        r = g.recommendations("Poor", 0.96, 300000, 71.8)
        self.assertEqual(r["speed"]["tpm"], 2500)
        self.assertEqual(r["weight"], "4.5 to 6.0%")
        self.assertIn("uneven die fill", r["die_fill"])

    def test_recommendations_bundle_good(self):
        r = g.recommendations("Good", 1.5, 300000, 71.8)
        self.assertIn("uniform", r["die_fill"])

    def test_models_list(self):
        names = [m[0] for m in g.MODELS]
        self.assertIn("Heckel equation", names)
        self.assertIn("Ryshkewitch-Duckworth", names)
        self.assertIn("Beverloo orifice flow", names)
        self.assertEqual(len(g.MODELS), 7)


if __name__ == "__main__":
    unittest.main()