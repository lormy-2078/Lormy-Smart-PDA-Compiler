"""
Rules engine -- decides whether a call produces a Principal PDA only, or a
Principal PDA + a separate Receiver (Consignee) PDA, based on the Load/Discharge
(liner) terms.

This is a DISCHARGE / IMPORT platform (Takoradi bulk clinker). The deciding
factor is who pays the OUT (discharge / cargo-handling) leg:

  * OUT is on cargo's account ("Free Out" family) -> the receiver/consignee is
    billed for stevedoring, port dues on cargo, etc., so the company prepares a
    separate Receiver PDA IN ADDITION TO the Principal PDA. This is the normal
    case for bulk clinker (real example: TAK26063 Principal + TAK26063A Receiver
    to Kumasi Cement, examined 2026-07-12).

  * OUT is on the vessel/owner's account ("Liner Out" family) -> cargo-handling
    cost folds into the vessel's own account, so there is no separate receiver
    account; it is a Principal PDA only. NOTE: actually folding the stevedoring
    lines into the Principal PDA for these terms is future work -- for now such a
    call is simply marked PDA 1 only.

Correction history: an earlier build (based solely on the TAK26024 ES LEADER
document, which happened to be a single principal-only PDA) had Free Out mapped
to "PDA 1 only". The KASSIOPI.GR pair (same vessel, Free Out, WITH a receiver
PDA) showed that was wrong -- Free Out is exactly when a receiver PDA IS needed.

Decision order:
  1. If `liner_terms` is an explicit, recognised selection -> that mapping wins.
  2. Otherwise, fall back to a keyword scan of the pasted appointment text.
  3. If nothing matches either -> default to Principal + Receiver (PDA 1 + PDA 2),
     since bulk clinker at Takoradi is Free Out by default.
"""

LINER_TERMS_OPTIONS = [
    "Free Out (FO)",
    "FIO (Free In & Out)",
    "FIOS (Free In, Out & Stowed)",
    "FIOST (Free In, Out, Stowed & Trimmed)",
    "LIFO (Liner In, Free Out)",
    "FILO (Free In, Liner Out)",
    "Free In (FI)",
    "Liner Terms / Gross Terms",
    "LILO (Liner In, Liner Out)",
    "Full Liner Terms",
    "Other / Not Specified",
]

# Terms where the OUT (discharge) leg is on cargo's account -> a Receiver PDA is
# prepared in addition to the Principal PDA. This is the normal bulk-clinker case.
_RECEIVER_PDA_TERMS = {
    "Free Out (FO)",
    "FIO (Free In & Out)",
    "FIOS (Free In, Out & Stowed)",
    "FIOST (Free In, Out, Stowed & Trimmed)",
    "LIFO (Liner In, Free Out)",
}

# Terms where the OUT (discharge) leg is on the vessel/owner's account -> no
# separate receiver account for most cargoes; Principal PDA only. (Ammonium
# Nitrate is the one exception -- see _ALWAYS_DUAL_PDA_CARGO below -- because
# GSA Levy and Admin/Release Fee are purely local charges that always sit on
# the Receiver/Shipper's account regardless of liner terms, so that cargo
# still gets a small Receiver PDA even under these terms.)
_PRINCIPAL_ONLY_TERMS = {
    "FILO (Free In, Liner Out)",
    "Free In (FI)",
    "Liner Terms / Gross Terms",
    "LILO (Liner In, Liner Out)",
    "Full Liner Terms",
}

# Cargoes whose Receiver PDA always exists, however small, no matter the liner
# terms -- e.g. bagged Ammonium Nitrate (MAXAM Ghana), where GSA Levy and
# Admin/Release Fee are purely local charges always billed to the Receiver/
# Shipper, even under Liner Out/LILO or Full Liner Terms where the stevedoring-
# family charges (and, under Full Liner Terms, Port Dues on Cargo) fold onto
# the Principal instead (see rate_engine._select_liner_routed_rows).
_ALWAYS_DUAL_PDA_CARGO = {"Bagged Ammonium Nitrate"}


def liner_tier(liner_terms: str) -> str:
    """Which of the three cargo-charge-routing tiers a liner term falls into
    (see rate_engine._select_liner_routed_rows): 'free_out' -- cargo charges
    stay on the Receiver; 'liner_out' -- stevedoring-family charges move to the
    Principal, Port Dues on Cargo stays on the Receiver; 'full_liner' --
    stevedoring-family AND Port Dues on Cargo move to the Principal. Distinct
    from decide_billing_structure()'s PDA1_ONLY/PDA1_AND_PDA2 decision below --
    a call can need a (small) Receiver PDA while still routing most of its
    cargo charges to the Principal."""
    if liner_terms == "Full Liner Terms":
        return "full_liner"
    if liner_terms in _PRINCIPAL_ONLY_TERMS:
        return "liner_out"
    return "free_out"

# Dry-bulk IMPORT cargoes that are discharged on Free Out terms by default at
# Takoradi (receiver pays cargo handling). Used only to pre-select a sensible
# default liner term when the operator hasn't chosen one -- they can still
# override it. Matched as substrings so future cargoes (Bulk Coal, Bulk Grains)
# are covered once added. FIOST is equivalent for the billing decision; Free Out
# is the house default.
_FREE_OUT_DEFAULT_CARGO_KEYWORDS = ("clinker", "gypsum", "limestone", "slag", "coal", "grain", "wheat")


def default_liner_terms_for_cargo(cargo_type):
    """Returns the default liner term ('Free Out (FO)') for a dry-bulk import
    cargo that's normally Free Out, or None if the cargo has no such default."""
    c = (cargo_type or "").lower()
    if any(k in c for k in _FREE_OUT_DEFAULT_CARGO_KEYWORDS):
        return "Free Out (FO)"
    return None


# Appointment-text fallbacks (only used when no liner term is selected).
NO_SPLIT_CLUES = [
    "liner terms", "liner out", "gross terms", "owner covers discharge",
    "discharge on owner", "stevedoring on owner",
]

SPLIT_SUPPORT_CLUES = [
    "free out", "fio", "fios", "fiost", "lifo",
    "receiver account", "receiver to settle", "cargo account", "cargo interests",
    "stevedoring on receiver", "discharge on cargo",
]


def decide_billing_structure(appointment_text: str, liner_terms: str = None, cargo_type: str = None):
    """Returns (decision, reason, matched_clues) where decision is one of
    'PDA1_ONLY' or 'PDA1_AND_PDA2'. PDA1_AND_PDA2 means a Principal PDA plus a
    separate Receiver (Consignee) PDA."""
    if liner_terms and liner_terms in _RECEIVER_PDA_TERMS:
        reason = (
            f"Load/Discharge terms selected as '{liner_terms}' -- the discharge (cargo-handling) "
            f"cost is on the cargo's account, so a separate Receiver (Consignee) PDA is prepared "
            f"in addition to the Principal PDA. This is the normal Takoradi bulk clinker case."
        )
        return "PDA1_AND_PDA2", reason, [liner_terms]

    if liner_terms and liner_terms in _PRINCIPAL_ONLY_TERMS:
        if cargo_type in _ALWAYS_DUAL_PDA_CARGO:
            reason = (
                f"Load/Discharge terms selected as '{liner_terms}' -- the stevedoring-family "
                f"charges (and, under Full Liner Terms, Port Dues on Cargo) move onto the "
                f"Principal PDA, but GSA Levy and Admin/Release Fee are purely local charges "
                f"that always sit on the Receiver/Shipper's account for {cargo_type}, so a "
                f"(smaller) Receiver PDA is still prepared alongside the Principal PDA."
            )
            return "PDA1_AND_PDA2", reason, [liner_terms]
        reason = (
            f"Load/Discharge terms selected as '{liner_terms}' -- the discharge (cargo-handling) "
            f"cost is on the vessel/owner's account, so there is no separate receiver account; "
            f"this is a Principal PDA only. (Folding stevedoring into the Principal PDA for these "
            f"terms is future work.)"
        )
        return "PDA1_ONLY", reason, [liner_terms]

    text = (appointment_text or "").lower()

    split_hits = [c for c in SPLIT_SUPPORT_CLUES if c in text]
    if split_hits:
        return (
            "PDA1_AND_PDA2",
            "Appointment wording indicates the discharge/cargo cost is on the receiver's account; "
            "a Receiver PDA is prepared in addition to the Principal PDA.",
            split_hits,
        )

    no_split_hits = [c for c in NO_SPLIT_CLUES if c in text]
    if no_split_hits:
        return (
            "PDA1_ONLY",
            "Appointment wording indicates liner/owner-account discharge; Principal PDA only.",
            no_split_hits,
        )

    return (
        "PDA1_AND_PDA2",
        "No Load/Discharge terms selected and no clear clues in the appointment text; defaulted to "
        "Principal + Receiver (PDA 1 + PDA 2), since Takoradi bulk clinker is Free Out by default.",
        [],
    )
