import json
from pathlib import Path
from dotenv import load_dotenv
from markupsafe import Markup
from flask import Flask, render_template, request, redirect, url_for, flash, send_file

load_dotenv()

from pda_engine.db import get_conn, init_db, now, log_review, DB_PATH
from pda_engine.rules_engine import decide_billing_structure, LINER_TERMS_OPTIONS, default_liner_terms_for_cargo
from pda_engine.rate_engine import price_call, save_lines, _select_cargo_rows
from pda_engine.extraction import extract_vessel_particulars
from pda_engine.ai_extraction import (
    extract_vessel_particulars_ai,
    extract_vessel_particulars_ai_from_text,
    extract_vessel_particulars_ai_from_content,
    extract_bl_manifest_ai,
    content_block_any,
    is_configured as ai_configured,
)
from pda_engine.email_intake import parse_email
from pda_engine.pda_export import build_pda_excel, build_pda_pdf, fmt_rate
from pda_engine import port_stay

PORTS_OF_CALL = [
    {"name": "Takoradi", "unlocode": "GHTKD", "supported": True},
    {"name": "Tema", "unlocode": "GHTEM", "supported": False},
]

# GPHA is the primary tariff (most schedules, most rate_table rows in use) and should
# always lead the Tariff Reference authority dropdown; other authorities follow in this
# order, then alphabetically for anything not listed yet.
AUTHORITY_ORDER = ["GPHA", "GMA"]

BASE_DIR = Path(__file__).resolve().parent
STORAGE = BASE_DIR / "storage"

app = Flask(__name__)
app.secret_key = "dev-only-local-prototype"

init_db()

_PENDING_EXTRACTIONS = {}


def badge(field):
    conf = getattr(request, "_prefill_confidence", {}) or {}
    level = conf.get(field)
    if not level:
        return Markup("")
    return Markup(f'<span class="badge {level}">{level} confidence</span>')


def match_cargo_type(extracted):
    """Best-effort match of a free-text extracted cargo string (e.g. 'Clinker')
    to one of the known dropdown cargo types (e.g. 'Bulk Clinker')."""
    if not extracted:
        return ""
    low = str(extracted).lower()
    for t in port_stay.CARGO_STAY_RATES_TAKORADI:
        if t.lower().replace("bulk ", "") in low:
            return t
    return ""


app.jinja_env.globals["badge"] = badge
app.jinja_env.globals["match_cargo_type"] = match_cargo_type
app.jinja_env.globals["fmt_rate"] = fmt_rate


def call_to_dict(row):
    return {k: row[k] for k in row.keys()}


@app.route("/")
def history():
    conn = get_conn()
    calls = conn.execute("SELECT * FROM calls ORDER BY call_id DESC").fetchall()
    conn.close()
    return render_template("history.html", calls=calls)


@app.route("/calls/new", methods=["GET"])
def new_call():
    # .get(), not .pop() -- navigating back to this same pre-fill URL (browser
    # back button after creating the call) needs the extracted data to still be
    # there, not blanked out because the first visit already consumed it.
    prefill = _PENDING_EXTRACTIONS.get(request.args.get("token", ""), {}) if request.args.get("token") else {}
    request._prefill_confidence = prefill.get("_confidence", {})
    return render_template(
        "new_call.html", prefill=prefill, prefill_doc_id="", ai_enabled=ai_configured(),
        ports=PORTS_OF_CALL, cargo_types=port_stay.CARGO_TYPES, liner_terms_options=LINER_TERMS_OPTIONS,
    )


def _finalize_extraction(found, confidence, engine_used, source_label):
    """Stash the extracted fields under a one-shot token, flash a summary, and
    redirect to the New Call form (which reads the token and pre-fills)."""
    n_fields = len(found)
    found = dict(found)
    found["_confidence"] = confidence
    import uuid
    token = uuid.uuid4().hex[:8]
    _PENDING_EXTRACTIONS[token] = found
    if n_fields == 0:
        flash(f"No fields could be extracted from {source_label} using {engine_used}. Fill the form in manually.")
    else:
        flash(f"Extracted {n_fields} field(s) from {source_label} using {engine_used}. Review before saving.")
    return redirect(url_for("new_call", token=token))


# Native file types the Claude extractor can read directly (pdf/image), plus the
# ones it converts to text (docx/xls). Email files are handled separately below.
AI_SUPPORTED_EXTS = {".pdf", ".docx", ".jpg", ".jpeg", ".png", ".webp", ".xls", ".xlsx"}
EMAIL_EXTS = {".eml", ".msg"}


@app.route("/calls/new/extract", methods=["POST"])
def new_call_extract():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file uploaded — fill the form in manually.")
        return redirect(url_for("new_call"))

    STORAGE.joinpath("documents").mkdir(parents=True, exist_ok=True)
    stored_path = STORAGE / "documents" / file.filename
    file.save(stored_path)
    ext = Path(file.filename).suffix.lower()

    # Email file: parse body + attachments, hand the whole lot to Claude in one pass.
    if ext in EMAIL_EXTS:
        if not ai_configured():
            flash("Reading email files (.eml/.msg) needs the Claude AI extractor "
                  "(set ANTHROPIC_API_KEY) — fill the form in manually for now.")
            return redirect(url_for("new_call"))
        try:
            body, attachments = parse_email(str(stored_path), STORAGE / "documents")
            blocks = [{"type": "text", "text": f"Appointment email:\n\n{body}"}]
            for att in attachments:
                block = content_block_any(att)
                if block:
                    blocks.append(block)
            found, confidence = extract_vessel_particulars_ai_from_content(blocks)
            # Don't auto-fill the manual appointment/enquiry box from an uploaded
            # document -- the operator uses that box for pasted text, not the AI's
            # billing summary of a file they already uploaded.
            found.pop("appointment_text", None); confidence.pop("appointment_text", None)
            label = f"{file.filename}" + (f" (+{len(attachments)} attachment(s))" if attachments else "")
            return _finalize_extraction(found, confidence, "Claude (email)", label)
        except Exception as e:
            flash(f"Could not read the email file ({e}) — fill the form in manually.")
            return redirect(url_for("new_call"))

    engine_used = None
    found, confidence = {}, {}
    if ai_configured() and ext in AI_SUPPORTED_EXTS:
        try:
            found, confidence = extract_vessel_particulars_ai(str(stored_path))
            engine_used = "Claude extraction"
        except Exception as e:
            flash(f"Claude extraction failed ({e}) — falling back to the offline extractor.")

    if engine_used is None:
        found, confidence = extract_vessel_particulars(str(stored_path))
        engine_used = "offline heuristic extraction"

    # Don't auto-fill the manual appointment/enquiry box from an uploaded file.
    found.pop("appointment_text", None); confidence.pop("appointment_text", None)
    return _finalize_extraction(found, confidence, engine_used, file.filename)


@app.route("/calls/new/extract_text", methods=["POST"])
def new_call_extract_text():
    text = (request.form.get("appointment_text") or "").strip()
    if not text:
        flash("Paste the appointment / email text into the box first, then click Extract.")
        return redirect(url_for("new_call"))
    if not ai_configured():
        flash("Extracting from pasted text needs the Claude AI extractor (set ANTHROPIC_API_KEY).")
        return redirect(url_for("new_call"))
    try:
        found, confidence = extract_vessel_particulars_ai_from_text(text)
        # Keep the operator's original pasted text in the box (more useful than the
        # AI's billing-only summary), but let the AI fill everything else.
        found["appointment_text"] = text
        confidence["appointment_text"] = "high"
        return _finalize_extraction(found, confidence, "Claude (pasted text)", "the pasted text")
    except Exception as e:
        flash(f"Claude extraction failed ({e}) — fill the form in manually.")
        return redirect(url_for("new_call"))


@app.route("/calls/new", methods=["POST"])
def create_call():
    f = request.form
    cargo_type = f.get("cargo_type") or ""
    cargo_qty_mt = float(f.get("cargo_qty_mt") or 0)
    # Single editable Port Stay box: the value in the box wins (it was pre-filled
    # with the auto calc but the user can type over it); if left blank, the server
    # falls back to the auto figure from cargo type + quantity.
    port_stay_days = port_stay.compute_port_stay_days(
        cargo_type, cargo_qty_mt, manual_days=float(f.get("port_stay_days") or 0)
    )

    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO calls
           (port, cargo_type, vessel_type, our_ref, your_ref, vessel, imo, flag,
            principal, principal_attn, receiver, receiver_attn,
            cargo_qty_mt, grt, loa, draft, port_stay_days, eta,
            movements_in, movements_out, movements_in_out, shifting_movements,
            anchorage_grt_days, gangway_day_hours, gangway_night_hours, third_party_cost,
            labour_delay_hours, liner_terms, appointment_text, status, created_at,
            cargo_qty_cbm, vessel_geared)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (f.get("port") or "Takoradi", cargo_type, f.get("vessel_type") or "Bulk Carrier",
         f.get("our_ref"), f.get("your_ref"), f.get("vessel"), f.get("imo"), f.get("flag"),
         # Principal is now a multi-line billing address (company, VAT no., street,
         # postal/city, country) -- normalize the textarea's CRLF to plain \n.
         (f.get("principal") or "").replace("\r\n", "\n"), f.get("principal_attn"),
         f.get("receiver"), f.get("receiver_attn"),
         cargo_qty_mt, float(f.get("grt") or 0), float(f.get("loa") or 0),
         float(f.get("draft") or 0), port_stay_days, f.get("eta"),
         int(f.get("movements_in") or 1), int(f.get("movements_out") or 1), int(f.get("movements_in_out") or 2),
         int(f.get("shifting_movements") or 0), float(f.get("anchorage_grt_days") or 0),
         float(f.get("gangway_day_hours") or 0), float(f.get("gangway_night_hours") or 0),
         float(f.get("third_party_cost") or 0), float(f.get("labour_delay_hours") or 0),
         (f.get("liner_terms") or default_liner_terms_for_cargo(cargo_type) or ""),
         f.get("appointment_text") or "", "draft", now(),
         float(f.get("cargo_qty_cbm") or 0), f.get("vessel_geared") or ""),
    )
    call_id = cur.lastrowid
    conn.commit()
    conn.close()

    log_review(call_id, "operator", "created", "Call created via New Call form.")
    _run_engines(call_id)
    return redirect(url_for("review_call", call_id=call_id))


def _run_engines(call_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
    conn.close()
    call = call_to_dict(row)

    decision, reason, clues = decide_billing_structure(
        call.get("appointment_text"), call.get("liner_terms"), call.get("cargo_type")
    )

    conn = get_conn()
    conn.execute("UPDATE calls SET billing_decision = ?, billing_reason = ? WHERE call_id = ?",
                 (decision, reason, call_id))
    conn.commit()
    conn.close()

    priced = price_call(call, pda_types=("PDA1", "PDA2"))
    save_lines(call_id, priced)
    log_review(call_id, "rules_engine", decision, reason + (f" Clues: {clues}" if clues else ""))


def _get_bl_rows(call_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM bill_of_lading WHERE call_id = ? ORDER BY bl_id", (call_id,)).fetchall()
    conn.close()
    return [call_to_dict(r) for r in rows]


def _price_bl(call, bl):
    """Prices one Bill of Lading's Receiver PDA -- the call's own particulars
    with this BL's receiver/tonnage/cbm substituted in, plus a manually-entered
    Tally line (Ammonium Nitrate Receiver PDAs are prepared per-BL with the
    Tally lumpsum apportioned by whoever prepares the call, not computed here).
    Returns (bl_call, priced) ready to use as one of build_pda_*'s bl_docs entries."""
    bl_call = dict(call)
    bl_call.update({
        "receiver": bl.get("receiver") or call.get("receiver"),
        "receiver_attn": bl.get("receiver_attn") or call.get("receiver_attn"),
        "cargo_qty_mt": bl.get("cargo_qty_mt") or 0,
        "cargo_qty_cbm": bl.get("cargo_qty_cbm") or 0,
        "bl_number": bl.get("bl_number") or "",
    })
    priced = price_call(bl_call, pda_types=("PDA1", "PDA2"))
    tally = bl.get("tally_amount") or 0
    if tally:
        priced["PDA2"]["lines"].append({
            "charge_code": "TALLY", "tariff_ref_code": None, "description": "Tally",
            "basis": "lumpsum", "unit_label": "Lumpsum (manual entry, per Bill of Lading)",
            "rate": tally, "qty": 1, "amount": tally,
            "source": "Manually entered per Bill of Lading -- shared out of a call-wide Tally figure by the operator",
            "group": "Others General", "is_placeholder": False, "stated_only": False, "pct": False,
        })
        priced["PDA2"]["subtotal"] = round(priced["PDA2"]["subtotal"] + tally, 2)
    return bl_call, priced


def _bl_docs_for(call):
    """[(bl_number, bl_call, priced), ...] for every BL on this call, or []
    if the call has no BL rows (the single-Receiver-PDA case, unaffected)."""
    return [(bl["bl_number"], *_price_bl(call, bl)) for bl in _get_bl_rows(call["call_id"])]


@app.route("/calls/<int:call_id>")
def review_call(call_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
    conn.close()
    if not row:
        flash("Call not found.")
        return redirect(url_for("history"))
    call = call_to_dict(row)
    priced = price_call(call, pda_types=("PDA1", "PDA2"))
    bl_rows = _get_bl_rows(call_id)
    bl_priced = [(bl, _price_bl(call, bl)[1]) for bl in bl_rows]
    # Second-stage manifest/BL extraction (see bl_extract below) stashes a LIST
    # of extracted bills under a token; the Review page shows them in an editable
    # preview table. .get(), not .pop(), so navigating back here still shows it.
    bl_token = request.args.get("bl_token")
    bl_preview = _PENDING_EXTRACTIONS.get(bl_token, []) if bl_token else []
    bl_total_mt = sum(bl["cargo_qty_mt"] or 0 for bl in bl_rows)
    return render_template(
        "review.html", call=call, priced=priced, liner_terms_options=LINER_TERMS_OPTIONS,
        bl_rows=bl_rows, bl_priced=bl_priced, bl_preview=bl_preview, bl_token=bl_token,
        bl_total_mt=bl_total_mt, ai_enabled=ai_configured(),
    )


@app.route("/calls/<int:call_id>/bl/extract", methods=["POST"])
def bl_extract(call_id):
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file uploaded for the cargo manifest / BL.")
        return redirect(url_for("review_call", call_id=call_id))
    if not ai_configured():
        flash("Manifest/BL extraction needs the Claude AI extractor (set ANTHROPIC_API_KEY) — fill the Bill of Lading in manually.")
        return redirect(url_for("review_call", call_id=call_id))

    STORAGE.joinpath("documents").mkdir(parents=True, exist_ok=True)
    stored_path = STORAGE / "documents" / file.filename
    file.save(stored_path)
    ext = Path(file.filename).suffix.lower()
    if ext not in AI_SUPPORTED_EXTS:
        flash(f"Unsupported file type for manifest/BL extraction: {ext}")
        return redirect(url_for("review_call", call_id=call_id))

    try:
        bills = extract_bl_manifest_ai(str(stored_path))
    except Exception as e:
        flash(f"Manifest/BL extraction failed ({e}) — fill the Bill of Lading in manually.")
        return redirect(url_for("review_call", call_id=call_id))

    if not bills:
        flash(f"No Bills of Lading could be read from {file.filename} — fill them in manually.")
        return redirect(url_for("review_call", call_id=call_id))

    import uuid
    token = uuid.uuid4().hex[:8]
    _PENDING_EXTRACTIONS[token] = bills
    flash(f"Extracted {len(bills)} Bill(s) of Lading from {file.filename}. Review below, then Create all.")
    return redirect(url_for("review_call", call_id=call_id, bl_token=token))


@app.route("/calls/<int:call_id>/bl/create_all", methods=["POST"])
def bl_create_all(call_id):
    f = request.form
    # Parallel arrays, one entry per previewed bill (see the preview table). The
    # `include` checkbox list holds the row indices the operator kept ticked.
    include = set(f.getlist("include"))
    numbers = f.getlist("bl_number")
    receivers = f.getlist("receiver")
    attns = f.getlist("receiver_attn")
    mts = f.getlist("cargo_qty_mt")
    cbms = f.getlist("cargo_qty_cbm")
    bags_list = f.getlist("bags")
    mults = f.getlist("cbm_multiplier")

    conn = get_conn()
    existing_numbers = {
        (r["bl_number"] or "").strip().lower()
        for r in conn.execute("SELECT bl_number FROM bill_of_lading WHERE call_id = ?", (call_id,)).fetchall()
    }
    added, skipped = 0, []
    for i in range(len(numbers)):
        if str(i) not in include:
            continue
        bl_number = (numbers[i] or "").strip()
        # Same duplicate guard as add_bl -- a manifest re-uploaded, or a BL
        # already added manually, shouldn't create a second row.
        if bl_number and bl_number.lower() in existing_numbers:
            skipped.append(bl_number)
            continue
        conn.execute(
            """INSERT INTO bill_of_lading
               (call_id, bl_number, receiver, receiver_attn, cargo_qty_mt, cargo_qty_cbm, tally_amount, bags, cbm_multiplier, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (call_id, bl_number, receivers[i] if i < len(receivers) else "",
             attns[i] if i < len(attns) else "",
             float(mts[i] or 0) if i < len(mts) else 0, float(cbms[i] or 0) if i < len(cbms) else 0,
             0.0, float(bags_list[i] or 0) if i < len(bags_list) else 0,
             float(mults[i] or 0) if i < len(mults) else 0, now()),
        )
        if bl_number:
            existing_numbers.add(bl_number.lower())
        added += 1
    conn.commit()
    conn.close()
    log_review(call_id, "operator", "bl_created_all", f"{added} Bill(s) of Lading created from manifest.")
    msg = f"Created {added} Bill(s) of Lading."
    if skipped:
        msg += f" Skipped {len(skipped)} already on this call: {', '.join(skipped)}."
    flash(msg)
    return redirect(url_for("review_call", call_id=call_id))


@app.route("/calls/<int:call_id>/bl/add", methods=["POST"])
def add_bl(call_id):
    f = request.form
    bl_number = (f.get("bl_number") or "").strip()

    # Real incident (2026-07-18, APOLLON TRADER): the same BL got added twice,
    # ~6 hours apart, because this form has always been add-only -- nothing
    # stopped a second submission for a BL number already on the call. Blocks
    # it outright rather than just flashing a warning after the fact, since a
    # BL number genuinely shouldn't repeat within one call; blank numbers are
    # exempt (a call can have more than one BL with no number yet).
    if bl_number:
        conn = get_conn()
        existing = conn.execute(
            "SELECT bl_id FROM bill_of_lading WHERE call_id = ? AND lower(trim(bl_number)) = ?",
            (call_id, bl_number.lower()),
        ).fetchone()
        conn.close()
        if existing:
            flash(f"A Bill of Lading numbered '{bl_number}' already exists on this call (BL #{existing['bl_id']}) "
                  f"— not added again. Remove the existing one first if you need to replace it, or check the number.")
            return redirect(url_for("review_call", call_id=call_id))

    conn = get_conn()
    conn.execute(
        """INSERT INTO bill_of_lading
           (call_id, bl_number, receiver, receiver_attn, cargo_qty_mt, cargo_qty_cbm, tally_amount, bags, cbm_multiplier, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (call_id, bl_number, f.get("receiver") or "", f.get("receiver_attn") or "",
         float(f.get("cargo_qty_mt") or 0), float(f.get("cargo_qty_cbm") or 0),
         float(f.get("tally_amount") or 0), float(f.get("bags") or 0), float(f.get("cbm_multiplier") or 0), now()),
    )
    conn.commit()
    conn.close()
    log_review(call_id, "operator", "bl_added", f"Bill of Lading {bl_number} added.")
    flash("Bill of Lading added.")
    return redirect(url_for("review_call", call_id=call_id))


@app.route("/calls/<int:call_id>/bl/<int:bl_id>/delete", methods=["POST"])
def delete_bl(call_id, bl_id):
    conn = get_conn()
    conn.execute("DELETE FROM bill_of_lading WHERE bl_id = ? AND call_id = ?", (bl_id, call_id))
    conn.commit()
    conn.close()
    log_review(call_id, "operator", "bl_deleted", f"Bill of Lading #{bl_id} removed.")
    flash("Bill of Lading removed.")
    return redirect(url_for("review_call", call_id=call_id))


@app.route("/calls/<int:call_id>/bl/distribute_tally", methods=["POST"])
def distribute_tally(call_id):
    """Splits a single call-wide Tally lumpsum across the call's BLs by their
    gross-weight (cargo_qty_mt) share, writing each BL's slice into its own
    tally_amount. Real practice for bagged Ammonium Nitrate (BALTIC ERICA: one
    $850 Tally shared across 4 MR-number BLs by gross MT). Largest-remainder
    rounding so the pennies sum back to exactly the total. Writes into the
    existing per-BL tally_amount, so pricing/export are unchanged."""
    total = float(request.form.get("tally_total") or 0)
    conn = get_conn()
    conn.execute("UPDATE calls SET tally_total = ? WHERE call_id = ?", (total, call_id))
    bls = conn.execute("SELECT bl_id, cargo_qty_mt FROM bill_of_lading WHERE call_id = ? ORDER BY bl_id", (call_id,)).fetchall()
    weights = [(r["bl_id"], r["cargo_qty_mt"] or 0) for r in bls]
    total_mt = sum(w for _, w in weights)

    if not bls:
        conn.commit(); conn.close()
        flash("No Bills of Lading to distribute the Tally across yet — add them first.")
        return redirect(url_for("review_call", call_id=call_id))
    if total_mt <= 0:
        conn.commit(); conn.close()
        flash("The Bills of Lading have no cargo weight (MT) to apportion the Tally by — set their gross MT first.")
        return redirect(url_for("review_call", call_id=call_id))

    total_cents = round(total * 100)
    # Largest-remainder apportionment: floor each share to whole cents, then hand
    # the leftover cents out one at a time to the BLs with the biggest fractional
    # remainders, so the parts add up to exactly `total`.
    raw = [(bl_id, (w / total_mt) * total_cents) for bl_id, w in weights]
    floors = [(bl_id, int(x)) for bl_id, x in raw]
    remainder = total_cents - sum(c for _, c in floors)
    order = sorted(range(len(raw)), key=lambda i: raw[i][1] - floors[i][1], reverse=True)
    cents = {bl_id: c for bl_id, c in floors}
    for k in range(remainder):
        cents[floors[order[k]][0]] += 1

    for bl_id, c in cents.items():
        conn.execute("UPDATE bill_of_lading SET tally_amount = ? WHERE bl_id = ?", (c / 100.0, bl_id))
    conn.commit()
    conn.close()
    log_review(call_id, "operator", "tally_distributed", f"Tally ${total:,.2f} split across {len(bls)} BL(s) by gross MT.")
    flash(f"Tally ${total:,.2f} distributed across {len(bls)} Bill(s) of Lading by gross weight.")
    return redirect(url_for("review_call", call_id=call_id))


@app.route("/calls/<int:call_id>/reprice", methods=["POST"])
def reprice_call(call_id):
    f = request.form
    cargo_type = f.get("cargo_type") or ""
    cargo_qty_mt = float(f.get("cargo_qty_mt") or 0)
    port_stay_days = port_stay.compute_port_stay_days(
        cargo_type, cargo_qty_mt, manual_days=float(f.get("port_stay_days") or 0)
    )

    conn = get_conn()
    # Shifting / Anchorage / 3rd-Party Cost are no longer on the reprice form
    # (removed from the "Marine Operations" tab per operator feedback -- to be
    # edited directly on the generated PDA later). They're left OUT of this
    # UPDATE so recalculating never zeroes whatever they were stored as.
    conn.execute(
        """UPDATE calls SET grt=?, loa=?, cargo_qty_mt=?, port_stay_days=?, movements_in=?, movements_out=?,
           movements_in_out=?, liner_terms=?, appointment_text=?,
           cargo_qty_cbm=?, vessel_geared=? WHERE call_id=?""",
        (float(f.get("grt") or 0), float(f.get("loa") or 0), cargo_qty_mt,
         port_stay_days,
         int(f.get("movements_in") or 0), int(f.get("movements_out") or 0), int(f.get("movements_in_out") or 0),
         (f.get("liner_terms") or default_liner_terms_for_cargo(cargo_type) or ""),
         f.get("appointment_text") or "",
         float(f.get("cargo_qty_cbm") or 0), f.get("vessel_geared") or "", call_id),
    )
    conn.commit()
    conn.close()
    log_review(call_id, "operator", "edited_drivers", "Drivers/appointment text updated on Review screen.")
    _run_engines(call_id)
    flash("Recalculated.")
    return redirect(url_for("review_call", call_id=call_id))


def _pda_types_for(call):
    """PDA 2 is always computed and saved regardless of billing decision (see
    _run_engines) -- this only controls what gets exported. Under PDA1_ONLY
    (e.g. Free Out terms), the company issues a single-document PDA, so the
    export omits the PDA 2 sheet entirely rather than bundling an
    always-unbilled placeholder."""
    if call["billing_decision"] == "PDA1_ONLY":
        return ["PDA1"]
    return ["PDA1", "PDA2"]


@app.route("/calls/<int:call_id>/export/excel")
def export_excel(call_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
    conn.close()
    call = call_to_dict(row)
    pda_types = _pda_types_for(call)
    priced = price_call(call, pda_types=tuple(pda_types))
    bl_docs = _bl_docs_for(call) if "PDA2" in pda_types else []
    out_path = STORAGE / "outputs" / f"PDA_{call['our_ref'] or call_id}.xlsx"
    build_pda_excel(call, priced, pda_types, str(out_path), bl_docs=bl_docs)
    _record_output(call_id, "+".join(pda_types), "xlsx", str(out_path))
    return send_file(out_path, as_attachment=True)


@app.route("/calls/<int:call_id>/export/pdf")
def export_pdf(call_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
    conn.close()
    call = call_to_dict(row)
    pda_types = _pda_types_for(call)
    priced = price_call(call, pda_types=tuple(pda_types))
    bl_docs = _bl_docs_for(call) if "PDA2" in pda_types else []
    out_path = STORAGE / "outputs" / f"PDA_{call['our_ref'] or call_id}.pdf"
    build_pda_pdf(call, priced, pda_types, str(out_path), bl_docs=bl_docs)
    _record_output(call_id, "+".join(pda_types), "pdf", str(out_path))
    return send_file(out_path, as_attachment=True)


def _record_output(call_id, pda_type, fmt, file_path):
    conn = get_conn()
    conn.execute("INSERT INTO outputs (call_id, pda_type, format, file_path, created_at) VALUES (?,?,?,?,?)",
                 (call_id, pda_type, fmt, file_path, now()))
    conn.commit()
    conn.close()
    log_review(call_id, "operator", f"exported_{fmt}", file_path)


@app.route("/rates")
def rates():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM rate_table ORDER BY rate_id").fetchall()
    conn.close()

    # Optional per-cargo view: "if cargo is Bulk Clinker, these are all the
    # charges likely to be incurred". Reuses the exact same cargo selector the
    # pricing engine uses (rate_engine._select_cargo_rows) -- so "what shows
    # here" and "what a real call for this cargo actually prices" can never
    # drift apart. Deliberately does NOT also resolve GRT bands or liner-terms
    # routing: this is still an editable admin table, so every GT band and
    # every Principal/Receiver liner-routing variant of a charge stays visible
    # and editable -- only the cargo dimension collapses to what's relevant.
    # The cargo's own "Not applicable" $0 override rows (added so the generic
    # bulk fallback doesn't double-charge a cargo with its own dedicated
    # charges) are real for pricing but pure noise on a "what applies" list,
    # so they're dropped here the same way the PDF/Excel export drops them.
    cargo_filter = request.args.get("cargo") or ""
    if cargo_filter:
        rows = _select_cargo_rows(rows, cargo_filter)
        rows = [r for r in rows if not (r["source"] or "").startswith("Not applicable")]

    def bucket(pda_type, group_name):
        return [r for r in rows if r["pda_type"] == pda_type and (r["group_name"] or "Ship Related Expenses") == group_name]

    # "Principal PDA -- Cargo Related Expenses" is normally empty -- it only has
    # rows for cargoes (e.g. Ammonium Nitrate) whose stevedoring-family charges
    # fold onto the Principal under Liner Out/Full Liner Terms (see
    # rate_engine._select_liner_routed_rows). Omitted entirely when empty so it
    # doesn't clutter the page for cargoes that don't use this mechanism.
    principal_cargo_rows = bucket("PDA1", "Cargo Related Expenses")
    sections = [
        {"heading": "Principal PDA — Vessel Related Expenses", "rows": bucket("PDA1", "Ship Related Expenses")},
    ]
    if principal_cargo_rows:
        sections.append({
            "heading": "Principal PDA — Cargo Related Expenses (Liner Out / Full Liner Terms only)",
            "rows": principal_cargo_rows,
        })
    sections += [
        {"heading": "Principal PDA — Others General", "rows": bucket("PDA1", "Others General")},
        {"heading": "Receiver PDA — Cargo Related Expenses", "rows": bucket("PDA2", "Cargo Related Expenses"), "divider_before": True},
        {"heading": "Receiver PDA — Others General", "rows": bucket("PDA2", "Others General")},
    ]
    return render_template(
        "rates.html", sections=sections, cargo_filter=cargo_filter, cargo_types=port_stay.CARGO_TYPES,
    )


@app.route("/rates/<int:rate_id>/update", methods=["POST"])
def update_rate(rate_id):
    amount = float(request.form.get("amount") or 0)
    conn = get_conn()
    conn.execute("UPDATE rate_table SET amount = ?, source = CASE WHEN source LIKE 'TBD%' THEN 'Confirmed by operator ' || ? ELSE source END WHERE rate_id = ?",
                 (amount, now(), rate_id))
    conn.commit()
    conn.close()
    flash("Rate updated.")
    cargo_filter = request.form.get("cargo_filter") or ""
    return redirect(url_for("rates", cargo=cargo_filter) if cargo_filter else url_for("rates"))


@app.route("/tariff")
def tariff_search():
    q = (request.args.get("q") or "").strip()
    authority = request.args.get("authority") or ""

    conn = get_conn()
    authorities_raw = [r["authority"] for r in conn.execute(
        "SELECT DISTINCT authority FROM tariff_reference"
    ).fetchall()]
    authorities = sorted(
        authorities_raw,
        key=lambda a: (AUTHORITY_ORDER.index(a) if a in AUTHORITY_ORDER else len(AUTHORITY_ORDER), a),
    )

    linked_codes = {
        r["tariff_ref_code"] for r in conn.execute(
            "SELECT DISTINCT tariff_ref_code FROM rate_table WHERE tariff_ref_code IS NOT NULL"
        ).fetchall()
    }

    rows = []
    if authority:
        conditions = ["authority = ?"]
        params = [authority]
        if q:
            like = f"%{q}%"
            conditions.append(
                "(code LIKE ? OR description LIKE ? OR section LIKE ? "
                "OR schedule LIKE ? OR remarks LIKE ? OR rate_text LIKE ?)"
            )
            params.extend([like, like, like, like, like, like])
        # ref_id preserves the tariff document's real schedule order (First, Second, ...,
        # Thirteenth, General Terms and Conditions) -- sorting by `schedule` text instead
        # sorts alphabetically ("Eighth" before "Eleventh" before "First"), scrambling it.
        sql = "SELECT * FROM tariff_reference WHERE " + " AND ".join(conditions) + " ORDER BY ref_id"
        if q:
            # A keyword search can match broadly; cap it. A full-authority browse (no
            # keyword) should show everything, or entire schedules silently go missing.
            sql += " LIMIT 500"
        rows = conn.execute(sql, params).fetchall()

    conn.close()

    # group results by schedule -> section for display
    grouped = []
    current_sched = None
    current_sec = None
    for r in rows:
        if r["schedule"] != current_sched:
            grouped.append({"schedule": r["schedule"], "sections": []})
            current_sched = r["schedule"]
            current_sec = None
        if r["section"] != current_sec:
            grouped[-1]["sections"].append({"section": r["section"], "unit_label": r["unit_label"], "rows": []})
            current_sec = r["section"]
        grouped[-1]["sections"][-1]["rows"].append(r)

    return render_template(
        "tariff.html", q=q, authority=authority, authorities=authorities,
        grouped=grouped, result_count=len(rows), linked_codes=linked_codes,
    )


if __name__ == "__main__":
    STORAGE.joinpath("documents").mkdir(parents=True, exist_ok=True)
    STORAGE.joinpath("outputs").mkdir(parents=True, exist_ok=True)
    # use_reloader=False: this project lives in a OneDrive-synced folder, and OneDrive's
    # background file activity was repeatedly false-triggering Werkzeug's file watcher
    # (it was "reloading" on unrelated Python standard-library files), causing brief
    # outages with no real code change behind them. Restart manually after edits instead.
    app.run(host="127.0.0.1", port=5055, debug=True, use_reloader=False)
