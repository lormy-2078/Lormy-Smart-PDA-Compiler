"""
Provisional Port Stay auto-calculation for Takoradi dry bulk cargoes.

Days = Total Cargo Quantity (MT) / the cargo's typical discharge/load rate
(tonnes per day at Takoradi), rounded to the nearest whole day. These rates
are the company's own operating assumptions for Takoradi, not a GPHA
tariff figure -- they belong to Port of Call, since a different port's berths
and equipment give different rates (Tema is not yet configured).

"Other" cargo has no known rate here and needs a manually entered port stay.
"""

CARGO_STAY_RATES_TAKORADI = {
    "Bulk Clinker": 7000,
    "Bulk Gypsum": 7000,
    "Bulk Limestone": 7000,
    "Bulk Slag": 7000,
    "Bulk Quicklime": 2300,
    "Bulk Bauxite": 18000,
    "Bulk Manganese": 35000,
    "Bulk Wheat": 4000,
    "Bulk Cocoa": 5000,
    "Bagged Ammonium Nitrate": 1200,
}

CARGO_TYPES = list(CARGO_STAY_RATES_TAKORADI.keys()) + ["Other"]

OTHER_CARGO = "Other"


def is_auto_calculated(cargo_type: str) -> bool:
    return cargo_type in CARGO_STAY_RATES_TAKORADI


def auto_port_stay_days(cargo_type: str, cargo_qty_mt: float):
    """The automatically-calculated provisional port stay (whole days) for a
    known Takoradi cargo, or None if that cargo has no standard discharge rate.
    Always available regardless of any manual override -- the auto figure is
    preserved and shown even when the user enters days manually."""
    rate = CARGO_STAY_RATES_TAKORADI.get(cargo_type)
    if rate and cargo_qty_mt:
        return float(round(cargo_qty_mt / rate))
    return None


def compute_port_stay_days(cargo_type: str, cargo_qty_mt: float, manual_days: float = 0) -> float:
    """The EFFECTIVE port stay used for pricing and Harbour Rent.

    A manual override (manual_days > 0) always wins -- for known cargoes too --
    giving the user freedom to enter the days themselves; the auto calculation
    is still preserved via auto_port_stay_days(). When no override is given, the
    auto figure is used (or 0 if the cargo has no standard rate and nothing was
    entered). Rounded to whole days per the company's convention.
    """
    manual = float(manual_days or 0)
    if manual > 0:
        return manual  # respect the user's exact entry (may be a half-day)
    auto = auto_port_stay_days(cargo_type, cargo_qty_mt)
    return auto if auto is not None else 0.0
