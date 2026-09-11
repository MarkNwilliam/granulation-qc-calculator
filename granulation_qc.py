"""Granulation QC calculator for in process particle size and flowability.

Pure python, no dependencies. Mirror of the interactive dashboard at
https://marknwilliam.github.io/granulation-qc-calculator/
"""
from decimal import Decimal, ROUND_HALF_UP
import math

ORDER = ("above20", "above40", "above60", "above80", "above100", "below100")
SIEVE_BANDS = (("Above 20#", "above20"), ("Above 40#", "above40"),
               ("Above 60#", "above60"), ("Above 80#", "above80"),
               ("Above 100#", "above100"), ("Below 100#", "below100"))

RATINGS = ("Excellent", "Good", "Fair", "Passable", "Poor",
           "Very poor", "Very, very poor")

CARR_MAX = (10, 15, 20, 25, 31, 37, None)
HAUSNER_MAX = (1.11, 1.18, 1.25, 1.34, 1.45, 1.59, None)

OUTLOOK = {
    "Excellent": "expect smooth, consistent compression with minimal tooling adjustment",
    "Good": "expect even die filling and little weight fluctuation during compression",
    "Fair": "flow is acceptable but expect moderate tooling adjustment; monitor tablet weight variation closely during compression",
    "Passable": "bulk flow is sluggish; plan to use a force feeder and watch weight variation and sticking during compression",
    "Poor": "higher risk of capping, lamination and weight variation; consider a glidant or re granulation before compression",
    "Very poor": "feeding problems and weight variation are likely; re granulation or a binder change should come first",
    "Very, very poor": "high risk of capping, lamination, or weight variation; consider re granulation or reformulation before proceeding",
}


def _rhu(x, nd):
    q = Decimal("1") if nd == 0 else Decimal("0." + "0" * nd)
    snapped = Decimal(str(round(float(x), 12)))
    return float(snapped.quantize(q, rounding=ROUND_HALF_UP))


def fmt(x, nd):
    return f"{_rhu(x, nd):.{nd}f}"


def _severity(name):
    return RATINGS.index(name)


def rat(e_percent):
    """Carr's index flow rating from the USP and Ph. Eur. table."""
    for idx, mx in enumerate(CARR_MAX):
        if mx is not None and e_percent <= mx:
            return RATINGS[idx]
    return RATINGS[-1]


def rat_h(hausner):
    """Hausner ratio flow rating from the USP and Ph. Eur. table."""
    for idx, mx in enumerate(HAUSNER_MAX):
        if mx is not None and hausner <= mx:
            return RATINGS[idx]
    return RATINGS[-1]


def sieve_analysis(sample_g, retained):
    """Full section A run for a PSD set.

    retained maps the six keys to grams. Standard round half up is used, and
    the cumulative Above 60# / Below 60# figures sum the rounded whole-number
    individual percentages to match the plant batch record convention.
    """
    a = float(sample_g)
    g = {k: float(retained.get(k, 0.0)) for k in ORDER}
    if a <= 0:
        raise ValueError("Sample weight must be greater than zero")

    individual = {}
    for k in ORDER:
        pct = g[k] / a * 100.0
        individual[k] = {"pct1": _rhu(pct, 1), "whole": int(_rhu(pct, 0))}

    above60 = sum(individual[k]["whole"] for k in ("above20", "above40", "above60"))
    above60_precise = _rhu(sum(g[k] / a * 100.0 for k in ("above20", "above40", "above60")), 1)
    below60 = sum(individual[k]["whole"] for k in ("above80", "above100", "below100"))
    below60_precise = _rhu(sum(g[k] / a * 100.0 for k in ("above80", "above100", "below100")), 1)

    D = _rhu(sum(g.values()), 2)
    loss = _rhu(a - D, 2)
    C = _rhu(g["above80"] + g["above100"] + g["below100"], 2)
    fines_pct = _rhu(C / a * 100.0, 1)

    return {
        "individual": individual,
        "above60": above60, "above60_precise": above60_precise,
        "below60": below60, "below60_precise": below60_precise,
        "D": D, "loss": loss,
        "C": C, "fines_pct": fines_pct,
        "fines_diff_note": abs(below60 - fines_pct) > 1,
        "flags": {
            "above20": individual["above20"]["whole"] <= 15,
            "above60": above60 <= 35,
            "below60": 50 <= below60 <= 90,
        },
    }


def physical(bulk_density, tapped_density):
    """Carr's index and Hausner ratio with USP flow ratings."""
    b, t = float(bulk_density), float(tapped_density)
    if b <= 0 or t <= 0:
        raise ValueError("Densities must be greater than zero")
    carr = _rhu((t - b) / t * 100.0, 2)
    hausner = _rhu(t / b, 2)
    r_carr, r_hausner = rat(carr), rat_h(hausner)
    return {
        "carr": carr, "hausner": hausner,
        "rating_carr": r_carr, "rating_hausner": r_hausner,
        "worse": r_carr if _severity(r_carr) >= _severity(r_hausner) else r_hausner,
    }


def verdict(carr_rating, hausner_rating, fines_pct, above20_whole):
    """Plain language ease of compression verdict.

    Starts from the worse of the two USP flow ratings, downgrades once for
    fines outside 50 to 90% and once for above 20# above 15%, and clamps
    between the ends of the table.
    """
    level = max(_severity(carr_rating), _severity(hausner_rating))
    if not (50 <= fines_pct <= 90):
        level += 1
    if above20_whole > 15:
        level += 1
    level = max(0, min(6, level))
    name = RATINGS[level]
    return {"level": level, "rating": name, "outlook": OUTLOOK[name]}


def _risk_level(score):
    if score >= 5:
        return "High"
    if score >= 2:
        return "Moderate"
    return "Low"


def sticking_risk(lod, fines_pct, worse_rating, above20_whole, speed_pct):
    """Scored estimator for punch sticking and picking.

    speed_pct is planned output as a percent of the press rated output. The
    result is advisory, not a substitute for watching the first compression
    and checking the punch faces.
    """
    score, reasons = 0, []
    if lod < 1.0:
        score += 1; reasons.append("LOD below 1%, dry dust and electrostatic build up")
    elif lod > 2.5:
        score += 1; reasons.append("LOD above 2.5%, moist surface for sticking and picking")
    if fines_pct > 90:
        score += 1; reasons.append("fines above 90%, dust on the tooling")
    elif fines_pct < 50:
        score += 1; reasons.append("fines below 50%, uneven die fill")
    if _severity(worse_rating) >= 5:
        score += 1; reasons.append("very poor flow, weight variation on the feed")
    if above20_whole > 15:
        score += 1; reasons.append("oversize above 20# above 15%, irregular granules")
    if speed_pct >= 85:
        score += 1; reasons.append("output above 85% of press rating, short dwell")
    return {"level": _risk_level(score), "score": score, "reasons": reasons}


def capping_risk(lod, fines_pct, worse_rating, above20_whole, force_margin_pct):
    """Scored estimator for capping and lamination.

    force_margin_pct is the head room left on the press, from the planned
    compression force up to the press maximum.
    """
    score, reasons = 0, []
    if above20_whole > 15:
        score += 2; reasons.append("oversize above 20# above 15%, weak compaction lattice")
    if fines_pct < 50:
        score += 1; reasons.append("fines below 50%, poor particle bonding")
    if lod < 1.0:
        score += 1; reasons.append("overdry granulation, friable compact edge")
    if _severity(worse_rating) >= 5:
        score += 1; reasons.append("very poor compressibility, porous compact")
    if force_margin_pct < 10:
        score += 1; reasons.append("planned force within 10% of the press maximum")
    return {"level": _risk_level(score), "score": score, "reasons": reasons}


PRESSES = {
    "DLT 50/300/300": {"max_force_kn": 50.0, "rated_output_tph": 300000.0,
                       "max_tablet_mm": 30.0},
}

FLOW_SPEED = {"Excellent": 1.00, "Good": 0.95, "Fair": 0.80, "Passable": 0.65,
              "Poor": 0.50, "Very poor": 0.35, "Very, very poor": 0.25}

WEIGHT_RSD = {"Excellent": "up to 1.5%", "Good": "1.5 to 2.0%",
              "Fair": "2.0 to 3.0%", "Passable": "3.0 to 4.5%",
              "Poor": "4.5 to 6.0%", "Very poor": "above 6%, watch rejects",
              "Very, very poor": "above 6%, expect rejects"}

MODELS = (
    ("Carr compressibility index", "C = 100 (rhoT - rhoB) / rhoT",
     "flow and compressibility, read with USP 1174"),
    ("Hausner ratio", "H = rhoT / rhoB = 100 / (100 - C)",
     "flow, read with USP 1174"),
    ("Beverloo orifice flow", "W = C rhoB (D - k d)^2.5",
     "gravity die fill rate through the feed orifice"),
    ("Dwell time", "t = (contact angle / 360) x (60 / turret rpm)",
     "time under compression, falls as speed rises"),
    ("Heckel equation", "ln(1 / (1 - D)) = k P + A",
     "mean yield pressure Py = 1/k, deformation and capping tendency"),
    ("Ryshkewitch-Duckworth", "sigma = sigma0 exp(-b e)",
     "compact tensile strength against porosity, capping risk"),
    ("Leuenberger", "sigma = sigmaMax (1 - exp(-gamma P (1 - e)))",
     "compact strength from pressure and porosity"),
)


def speed_recommendation(worse_rating, rated_output_tph):
    """Permissible press speed from the flow character.

    Poor flow shortens the safe window for uniform die fill, so the press is
    run slower. Returns a band around the rated output of the machine.
    """
    factor = FLOW_SPEED[worse_rating]
    tpm = rated_output_tph / 60.0 * factor
    note = ("uniform die fill expected at this setting"
            if _severity(worse_rating) <= 2 else
            "slow the turret further if weight or thickness drifts")
    return {"factor": factor, "percent_of_rating": round(factor * 100),
            "tpm": round(tpm), "tpm_low": round(tpm * 0.9),
            "tpm_high": round(tpm * 1.1), "note": note}


def lod_advisory(lod):
    """Moisture window advice and corrective actions, per granulation SOP."""
    if lod < 1.0:
        return {"level": "Low moisture, granulation too dry",
                "defects": ["capping and splitting of the tablet top",
                            "friability and pickup defects on takeoff"],
                "actions": ["bring the moisture back up, re humidify in the FBE or add a little water with mixing",
                            "shorten the drying step on the next batch",
                            "re sieve and re lubricate before compression"]}
    if lod <= 2.5:
        return {"level": "In the drying window",
                "defects": [],
                "actions": ["proceed to compression and keep the blend covered"]}
    return {"level": "High moisture, granulation too wet",
            "defects": ["sticking and picking on the punches",
                        "binding in the die cavity",
                        "lamination, tablets splitting in half"],
            "actions": ["re dry in the FBE to within the BMR limit",
                        "re sieve the dried granulation",
                        "re lubricate before compression"]}


def recommendations(worse_rating, lod, rated_output_tph, fines_pct):
    """Bundle the operational advice the dashboard prints."""
    speed = speed_recommendation(worse_rating, rated_output_tph)
    lodv = lod_advisory(lod)
    if _severity(worse_rating) >= 4:
        die_fill = ("uneven die fill is likely, expect weight and thickness "
                    "variation; use a force feeder and hold the lower speed")
    else:
        die_fill = "die fill should stay uniform at the recommended speed"
    return {"speed": speed, "weight": WEIGHT_RSD[worse_rating],
            "lod": lodv, "die_fill": die_fill}


def punch_area(diameter_mm):
    """Punch face area from the punch diameter, in square mm and square cm."""
    r = float(diameter_mm) / 2.0
    mm2 = math.pi * r * r
    return {"mm2": mm2, "cm2": mm2 / 100.0}


def dwell_time(alpha_deg, rpm):
    """Punch dwell time t = (contact angle / 360) x (60 / rpm)."""
    if rpm <= 0:
        raise ValueError("Turret speed must be greater than zero")
    seconds = (float(alpha_deg) / 360.0) * (60.0 / float(rpm))
    return {"seconds": seconds, "ms": seconds * 1000.0}


def heckel_pressure(solid_fraction, k, a):
    """Pressure to reach a relative density from the Heckel equation.

    ln(1 / (1 - D)) = k P + A, so P = (ln(1 / (1 - D)) - A) / k with k = 1/Py.
    """
    if not (0.0 < solid_fraction < 1.0):
        raise ValueError("Solid fraction must be between 0 and 1")
    if k <= 0:
        raise ValueError("Heckel k must be greater than zero")
    return (math.log(1.0 / (1.0 - float(solid_fraction))) - float(a)) / float(k)


def compression_force(pressure_mpa, area_mm2):
    """Force in kN from pressure in MPa (1 MPa = 1 N/mm2) and area in mm2."""
    return float(pressure_mpa) * float(area_mm2) / 1000.0


def compression_setting(diameter_mm=None, solid_fraction=None, heckel_k=None,
                        heckel_a=None, alpha_deg=None, rpm=None):
    """Optional compression setting.

    Every result stays None until its own inputs are present, so nothing is
    invented from data the plant does not hold.
    """
    out = {"area_mm2": None, "area_cm2": None, "pressure_mpa": None,
           "force_kn": None, "dwell_ms": None}
    if diameter_mm:
        a = punch_area(diameter_mm)
        out["area_mm2"], out["area_cm2"] = a["mm2"], a["cm2"]
    if solid_fraction is not None and heckel_k is not None and heckel_a is not None:
        out["pressure_mpa"] = heckel_pressure(solid_fraction, heckel_k, heckel_a)
    if out["pressure_mpa"] is not None and out["area_mm2"] is not None:
        out["force_kn"] = compression_force(out["pressure_mpa"], out["area_mm2"])
    if alpha_deg and rpm:
        out["dwell_ms"] = dwell_time(alpha_deg, rpm)["ms"]
    return out