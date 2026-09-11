"""Granulation QC calculator for in process particle size and flowability.

Pure python, no dependencies. Mirror of the interactive dashboard at
https://marknwilliam.github.io/granulation-qc-calculator/
"""
from decimal import Decimal, ROUND_HALF_UP

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