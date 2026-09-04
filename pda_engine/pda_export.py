"""
Renders a priced call into the the company PDA layout, as Excel (openpyxl)
and PDF (reportlab). PDA 1 mirrors the manually-digitised TAK26063 KASSIOPI.GR
template exactly: letterhead, To/Att/Date/Ref block, vessel particulars
(including Provisional/Actual rows), a Ship Related Expenses table and a
separate Others General table each with their own subtotal, Grand Total,
bank remittance block, prefunding note, and a Berthed/Sailed line. PDA 2 uses
a simpler single-table layout since there's no reference template for it yet.
"""

from pathlib import Path
from datetime import datetime
from xml.sax.saxutils import escape as _xml_escape
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

FONT = "Arial"
DARKBLUE = "1F3864"
SUBFILL = "D9E2F3"
AMBER = "FFF2CC"
MONEY = '$#,##0.00;($#,##0.00);"-"'
# Rate cells need more precision than 2dp -- Light Dues is $0.095/GRT, which a
# 2-decimal format wrongly rounds to $0.10. This keeps 2-4 decimals (Excel) /
# trims trailing zeros to the same effect (PDF & web).
RATE_MONEY = '$#,##0.00##'


def fmt_rate(value):
    """Format a unit rate keeping its real precision: at least 2 decimals, up to
    4, trailing zeros trimmed. 0.095 -> '0.095', 1411.19 -> '1,411.19',
    5200 -> '5,200.00', 0.0056 -> '0.0056'."""
    s = f"{float(value or 0):,.4f}".rstrip("0")
    intpart, _, dec = s.partition(".")
    if len(dec) < 2:
        dec = (dec + "00")[:2]
    return f"{intpart}.{dec}"

BANK_REMITTANCE = [
    "Bank / Remittance details to be provided by the Agent.",
]

PREFUNDING_NOTE = (
    "NOTE: GPHA, GSA, GMA, Terminal Stevedoring, and Vendors shall receive full payment prior to berthing, "
    "and this PDA is subject to 100% prefunding 5 days prior to expected berthing to enable secure clearances. "
    "Vessels staying 30 consecutive days in the port and/or anchorage, as from declaring arrival by NOR or EOSP "
    "or completed mooring at berth, under the Agent's appointed husbandry, are subject to a $250/day additional "
    "Agency Fee per day from Day 31 onward until departure, except where the vessel is actively engaged in "
    "loading or discharging cargo operations from Day 31 onward."
)


def _pdf_text(value):
    """Escape for reportlab's Paragraph mini-markup and turn embedded newlines
    (e.g. a multi-line Principal billing address: company, VAT no., street,
    postal/city, country) into <br/> so each line renders on its own line
    instead of being collapsed into one."""
    return _xml_escape(str(value)).replace("\n", "<br/>")


def _box():
    thin = Side(style="thin", color="BFBFBF")
    return Border(left=thin, right=thin, top=thin, bottom=thin)


def _parse_created_at(call):
    try:
        dt = datetime.fromisoformat(call.get("created_at"))
        return dt.replace(tzinfo=None)  # Excel/openpyxl rejects tz-aware datetimes
    except Exception:
        return datetime.now()


# Which expense-section groups each PDA shows, in order. The first is the
# "primary" section where any un-grouped line falls; the rest follow. PDA1's
# middle "Cargo Related Expenses" section is normally empty (and skipped) --
# it only has content for cargoes like Ammonium Nitrate under Liner Out/Full
# Liner Terms, where stevedoring-family charges fold onto the Principal
# (see rate_engine._select_liner_routed_rows).
_SECTION_GROUPS = {
    "PDA1": ["Ship Related Expenses", "Cargo Related Expenses", "Others General"],
    "PDA2": ["Cargo Related Expenses", "Others General"],
}


def build_pda_excel(call: dict, priced: dict, pda_types, output_path: str, bl_docs=None):
    """bl_docs: optional list of (bl_number, call_for_bl, priced_for_bl) tuples --
    when given, the PDA2 slot renders once per Bill of Lading (its own sheet,
    each priced off that BL's own tonnage/cbm/receiver) instead of the single
    call-level Receiver PDA. Cargoes without BL rows are unaffected -- this
    param is only ever populated when the call actually has BL rows."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for pda_type in pda_types:
        if pda_type == "PDA2" and bl_docs:
            multi = len(bl_docs) > 1
            for i, (bl_number, bl_call, bl_priced) in enumerate(bl_docs, start=1):
                name = f"PDA2-BL{i}" if multi else "PDA2"
                ws = wb.create_sheet(title=name[:31])
                _render_pda_sheet(ws, bl_call, bl_priced["PDA2"], "PDA2")
            continue
        ws = wb.create_sheet(title=pda_type)
        _render_pda_sheet(ws, call, priced[pda_type], pda_type)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path


def _render_pda_sheet(ws, call, priced_pda, pda_type="PDA1"):
    """Renders a PDA sheet in the the company layout. PDA1 (Principal) matches the
    reference TAK26063 KASSIOPI.GR digitised layout; PDA2 (Receiver) uses the same
    layout addressed to the receiver/consignee (ref + 'A'), with Cargo Related
    Expenses + Others General sections (reference TAK26063A)."""
    is_receiver = pda_type == "PDA2"
    section_groups = _SECTION_GROUPS.get(pda_type, ["Ship Related Expenses", "Others General"])
    primary_group = section_groups[0]
    widths = {"A": 10, "B": 34, "C": 20, "D": 11, "E": 10, "F": 13, "G": 14, "H": 12}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    def setc(cell, value=None, size=10, bold=False, italic=False, color="000000",
             align="left", fill=None, border=False, fmt=None, wrap=False):
        c = ws[cell]
        if value is not None:
            c.value = value
        c.font = Font(name=FONT, size=size, bold=bold, italic=italic, color=color)
        c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
        if fill:
            c.fill = openpyxl.styles.PatternFill("solid", fgColor=fill)
        if border:
            c.border = _box()
        if fmt:
            c.number_format = fmt
        return c

    r = 1
    ws.merge_cells(f"A{r}:D{r}")
    setc(f"A{r}", "AUTOMATED PRO FORMA DISBURSEMENT ACCOUNT", size=13, bold=True, color=DARKBLUE)
    ws.merge_cells(f"E{r}:H{r}")
    title = "PROVISIONAL DISBURSEMENT ACCOUNT" + (" - PDA 2 (RECEIVER)" if is_receiver else "")
    setc(f"E{r}", title, size=11, bold=True, color=DARKBLUE, align="right")
    r += 1
    ws.merge_cells(f"A{r}:D{r}")
    setc(f"A{r}", "Under Development by Lormy", size=9, italic=True)
    r += 2

    # Boxed address block, top-left -- matches the real reference document
    # (TAK26024 ES LEADER.xls: To:/Att: genuinely bordered on 3 sides).
    to_party = call.get("receiver" if is_receiver else "principal") or "-"
    setc(f"A{r}", "To:", bold=True, border=True)
    ws.merge_cells(f"B{r}:D{r}")
    setc(f"B{r}", to_party, border=True, wrap=True)
    # The Principal address may be a multi-line billing block (company, VAT no.,
    # street, postal/city, country) -- grow the row to fit instead of clipping it.
    to_party_lines = to_party.count("\n") + 1
    if to_party_lines > 1:
        ws.row_dimensions[r].height = 14 * to_party_lines
    setc(f"E{r}", "Date:", bold=True, align="right")
    setc(f"F{r}", _parse_created_at(call), align="left", fmt="dd-mmm-yyyy")
    r += 1
    setc(f"A{r}", "Att:", bold=True, border=True)
    ws.merge_cells(f"B{r}:D{r}")
    setc(f"B{r}", call.get("receiver_attn" if is_receiver else "principal_attn") or "-", border=True)
    setc(f"E{r}", "Our Ref:", bold=True, align="right")
    ref = (call.get("our_ref") or "-") + ("A" if is_receiver and call.get("our_ref") else "")
    if call.get("bl_number"):
        ref += f" / BL {call['bl_number']}"
    setc(f"F{r}", ref, bold=True)
    r += 1
    setc(f"E{r}", "Your Ref:", bold=True, align="right")
    setc(f"F{r}", call.get("your_ref") or "-")
    r += 2
    if call.get("bl_number"):
        ws.merge_cells(f"A{r}:D{r}")
        setc(f"A{r}", f"Bill of Lading #: {call['bl_number']}", bold=True)
        r += 1

    ws.merge_cells(f"A{r}:H{r}")
    setc(f"A{r}", "Vessel Particulars", bold=True, color="FFFFFF", fill=DARKBLUE)
    r += 1
    cargo_qty = call.get("cargo_qty_mt") or 0
    port_stay = call.get("port_stay_days") or 0
    particulars = [
        ("Vessel", call.get("vessel") or "-", "IMO No.", call.get("imo") or "-"),
        ("Vessel Type", call.get("vessel_type") or "-", "Flag", call.get("flag") or "-"),
        ("GRT", call.get("grt") or 0, "LOA (m)", call.get("loa") or 0),
        ("Draft (m)", call.get("draft") or 0, "ETA", call.get("eta") or "-"),
        ("Cargo", call.get("cargo_type") or "-", "Port of Call", call.get("port") or "-"),
        ("Provisional Cargo Qty", f"{cargo_qty:,.0f} MT", "Provisional Port Stay", f"{port_stay:.1f} days"),
        ("Actual Cargo Qty", "-", "Actual Port Stay", "-"),
    ]
    agency_fee = next((l["amount"] for l in priced_pda["lines"] if l["charge_code"] == "AGY01"), 0.0)
    particulars += [
        ("Date rcvd Deposit", "-", "Exchange Rate", "-"),
        ("Amount Deposited", "-", "Agency Fee", f"${agency_fee:,.2f}"),
        ("Berthed Date", "-", "Berthed Time", "-"),
        ("Sailed Date", "-", "Sailed Time", "-"),
    ]
    for l1, v1, l2, v2 in particulars:
        setc(f"A{r}", l1, bold=True, border=True, fill="F2F2F2")
        ws.merge_cells(f"B{r}:C{r}")
        setc(f"B{r}", v1, border=True)
        setc(f"D{r}", l2, bold=True, border=True, fill="F2F2F2")
        ws.merge_cells(f"E{r}:H{r}")
        setc(f"E{r}", v2, border=True)
        r += 1
    setc(f"A{r}", "Owner's Details", bold=True, border=True, fill="F2F2F2")
    ws.merge_cells(f"B{r}:H{r}")
    setc(f"B{r}", "-", border=True)
    r += 2

    # RED BOLD prefunding note, positioned BEFORE the expense tables -- matches
    # the real reference document (TAK26024 ES LEADER.xls), where this note is
    # genuinely red and bold and sits right after Vessel Particulars.
    ws.merge_cells(f"A{r}:H{r}")
    setc(f"A{r}", PREFUNDING_NOTE, size=9, bold=True, color="C00000", wrap=True)
    ws.row_dimensions[r].height = 60
    r += 2

    def expense_table(title, lines):
        nonlocal r
        ws.merge_cells(f"A{r}:H{r}")
        setc(f"A{r}", title, bold=True, color="FFFFFF", fill=DARKBLUE)
        r += 1
        heads = ["Code", "Description", "Basis", "Rate ($)", "Qty", "P/Amount ($)", "Actual Amount ($)", "Notes"]
        for i, h in enumerate(heads):
            col = get_column_letter(1 + i)
            setc(f"{col}{r}", h, bold=True, color="FFFFFF", fill=DARKBLUE, border=True,
                 align="center" if i >= 3 else "left")
        r += 1
        first = r
        for line in lines:
            display_code = line.get("tariff_ref_code") or line["charge_code"]
            setc(f"A{r}", display_code, border=True, align="center")
            setc(f"B{r}", line["description"], border=True)
            setc(f"C{r}", line["unit_label"], border=True)
            # Percentage rows (taxes, 1%-of-stevedoring) show the rate as a % so
            # "$0.05" reads as "5%"; the cell stays numeric so =D*E still works.
            rate_fmt = "0%" if line.get("pct") else RATE_MONEY
            setc(f"D{r}", line["rate"], border=True, fmt=rate_fmt, align="right")
            if line.get("stated_only"):
                # Stated for transparency, but no amount and excluded from the SUM.
                setc(f"E{r}", None, border=True)
                setc(f"F{r}", None, border=True)
                note = "Stated, not charged"
            else:
                setc(f"E{r}", line["qty"], border=True, fmt="#,##0.00", align="right")
                setc(f"F{r}", f"=D{r}*E{r}", border=True, fmt=MONEY, align="right")
                note = "PLACEHOLDER - real rate needed" if line["is_placeholder"] else ""
            setc(f"G{r}", None, border=True)
            setc(f"H{r}", note, border=True, size=8, italic=True,
                 color="C00000" if line["is_placeholder"] else "808080" if note else "000000")
            r += 1
        last = r - 1
        ws.merge_cells(f"A{r}:E{r}")
        setc(f"A{r}", f"Sub Total - {title}", bold=True, align="right", border=True, fill=SUBFILL)
        setc(f"F{r}", f"=SUM(F{first}:F{last})", bold=True, border=True, fmt=MONEY, fill=SUBFILL)
        setc(f"G{r}", "", border=True, fill=SUBFILL)
        setc(f"H{r}", "", border=True, fill=SUBFILL)
        subtotal_row = r
        r += 2
        return subtotal_row

    subtotal_rows = []
    for i, group in enumerate(section_groups):
        if i == 0:
            group_lines = [l for l in priced_pda["lines"] if l.get("group", primary_group) == primary_group]
        else:
            group_lines = [l for l in priced_pda["lines"] if l.get("group") == group]
        if group_lines:
            subtotal_rows.append(expense_table(group, group_lines))

    # Bold black "quote our ref" note, positioned AFTER the expense tables but
    # BEFORE Grand Total -- matches the real reference document's actual order.
    ws.merge_cells(f"A{r}:H{r}")
    setc(f"A{r}", "PLEASE QUOTE OUR REFERENCE NUMBER WITH ALL REMITTANCES.", bold=True, size=9)
    r += 1
    ws.merge_cells(f"A{r}:H{r}")
    setc(f"A{r}", "Remittances should be made at least five (5) working days before the arrival of the vessel.", size=9, wrap=True)
    r += 2

    ws.merge_cells(f"A{r}:E{r}")
    setc(f"A{r}", "Grand Total Payable", bold=True, size=11, align="right", fill=AMBER, border=True)
    total_formula = "=" + "+".join(f"F{row}" for row in subtotal_rows) if subtotal_rows else 0
    setc(f"F{r}", total_formula, bold=True, size=11, fmt=MONEY, fill=AMBER, border=True)
    setc(f"G{r}", "", fill=AMBER, border=True)
    setc(f"H{r}", "", fill=AMBER, border=True)
    grand_total_row = r
    r += 2

    if any(l["is_placeholder"] for l in priced_pda["lines"]):
        ws.merge_cells(f"A{r}:H{r}")
        setc(f"A{r}",
             "NOTE: rows marked PLACEHOLDER use $0.00 stand-in rates because this port/cargo rate card does not "
             "yet contain a real figure for that charge. Do not issue this PDA to the client until those rates "
             "are confirmed and entered in the Rate Library.",
             size=8, italic=True, color="C00000", wrap=True)
        ws.row_dimensions[r].height = 30
        r += 2

    # Emphasized (larger, bold) banking block -- matches the real reference
    # document's noticeably bigger 12pt bold remittance/banking text.
    ws.merge_cells(f"A{r}:H{r}")
    setc(f"A{r}", f"Please remit the sum of Grand Total Payable (cell F{grand_total_row}) to:", bold=True, size=12, wrap=True)
    r += 1
    for line in BANK_REMITTANCE:
        ws.merge_cells(f"A{r}:H{r}")
        setc(f"A{r}", line, bold=True, size=12, wrap=True)
        r += 1
    ws.freeze_panes = "A9"
    ws.sheet_view.showGridLines = False

    # Print-ready setup -- landscape (the sheet is 8 columns wide, portrait
    # would clip or force manual rescaling), fit to 1 page wide (tall can run
    # to a 2nd page for a long charge list, which is fine -- width is what
    # clips), centered, no gridlines on the printed page.
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins = PageMargins(left=0.3, right=0.3, top=0.4, bottom=0.4, header=0.2, footer=0.2)
    ws.print_options.horizontalCentered = True
    ws.print_options.gridLines = False


def build_pda_pdf(call: dict, priced: dict, pda_types, output_path: str, bl_docs=None):
    """bl_docs: optional list of (bl_number, call_for_bl, priced_for_bl) tuples --
    when given, the PDA2 slot renders once per Bill of Lading (its own
    print-ready page(s), each priced off that BL's own tonnage/cbm/receiver)
    instead of the single call-level Receiver PDA."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                             leftMargin=7 * mm, rightMargin=7 * mm,
                             topMargin=4 * mm, bottomMargin=4 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleBlue", parent=styles["Title"], textColor=colors.HexColor("#1F3864"), fontSize=14)
    h_style = ParagraphStyle("H", parent=styles["Heading2"], textColor=colors.white, backColor=colors.HexColor("#1F3864"))
    note_style = ParagraphStyle("Note", parent=styles["Normal"], fontSize=7.5, textColor=colors.HexColor("#C00000"))
    # Explicit tight leading -- a multi-line Principal billing address (company,
    # VAT no., street, postal/city, country) can run to 5-6 lines in this style,
    # so the default inherited ~12pt leading (sized for 10pt body text, not this
    # style's 8pt) wastes real vertical budget needed to keep each PDA on 1 page.
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=9.5)
    # Matches the real reference document (TAK26024 ES LEADER.xls): the
    # prefunding note is genuinely red+bold (not small italic), the "quote our
    # reference" note is bold black, and the banking block is noticeably larger.
    prefunding_style = ParagraphStyle("Prefunding", parent=styles["Normal"], fontSize=9, leading=12,
                                       fontName="Helvetica-Bold", textColor=colors.HexColor("#C00000"))
    quote_ref_style = ParagraphStyle("QuoteRef", parent=styles["Normal"], fontSize=9, leading=12,
                                      fontName="Helvetica-Bold")
    bank_style = ParagraphStyle("Bank", parent=styles["Normal"], fontSize=12, leading=14,
                                 fontName="Helvetica-Bold", spaceBefore=0, spaceAfter=0)
    total_style = ParagraphStyle("Total", parent=styles["Normal"], fontSize=11, leading=13,
                                  fontName="Helvetica-Bold", spaceBefore=0, spaceAfter=0)

    def particulars_table(rows):
        """A 4-column label/value/label/value grid, matching the Excel Vessel
        Particulars block. `rows` is a list of (label1, value1, label2, value2)."""
        data = [list(row) for row in rows]
        table = Table(data, colWidths=[85, 155, 85, 155])
        table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F2F2")),
            ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F2F2F2")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BFBFBF")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        return table

    # Plain Python strings in a Table cell never wrap -- a long code like
    # "GSA-BULK-TANKER" or a long Basis label just overflows past the column
    # and collides with the next one. Wrapping those cells as Paragraphs lets
    # them break onto a second line within their own column instead.
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8, leading=9.5)

    def expense_table(lines, title):
        data = [["Code", "Description", "Basis", "Rate", "Qty", "Amount ($)"]]
        subtotal = 0.0
        for line in lines:
            rate_txt = f"{line['rate'] * 100:.0f}%" if line.get("pct") else fmt_rate(line["rate"])
            if line.get("stated_only"):
                qty_txt, amt_txt = "-", "stated only"
            else:
                qty_txt, amt_txt = f"{line['qty']:,.2f}", f"{line['amount']:,.2f}"
                subtotal += line["amount"]
            data.append([
                Paragraph(line.get("tariff_ref_code") or line["charge_code"], cell_style),
                Paragraph(line["description"], cell_style),
                Paragraph(line["unit_label"] or "", cell_style),
                rate_txt, qty_txt, amt_txt,
            ])
        data.append(["", "", "", "", f"Sub Total - {title}", f"{subtotal:,.2f}"])
        # Column widths sized to the real charge-code/description/basis text
        # (measured against the actual rate library) so ordinary rows render
        # on one line; only the rare 60+ char description wraps to a second
        # line, which is normal typesetting, not the overflow/collision bug
        # this replaced.
        table = Table(data, colWidths=[90, 195, 115, 45, 50, 55])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -2), 0.5, colors.HexColor("#BFBFBF")),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#D9E2F3")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ]))
        return table, round(subtotal, 2)

    # Expand PDA2 into one entry per Bill of Lading when bl_docs is given --
    # everything below just renders whatever's in `docs`, so PDA1 (and the
    # single-receiver case with no BL rows) is completely unaffected.
    docs = []
    for pda_type in pda_types:
        if pda_type == "PDA2" and bl_docs:
            for bl_number, bl_call, bl_priced in bl_docs:
                docs.append((pda_type, bl_call, bl_priced[pda_type]))
        else:
            docs.append((pda_type, call, priced[pda_type]))

    story = []
    for n, (pda_type, doc_call, priced_pda) in enumerate(docs):
        call = doc_call
        is_receiver = pda_type == "PDA2"
        section_groups = _SECTION_GROUPS.get(pda_type, ["Ship Related Expenses", "Others General"])
        primary_group = section_groups[0]

        ref = (call.get("our_ref") or "-") + ("A" if is_receiver and call.get("our_ref") else "")
        if call.get("bl_number"):
            ref += f" / BL {call['bl_number']}"
        to_party = call.get("receiver" if is_receiver else "principal") or "-"
        attn = call.get("receiver_attn" if is_receiver else "principal_attn") or "-"

        # Boxed address block, top-left (matches the real reference document:
        # To:/Att: is genuinely bordered), agent letterhead top-right (plain).
        addr_para = Paragraph(f"<b>To:</b> {_pdf_text(to_party)}<br/><b>Att:</b> {_pdf_text(attn)}", small)
        letterhead_para = Paragraph(
            "<b>AUTOMATED PRO FORMA DISBURSEMENT ACCOUNT</b><br/><i>Under Development by Lormy</i>", small)
        header_table = Table([[addr_para, letterhead_para]], colWidths=[260, 260])
        header_table.setStyle(TableStyle([
            ("BOX", (0, 0), (0, 0), 1, colors.HexColor("#1F3864")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (0, 0), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 4))

        story.append(Paragraph(
            "Provisional Disbursement Account &mdash; PDA 2 (Receiver)" if is_receiver
            else "Provisional Disbursement Account", styles["Heading3"]))
        story.append(Paragraph(f"Our Ref: {ref}  |  Your Ref: {call.get('your_ref') or '-'}  |  "
                                f"Date: {_parse_created_at(call).strftime('%d-%b-%Y')}", small))
        story.append(Spacer(1, 4))

        # Full Vessel Particulars grid -- previously missing from the PDF
        # entirely (only a one-line summary existed); now matches the Excel
        # sheet's fields, plus the deposit/agency-fee/berthed-sailed/owner's
        # details block from the real reference document.
        cargo_qty = call.get("cargo_qty_mt") or 0
        port_stay = call.get("port_stay_days") or 0
        agency_fee = next((l["amount"] for l in priced_pda["lines"] if l["charge_code"] == "AGY01"), 0.0)
        particulars_rows = [
            ("Vessel", call.get("vessel") or "-", "IMO No.", call.get("imo") or "-"),
            ("Vessel Type", call.get("vessel_type") or "-", "Flag", call.get("flag") or "-"),
            ("GRT", f"{call.get('grt') or 0:,.0f}", "LOA (m)", f"{call.get('loa') or 0:,.2f}"),
            ("Draft (m)", f"{call.get('draft') or 0:,.2f}", "ETA", call.get("eta") or "-"),
            ("Cargo", call.get("cargo_type") or "-", "Port of Call", call.get("port") or "-"),
            ("Provisional Cargo Qty", f"{cargo_qty:,.0f} MT", "Provisional Port Stay", f"{port_stay:.1f} days"),
            ("Actual Cargo Qty", "-", "Actual Port Stay", "-"),
            ("Date rcvd Deposit", "-", "Exchange Rate", "-"),
            ("Amount Deposited", "-", "Agency Fee", f"${agency_fee:,.2f}"),
            ("Berthed Date", "-", "Berthed Time", "-"),
            ("Sailed Date", "-", "Sailed Time", "-"),
        ]
        if call.get("bl_number"):
            particulars_rows.append(("Bill of Lading #", call["bl_number"], "", ""))
        story.append(particulars_table(particulars_rows))
        owner_table = Table([["Owner's Details", "-"]], colWidths=[85, 395])
        owner_table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F2F2F2")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BFBFBF")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(owner_table)
        story.append(Spacer(1, 4))

        # RED BOLD prefunding note, positioned BEFORE the expense tables --
        # matches the real reference document's actual order and emphasis.
        story.append(Paragraph(PREFUNDING_NOTE, prefunding_style))
        story.append(Spacer(1, 4))

        grand_total = 0.0
        for i, group in enumerate(section_groups):
            if i == 0:
                group_lines = [l for l in priced_pda["lines"] if l.get("group", primary_group) == primary_group]
            else:
                group_lines = [l for l in priced_pda["lines"] if l.get("group") == group]
            if not group_lines:
                continue
            table, sub = expense_table(group_lines, group)
            story.append(table)
            story.append(Spacer(1, 4))
            grand_total = round(grand_total + sub, 2)

        # Bold black "quote our ref" note, positioned AFTER the expense tables
        # but BEFORE Grand Total -- matches the real reference document's order.
        story.append(Paragraph(
            "PLEASE QUOTE OUR REFERENCE NUMBER WITH ALL REMITTANCES. Remittances should be made at least "
            "five (5) working days before the arrival of the vessel.", quote_ref_style))
        story.append(Spacer(1, 4))

        story.append(Paragraph(f"<b>Grand Total Payable: ${grand_total:,.2f}</b>", total_style))
        story.append(Spacer(1, 2))

        if any(l["is_placeholder"] for l in priced_pda["lines"]):
            story.append(Paragraph(
                "NOTE: rows using a $0.00 placeholder rate need a real Takoradi tariff figure before this PDA is issued.",
                note_style))
            story.append(Spacer(1, 4))

        # Emphasized (larger, bold) banking block -- matches the real reference
        # document's noticeably bigger 12pt bold remittance/banking text.
        story.append(Paragraph(f"Please remit the sum of Grand Total Payable (${grand_total:,.2f}) to:", bank_style))
        for line in BANK_REMITTANCE:
            story.append(Paragraph(line, bank_style))

        # Each PDA (or each BL-scoped Receiver PDA) is its own print-ready page --
        # the next document always starts fresh rather than running on.
        if n < len(docs) - 1:
            story.append(PageBreak())

    doc.build(story)
    return output_path
