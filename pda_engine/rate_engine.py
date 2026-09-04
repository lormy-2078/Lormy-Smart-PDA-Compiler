"""
Rate engine -- turns a call's drivers (GRT, cargo tonnage, days, movements...)
into priced PDA line items using the active rate_table rows for the call's
port/cargo/vessel type. All amounts are simple rate x qty, matching the
'Rate x Unit' structure of the original the company PDA spreadsheets.

Harbour Rent (GPHA calls this "Berth Occupancy Charge") is the one exception --
its rate isn't a single flat number, it's banded by vessel LOA (GPHA Port
Tariff Aug 2023, Schedule 2.A.1). Per the company convention, Harbour Rent is
billed as Provisional Port Stay (days) x the LOA-appropriate daily rate -- the
system picks the correct band automatically from the vessel's LOA, then it's
a plain rate x qty line like everything else.
"""

from pda_engine.db import get_conn
from pda_engine.rules_engine import liner_tier

# (max LOA in metres, GPHA "first 24 hours" daily rate $, band label, real GPHA code)
_LOA_BANDS = [
    (150, 551.25, "up to 150m", "2A1001"),
    (200, 981.69, "150-200m", "2A1002"),
    (250, 1390.51, "200-250m", "2A1003"),
    (300, 1962.73, "250-300m", "2A1004"),
    (350, 2355.27, "300-350m", "2A1005"),
    (400, 3061.86, "350-400m", "2A1006"),
    (float("inf"), 3674.23, "above 400m", "2A1007"),
]

_HARBOUR_RENT_SOURCE = (
    "GPHA Port Tariff Aug 2023, Schedule 2.A.1 (Berth Occupancy Charge, LOA-banded daily rate); "
    "billed as Provisional Port Stay days x rate per the company convention"
)


def _harbour_rent_band(loa: float):
    for max_loa, rate, label, code in _LOA_BANDS:
        if loa <= max_loa:
            return rate, label, code
    return _LOA_BANDS[-1][1], _LOA_BANDS[-1][2], _LOA_BANDS[-1][3]


def harbour_rent_line(loa: float, port_stay_days: float):
    """Returns the Harbour Rent PDA1 line dict = LOA-banded daily rate x the
    provisional port stay (whichever is in effect -- the auto figure, or the
    user's manual override). The port stay is used exactly as given, not
    re-rounded, so a manual 5.5-day override bills 5.5 x rate. Returns None if
    loa/port_stay_days are not set yet."""
    if not loa or not port_stay_days:
        return None

    rate, band_label, code = _harbour_rent_band(loa)
    days = float(port_stay_days)

    return {
        "charge_code": code,
        "tariff_ref_code": code,
        "description": "Harbour Rent",
        "basis": "per_day",
        "unit_label": "Per Day",
        "rate": rate,
        "qty": days,
        "amount": round(rate * days, 2),
        "source": _HARBOUR_RENT_SOURCE + f" -- LOA band {band_label}",
        "group": "Ship Related Expenses",
        "is_placeholder": False, "stated_only": False, "pct": False,
    }


def driver_value(driver: str, call: dict) -> float:
    if driver == "fixed_1":
        return 1
    if driver == "cargo_qty_mt_gearless_only":
        # Craneage (GPHA D(4)) only applies when a crane is actually deployed --
        # a geared vessel uses its own gear, so no MHC/craneage charge at all.
        if (call.get("vessel_geared") or "").strip().lower() != "gearless":
            return 0.0
        return float(call.get("cargo_qty_mt") or 0)
    return float(call.get(driver) or 0)


def _select_cargo_rows(rows, cargo_type):
    """Some charges (currently the GSA Levy, Port Dues on Cargo) vary by cargo
    type and are stored as multiple rate_table rows sharing one charge_code,
    each editable independently in the Rate Library: one or more with
    `cargo_match` set to an exact cargo type (a carve-out rate), plus one with
    `cargo_match` blank/NULL (the generic fallback for every other cargo). This
    picks exactly one row per (pda_type, charge_code) -- the cargo-specific
    match if the call's cargo type has one, else the generic fallback -- while
    preserving row order. Charges with only a single row, or where NO row in
    the group has a cargo_match set at all (meaning that charge_code doesn't
    vary by cargo -- it may vary by something else, e.g. a GRT band, handled
    downstream by _select_grt_band_rows), are returned unchanged in full. A
    charge_code with exactly one row that IS cargo_match-tagged (a cargo-
    exclusive charge with no generic fallback, e.g. Ammonium Nitrate's bagged-
    cargo stevedoring lines) is dropped entirely for every other cargo type,
    rather than passed through -- otherwise a single-row cargo-exclusive charge
    would incorrectly appear on every call regardless of cargo."""
    candidates = {}
    for r in rows:
        candidates.setdefault((r["pda_type"], r["charge_code"]), []).append(r)

    cargo = (cargo_type or "").strip().lower()
    winners = {}
    passthrough_keys = set()
    drop_keys = set()
    for key, group in candidates.items():
        if len(group) == 1:
            only = group[0]
            match_val = (only["cargo_match"] or "").strip()
            if match_val and match_val.lower() != cargo:
                drop_keys.add(key)
            else:
                winners[key] = only
            continue
        if not any((r["cargo_match"] or "").strip() for r in group):
            passthrough_keys.add(key)
            continue
        exact = next((r for r in group if (r["cargo_match"] or "").strip().lower() == cargo and r["cargo_match"]), None)
        generic = next((r for r in group if not (r["cargo_match"] or "").strip()), None)
        winners[key] = exact or generic or group[0]

    seen = set()
    selected = []
    for r in rows:
        key = (r["pda_type"], r["charge_code"])
        if key in drop_keys:
            continue
        if key in passthrough_keys:
            selected.append(r)
            continue
        if key in seen:
            continue
        seen.add(key)
        selected.append(winners[key])
    return selected


def _select_liner_routed_rows(rows, tier):
    """Some Ammonium Nitrate cargo charges (Stevedoring, Estimated Labour Delays,
    Stevedoring Labour O'time, Cranage -- and, only under Full Liner Terms, Port
    Dues on Cargo) move from the Receiver's PDA2 onto the Principal's PDA1
    depending on the call's liner-terms tier (rules_engine.liner_tier). Stored
    as two rate_table rows sharing one charge_code -- one tagged pda_type=PDA2
    with `liner_routing` listing the tiers where it stays on the Receiver, one
    tagged pda_type=PDA1 listing the tiers where it moves to the Principal.
    Picks whichever row's liner_routing includes this call's tier, so the
    winning row brings its own correct pda_type with it. Charges with only one
    row and NO liner_routing set pass through unchanged -- i.e. every charge
    built before this feature. A charge_code with exactly one row that DOES
    have liner_routing set (e.g. price_call() was called for a single pda_type
    that doesn't include this charge's alternate) is dropped entirely unless
    this call's tier is actually listed on that lone row -- otherwise it would
    incorrectly fire regardless of tier whenever its PDA1/PDA2 counterpart
    wasn't fetched alongside it."""
    candidates = {}
    for r in rows:
        candidates.setdefault(r["charge_code"], []).append(r)

    winners = {}
    passthrough_keys = set()
    drop_keys = set()
    for code, group in candidates.items():
        if len(group) == 1:
            only = group[0]
            routing = (only["liner_routing"] or "").strip()
            if not routing:
                winners[code] = only
            elif tier in [t.strip() for t in routing.split(",") if t.strip()]:
                winners[code] = only
            else:
                drop_keys.add(code)
            continue
        if not any((r["liner_routing"] or "").strip() for r in group):
            passthrough_keys.add(code)
            continue
        match = next(
            (r for r in group if tier in [t.strip() for t in (r["liner_routing"] or "").split(",") if t.strip()]),
            None,
        )
        winners[code] = match or group[0]

    seen = set()
    selected = []
    for r in rows:
        code = r["charge_code"]
        if code in drop_keys:
            continue
        if code in passthrough_keys:
            selected.append(r)
            continue
        if code in seen:
            continue
        seen.add(code)
        selected.append(winners[code])
    return selected


def _select_grt_band_rows(rows, grt):
    """Some charges (Environmental Charge / GPHA Garbage Collection Charge,
    Twelfth Schedule; the marine-ops GT-band schedule) vary by vessel GRT band
    and are stored as multiple rate_table rows sharing one charge_code, each
    tagged with grt_min/grt_max (inclusive; NULL min behaves as 0, NULL max
    behaves as unbounded). Picks exactly one row per (pda_type, charge_code)
    whose band contains the call's GRT, preserving order. Charges with only one
    row and NO grt_min/grt_max set are returned unchanged (they don't vary by
    GRT at all). A charge_code with exactly one row that DOES have grt_min/
    grt_max set (a GRT-exclusive charge with no other band, e.g. the extra
    tug surcharge that only applies under 10,000 GT) is dropped entirely when
    the call's GRT falls outside that single band, rather than passed through
    unconditionally -- otherwise it would incorrectly fire for every GRT."""
    candidates = {}
    for r in rows:
        candidates.setdefault((r["pda_type"], r["charge_code"]), []).append(r)

    grt_val = float(grt or 0)
    winners = {}
    drop_keys = set()
    for key, group in candidates.items():
        if len(group) == 1:
            only = group[0]
            if only["grt_min"] is None and only["grt_max"] is None:
                winners[key] = only
            elif (only["grt_min"] is None or grt_val >= only["grt_min"]) and \
                 (only["grt_max"] is None or grt_val <= only["grt_max"]):
                winners[key] = only
            else:
                drop_keys.add(key)
            continue
        if not any(g["grt_min"] is not None or g["grt_max"] is not None for g in group):
            winners[key] = group[0]
            continue
        match = next(
            (g for g in group
             if (g["grt_min"] is None or grt_val >= g["grt_min"])
             and (g["grt_max"] is None or grt_val <= g["grt_max"])),
            None,
        )
        winners[key] = match or group[-1]

    seen = set()
    selected = []
    for r in rows:
        key = (r["pda_type"], r["charge_code"])
        if key in drop_keys:
            continue
        if key in seen:
            continue
        seen.add(key)
        selected.append(winners[key])
    return selected


def price_call(call: dict, pda_types=("PDA1", "PDA2")):
    """call: dict of call fields (as from sqlite3.Row -> dict).
    Returns {pda_type: {"lines": [...], "subtotal": float}}"""
    conn = get_conn()
    all_rows = conn.execute(
        "SELECT * FROM rate_table WHERE active = 1 AND pda_type IN (%s) ORDER BY rate_id"
        % ",".join("?" * len(pda_types)),
        tuple(pda_types),
    ).fetchall()
    conn.close()

    tier = liner_tier(call.get("liner_terms"))
    rows = _select_liner_routed_rows(all_rows, tier)
    rows = _select_cargo_rows(rows, call.get("cargo_type"))
    rows = _select_grt_band_rows(rows, call.get("grt"))

    result = {t: {"lines": [], "subtotal": 0.0} for t in pda_types}
    # Amounts already computed within each PDA, keyed by charge_code, so that
    # `percent_of_charge` lines (taxes, the 1%-of-stevedoring delay estimate) can
    # reference an earlier line's amount. Relies on base charges being seeded
    # before the lines that derive from them.
    computed = {t: {} for t in pda_types}

    for r in rows:
        pda_type = r["pda_type"]
        basis = r["basis"]

        if (r["source"] or "").startswith("Not applicable"):
            # A cargo-exclusive "not applicable" override (e.g. bulk Port Dues/
            # Stevedoring/Draft Survey for Bagged Ammonium Nitrate, which has its
            # own dedicated *-BAGGED charges instead) -- exists purely to stop
            # the generic bulk-cargo fallback from double-charging; showing a
            # visible "$0.00 Not applicable" line on the actual PDA would just
            # be clutter the real reference documents never have. Still record
            # it as 0 in `computed` so any percent_of_charge line referencing it
            # (e.g. GET-DRAFT off DRAFTSVY) correctly resolves to 0 too.
            computed[pda_type][r["charge_code"]] = 0.0
            continue

        if basis == "stated_only":
            # Shown with its rate for transparency, but no amount is computed and
            # it does NOT contribute to the subtotal (e.g. GETFUND/VAT on GPHA
            # Stevedoring on the receiver PDA).
            line = {
                "charge_code": r["charge_code"], "tariff_ref_code": r["tariff_ref_code"],
                "description": r["description"], "basis": basis, "unit_label": r["unit_label"],
                "rate": r["amount"], "qty": None, "amount": None,
                "source": r["source"], "group": r["group_name"] or "Ship Related Expenses",
                "is_placeholder": False, "stated_only": True, "pct": True,
            }
            result[pda_type]["lines"].append(line)
            continue

        # Display rate/unit default to the rate_table row; per_unit_with_minimum
        # may override them so a bound minimum shows as a clean flat line.
        disp_rate, disp_unit = r["amount"], r["unit_label"]

        if basis == "percent_of_charge":
            # rate x (sum of the referenced charge_code(s)' amounts within this PDA).
            # `driver` is usually one charge_code, but can be a comma-separated list
            # (e.g. "GW-DAY,GW-NIGHT") when a tax applies to a combined total. When a
            # referenced code was routed onto the OTHER pda_type (see
            # _select_liner_routed_rows), it's simply absent from `computed[pda_type]`
            # and contributes 0 -- the sum naturally shrinks to whatever's still here.
            codes = [c.strip() for c in r["driver"].split(",")]
            base_amount = sum(computed[pda_type].get(code, 0.0) for code in codes)
            qty = base_amount
            amount = round(r["amount"] * base_amount, 2)
            is_pct = True
        elif basis == "per_unit_with_minimum":
            # GPHA Craneage (Third Schedule 3H6001 + General Terms D(2)-D(4)):
            # greater of (qty x rate) or a flat minimum -- but only when the
            # charge applies at all (qty > 0; a geared vessel's
            # cargo_qty_mt_gearless_only driver returns 0, meaning no crane was
            # deployed and no minimum is owed either).
            drv_qty = driver_value(r["driver"], call)
            per_unit = round(r["amount"] * drv_qty, 2)
            minimum = r["minimum_amount"] or 0
            if drv_qty <= 0:
                qty, amount = 0.0, 0.0
            elif minimum >= per_unit:
                # The minimum binds -- present it as a single flat "Min Crane
                # Hire" line (rate = the minimum, qty = 1) rather than a
                # per-tonne rate x qty that wouldn't equal the amount shown.
                qty, amount = 1.0, round(minimum, 2)
                disp_rate, disp_unit = round(minimum, 2), "Min Crane Hire (lumpsum)"
            else:
                qty, amount = drv_qty, per_unit
                disp_unit = "Per Tonne (Craneage)"
            is_pct = False
        else:
            qty = driver_value(r["driver"], call)
            amount = round(r["amount"] * qty, 2)
            is_pct = False

        line = {
            "charge_code": r["charge_code"],
            "tariff_ref_code": r["tariff_ref_code"],
            "description": r["description"],
            "basis": basis,
            "unit_label": disp_unit,
            "rate": disp_rate,
            "qty": qty,
            "amount": amount,
            "source": r["source"],
            "group": r["group_name"] or "Ship Related Expenses",
            "is_placeholder": (r["source"] or "").startswith("TBD"),
            "stated_only": False,
            "pct": is_pct,
        }
        computed[pda_type][r["charge_code"]] = amount
        result[pda_type]["lines"].append(line)
        result[pda_type]["subtotal"] += amount

    if "PDA1" in result:
        harbour_rent = harbour_rent_line(call.get("loa"), call.get("port_stay_days"))
        if harbour_rent:
            lines = result["PDA1"]["lines"]
            insert_at = next(
                (i + 1 for i, l in enumerate(lines) if l["charge_code"] == "2A4004"),
                len(lines),
            )
            lines.insert(insert_at, harbour_rent)
            result["PDA1"]["subtotal"] += harbour_rent["amount"]

    for t in result:
        result[t]["subtotal"] = round(result[t]["subtotal"], 2)
    return result


def save_lines(call_id: int, priced: dict):
    conn = get_conn()
    conn.execute("DELETE FROM pda_lines WHERE call_id = ?", (call_id,))
    for pda_type, data in priced.items():
        for line in data["lines"]:
            conn.execute(
                """INSERT INTO pda_lines (call_id, pda_type, charge_code, description, basis, rate, qty, amount, notes)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (call_id, pda_type, line["charge_code"], line["description"], line["basis"],
                 line["rate"], line["qty"], line["amount"],
                 "PLACEHOLDER - needs real Takoradi rate" if line["is_placeholder"] else ""),
            )
    conn.commit()
    conn.close()
