# Pro Forma Disbursement Account Platform (local prototype)

**Prototype &middot; Developed by Lormy** &mdash; Takoradi-first, for the company.

A working, local implementation of the MVP scope in `Takoradi_PDA_Automation_Platform_PRD_v1.docx` /
`Implementation_Plan_v1.docx`: upload a vessel-particulars file, extract fields, run the Business Rule
Pack v1 to decide PDA 1 vs PDA 1+2, price every charge line against a rate table, and export a
branded PDA in Excel and PDF.

**This is not the Power Apps / Azure AI Document Intelligence / Dataverse stack the PRD names** — that
needs your own Microsoft 365/Azure tenant, subscriptions, and credentials, none of which are available
here. Everything below is a self-contained Python/Flask substitute that implements the same pipeline
(Modules A-H) so you have something to actually click through today. Swapping in the real Azure stack
later means replacing `pda_engine/extraction.py` with an Azure AI Document Intelligence call — the
rules engine, rate engine, data model, and export layer don't need to change.

## Run it

```
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5055

### Optional: turn on AI extraction (Claude API)

By default the platform uses the offline heuristic extractor below. To use Claude's vision/PDF
understanding instead — which also reads scanned PDFs and photos of paperwork, not just
text-layer documents — set an Anthropic API key before running the app:

```
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python app.py

# bash
export ANTHROPIC_API_KEY="sk-ant-..."
python app.py
```

Get a key at [console.anthropic.com](https://console.anthropic.com). This calls the Claude API
and is billed to your own Anthropic account per request — nothing runs unless you upload a file
on the New Call page. The New Call page shows which extractor is active. If the API call fails
for any reason (no key, network, rate limit), the app automatically falls back to the offline
extractor and tells you why. Optionally override the model with `ANTHROPIC_MODEL` (default
`claude-opus-4-8`).

## What's real vs. placeholder

- **PDA 1 and PDA 2 rates** (`data/rate_library_takoradi_clinker.json`) are cross-checked against the
  official **GPHA Port Tariff, August 2023** (334-page PDF, digitized copy also used) as of 2026-07-11.
  Pilotage, Towage, Mooring/Unmooring, Shifting, Anchorage, Light Dues, ISPS, and PIDD all matched the
  the company `TAK26063 KASSIOPI.GR.xls` source exactly against the tariff's 30,000-40,000 GT band —
  no changes needed there. Two real problems turned up in that reconciliation and have been fixed:
  - **"Port Dues on Vessels" (GPHA code 1A1001, $0.18/GT, min $500) was tried, then removed again** —
    initially added because it's a real GPHA charge that was missing from the rate table entirely, but
    its own tariff remark restricts it to **"vessels that did not load/discharge cargo or passengers
    during their call."** Every call this platform prices today is a cargo-working call (Takoradi clinker
    discharge, Free Out) — so it's categorically inapplicable here, not just absent from the two real
    the company PDAs checked so far. Removed entirely from the rate library (not left as an inactive
    placeholder) — the full tariff entry stays in `tariff_reference` (code 1A1001) if a future module ever
    prices a non-cargo-working call type.
  - **"Harbour Rent" (GPHA calls it *Berth Occupancy Charge*) uses the wrong rate for the vessel's size
    if you use a flat number.** GPHA bands the daily rate by **LOA** (not GRT) — Schedule 2.A.1. Per
    the company convention, Harbour Rent is billed as **Provisional Port Stay (days) x the LOA-band daily
    rate** — `pda_engine/rate_engine.py` (`harbour_rent_line()`) picks the correct LOA band automatically
    and produces one line item, still labeled "Harbour Rent" on every PDA 1, positioned directly under
    Mooring/Unmooring in the Ship Related Expenses list.
  - **PDA 2 cargo-related lines are now populated with real GPHA figures**: Port Dues on Cargo (Bulk
    Clinker, Takoradi, $3.71/tonne), GPHA Stevedoring (dry bulk import, grabbing, $4.63/tonne), Labour
    Overtime (dry bulk grabbing, $0.70/tonne), and General Port Cleaning Dues ($0.30/tonne, mapped to
    the old "Bulk Documentation / Port Cleaning" line). These are large — for a 58,420 MT cargo they sum
    to roughly $545,000, dwarfing PDA 1. **Sanity-check this total against a real invoice before trusting
    it** — it's transcribed correctly from the tariff document, but hasn't been checked against an actual
    issued PDA 2.
  - Every rate table row's `source` field now cites its exact GPHA Schedule and code (or explains why it
    still can't be sourced from GPHA — see below), visible in the Rate Library page.
  - Generating a PDA for GRT 34,542 / LOA 199m / 58,420 MT Bulk Clinker (auto-calculated 8.0-day stay)
    now gives PDA 1 = **$56,736.57** and PDA 2 = **$545,642.80** (up from $0.00 placeholder). The
    original TAK26063 document assumed a manually-entered 5-day stay ($47,573.94 PDA 1 total) — the
    auto-calculated figure is longer because 58,420 MT ÷ 7,000 MT/day ≈ 8.3 days, not 5; check that
    7,000 MT/day Takoradi clinker rate against real experience if it looks off.
  - **Still placeholder, and will stay that way until you supply the number** — these are genuinely not
    GPHA charges, so the tariff document can't answer them: **GSA Levy** (Ghana Shippers' Authority is a
    separate body with its own tariff), **Admin/Release** (a the company internal agency fee), **Draft
    Survey** (a private surveyor's quote), and **Taxes** (source unclear — not in the GPHA tariff).
    **Labour Delays** now has a real per-man-hour rate ($8.00, GPHA code 3L2001) but needs an actual
    delay-hours figure from the day — there's a "Labour Delay Hours" driver field on the call form that
    defaults to 0.
  - **Anchorage** only implements the tariff's first-10-days band (11-30 days is cheaper, 31-60 cheaper
    still, plus a $250/day minimum) — fine for a normal call, but will overstate a long anchorage wait.
- **Provisional Port Stay is auto-calculated, with an optional manual override.** For the 9 known
  Takoradi bulk cargoes (`pda_engine/port_stay.py`), the auto figure is Cargo Quantity ÷ the company's
  typical Takoradi discharge/load rate for that cargo, rounded to the nearest whole day (e.g. 58,420 MT
  of Bulk Clinker ÷ 7,000 MT/day ≈ 8.0 days). These per-cargo rates are the company's own Takoradi
  operating assumptions, not a GPHA tariff figure. **It's a single editable box**: on the New Call form
  it auto-fills with the calculated days when you pick a cargo type and quantity, but you can type straight
  over it — different receivers discharge at different rates, so the operator has the final say. Whatever is
  in the box is what's used; if left blank the server falls back to the auto figure. On the Review screen
  the box holds the stored value and stays editable. `port_stay.compute_port_stay_days()` returns the box
  value when > 0, else the auto figure; `port_stay.auto_port_stay_days()` always returns the auto figure
  (used by the live JS to pre-fill and show the reference). Selecting **"Other"** cargo (no standard rate)
  just means you type the days in. **Harbour Rent = LOA-band daily rate × the effective port stay, used
  exactly as entered** — no re-rounding, so a 5.5-day entry bills 5.5 × rate.
- **Gangway watchmen scale with the Provisional Port Stay.** The two gangway lines are billed **per port
  stay day** (Day watchman $120/day = 1 × 12h × $10/hr; Night watchmen $240/day = 2 × 12h × $10/hr),
  driven by `port_stay_days` — so a 5-day stay is $600 + $1,200 and an 8-day stay is $960 + $1,920,
  automatically. (Previously these used fixed 60/120-hour fields that ignored the port stay.) The old
  gangway-hours input fields are gone.
- **The New Call and Review forms' "Operational Drivers" (movements, shifting, anchorage, 3rd-party cost)
  are in a collapsible section**, collapsed by default with sensible defaults pre-filled, so the forms stay
  focused on the essentials. **Applicable Liner Terms is deliberately kept out of that collapse and always
  visible**, since it's the key decision that drives whether a Receiver PDA is produced at all. (The
  in-app preview browser needed an explicit `details:not([open]) .drivers-body { display:none }` rule in
  `base.html` because its native `<details>` didn't collapse on its own.)
- **Port of Call is a dropdown** (Takoradi / GHTKD, Tema / GHTEM) — **Tema is listed but disabled**,
  since the rate library, port-stay formula, and reconciliation above are Takoradi-only for now. Wire up
  Tema by adding its rates to a new/extended rate library and its own port-stay divisors, then remove the
  `"supported": False` flag on the `PORTS_OF_CALL` entry in `app.py`.
- **Tariff Reference (new): a full, searchable copy of the GPHA Port Tariff lives in the app.** The
  entire digitized document — all 13 schedules, ~1,400 rate rows, plus the General Terms and Conditions
  — was imported into a `tariff_reference` DB table (`data/gpha_tariff_reference.json`, extracted from a
  pre-existing digitized HTML copy) and is browsable/searchable by code or keyword at `/tariff`. This is
  the *reference catalog*; `rate_table` (Rate Library) stays the small, curated, pricing-ready subset —
  the two are linked by a `tariff_ref_code` column so each Rate Library row can show a "View source" link
  back to its exact tariff entry. Accuracy was spot-checked 2026-07-12 by rendering actual PDF pages to
  images (the PDF has no text layer — it's a scan) and comparing values directly: 1A1001, 1B1002, 2A3004,
  2A4004 all matched exactly. Other authorities can be added later the same way — digitize the document,
  extract to a JSON file shaped like `gpha_tariff_reference.json` tagged with the right `authority`, seed
  it into the same table.
  - **GMA (Ghana Maritime Authority) Safety Levy added 2026-07-12**: digitized from `GMA SAFETY LEVY.pdf`
    (13 rows, `data/gma_safety_levy_reference.json`, authority `GMA`) — a single-page "SAFETY CHARGE"
    schedule giving a per-GT rate by vessel type across three rate eras (1st Old Law, 2nd Old Law, New
    Law; the document doesn't date these, so "New Law" is assumed current but not confirmed). This
    **closes a real gap**: the existing `LI2009` "Ghana Maritime Authority Levy" rate table row ($0.12/GT)
    previously had to be marked "not cross-checkable" for lack of a GMA source document — its rate now
    matches this document's Bulk Carrier / New Law figure exactly, and its `source` field and
    `tariff_ref_code` (`GMA-SL-BULK`) have been updated accordingly. Seeded additively via
    `db.py::_seed_tariff_authority_if_missing()`, scoped strictly to `authority='GMA'` so it can never
    touch the GPHA rows even on a `reseed_tariff_reference` run. The other 12 vessel-type rates (Container,
    Tanker variants, RoRo, Reefer, etc.) are in the Tariff Reference catalog but not yet wired into any
    rate_table row, since the platform only prices Bulk Carrier calls today.
    - **Updated 2026-07-15** from a cleaner source (`SAFETY CHARGE FEES_GMA.xlsx`, an actual spreadsheet
      instead of a scanned photo). All 13 original rows confirmed numerically identical; the cleaner source
      also resolved the earlier "hand-marked checkmark" note on Reefer (was just a mark on the printed page,
      not real data) and added a genuinely new 14th row, **Passenger** (`GMA-SL-PASSENGER`) — confirmed by
      the user to follow the same progressive/two-tier basis as Container: first 40,000 tons at $0.50, every
      extra ton over 40,000 at $0.25. `LI2009` (Bulk Carrier) is untouched since its numbers didn't change. Applied via
      a new `db.py::refresh_tariff_authority(seed_path, authority)` — an explicit, authority-scoped
      delete-and-reinsert for when a source document is updated (distinct from
      `_seed_tariff_authority_if_missing()`, which only fires on first-ever startup); verified GPHA's 1,573
      rows, GSA's 8 rows, and all 21 existing calls were untouched by the refresh.
  - **GSA (Ghana Shippers' Authority) Service Charge Rates added 2026-07-14**: digitized from a photo of
    "GHANA SHIPPERS' COUNCIL — SERVICE CHARGE RATES PER METRIC TON" (8 rows,
    `data/gsa_service_charge_reference.json`, authority `GSA`). The source document's own letterhead says
    "Council" — per explicit user instruction the app keeps labeling the charge "Ghana Shippers' Authority
    (GSA)" everywhere regardless. **This is the real source for the `GSALEVY` rate table line**, which was
    previously a single flat $0.20/tonne "editable default, unverified" row borrowed from one receiver PDA.
    The document shows Clinker gets its own cheaper carve-out (**$0.20/tonne**) separate from the general
    **Bulk Cargo / Tanker rate ($0.35/tonne)** — so `GSALEVY` is now **two rate_table rows, both
    independently editable**, and the rate engine auto-selects the right one by the call's cargo type (see
    below), closing the request to "intelligently detect the cargo and apply the rate but still make that
    editable."
  - **Authority selection is now required to see anything at all.** The dropdown defaults to "Select
    authority" and the page shows nothing (no cross-authority schedule browse, no rows) until one is
    chosen; picking an authority alone (no keyword needed) then shows every charge for that authority,
    and a keyword can further narrow within it. `app.py::tariff_search()` only queries
    `tariff_reference` at all when `authority` is set.
  - **Fixed 2026-07-12: browsing GPHA alone was silently dropping most of the tariff.** Rows were sorted
    `ORDER BY schedule` (alphabetical on the schedule name — "Eighth Schedule" sorts before "First
    Schedule"), and a `LIMIT 500` meant for keyword searches was also applied to a full-authority browse,
    cutting off partway through the Fourth Schedule and silently dropping Schedules 5–13 and the entire
    General Terms and Conditions section (185 rows). Now sorted `ORDER BY ref_id` (preserves the tariff
    document's real order) and the `LIMIT 500` only applies when a keyword is typed — browsing a whole
    authority with no keyword shows every row. Verified: selecting GPHA alone now returns all 1,573 rows
    in correct schedule order, ending with General Terms and Conditions.
  - **"Jump to Schedule" list** appears above the results whenever more than one schedule is present —
    a link per schedule (with its row count) that jumps straight to that section, plus a "Back to top"
    link at the end of every schedule card. Skipped for single-schedule results (e.g. browsing GMA alone)
    since there's nothing to jump between.
  - **Authority dropdown order is now explicit, not alphabetical**: `app.py::AUTHORITY_ORDER = ["GPHA",
    "GMA"]` puts GPHA first (it's the primary tariff — most schedules, most rate_table rows in use), with
    any future authority not yet in that list falling after them alphabetically. Previously alphabetical
    sorting put GMA above GPHA.
- **Field extraction accepts pasted email text, email files, documents, and scans** — three intake routes
  on the New Call page, all filling the same form (each field flagged with a confidence badge to review):
  - **Paste the appointment / nomination email into the box → "Extract details from this text (AI)".**
    Claude reads the pasted text and fills the whole form — vessel, IMO, GRT/LOA/draft, cargo + quantity,
    principal, receiver/consignee, refs, ETA, *and the Applicable Liner Terms dropdown* (mapped to an exact
    option). `pda_engine/ai_extraction.py::extract_vessel_particulars_ai_from_text()`.
  - **Upload a saved email (`.eml` or `.msg`).** `pda_engine/email_intake.py::parse_email()` pulls out the
    body text *and every attachment*, then hands the body + each attachment (PDF/image natively, docx/xls as
    text) to Claude in **one call** — so the common "particulars are in the attached PDF/spreadsheet, terms
    are in the body" case is read as a whole. `.eml` uses the stdlib `email` module; `.msg` uses `extract-msg`.
  - **Upload a document or scan** (`.pdf`, `.docx`, `.xls`, `.xlsx`, `.jpg`, `.png`). Same AI extractor.
- **Field extraction** has two engines, selected automatically:
  - **`pda_engine/ai_extraction.py`** (used when `ANTHROPIC_API_KEY` is set) sends the content straight
    to the Claude API — PDFs and images (including scans/photos with no text layer) go in as native
    document/vision content, Word/Excel docs as extracted text, pasted text and email bodies as text —
    and gets back strict JSON matching the call schema, via `output_config.format` (a JSON-schema-constrained
    response, not prompt-and-hope). This is real OCR/computer-vision extraction, not a heuristic. It reads
    all the supplied content (email body + attachments) together in a single call.
  - **`pda_engine/extraction.py`** (fallback, or when no API key is configured) is a heuristic
    label-scanner, not a trained document-AI model. It reads `.xls`/`.xlsx` (cell grid), `.pdf` (text
    layer + any tables, via pdfplumber), and `.docx` (paragraphs + tables, via python-docx), reducing
    all of them to the same label/value row scan. Scanned/image-only PDFs have no text layer and
    won't extract anything with this engine — that needs either the Claude engine above or OCR (e.g.
    Tesseract), which isn't installed in this environment.

  Both engines flag every field's confidence so you can catch a bad guess before generating a PDA.
- **Load/Discharge (Liner) Terms dropdown drives the PDA 1 vs PDA 1 + PDA 2 decision.** The New Call and
  Review forms have a "Applicable Liner Terms" dropdown with the full list: Free Out (FO), FIO, FIOS,
  FIOST, LIFO, FILO, Free In (FI), Liner/Gross Terms, LILO, Other. This is a **discharge/import** platform,
  so the deciding factor is who pays the OUT (discharge/cargo-handling) leg:
  - **"Free Out" family (FO, FIO, FIOS, FIOST, LIFO)** → discharge cost is on the cargo's account, so a
    separate **Receiver (Consignee) PDA** is prepared *in addition to* the Principal PDA. This is the
    normal bulk-clinker case (real example: `TAK26063` Principal + `TAK26063A` Receiver to Kumasi Cement).
  - **"Liner Out" family (FILO, Free In, Liner/Gross, LILO)** → the vessel/owner covers discharge, so there
    is no separate receiver account — **Principal PDA only**. (Actually folding the stevedoring lines into
    the Principal PDA for these terms is future work.)

  **Default per cargo:** dry-bulk import cargoes that are normally Free Out — clinker, gypsum, limestone,
  slag, coal, grains, wheat — pre-select **Free Out (FO)** in the dropdown automatically (both client-side
  on cargo change and server-side in `create_call`/`reprice_call`, via
  `rules_engine.default_liner_terms_for_cargo()`). It's applied silently and only when the operator hasn't
  already chosen a term — they keep full freedom to change it. Export/other cargoes (cocoa, bauxite,
  manganese, quicklime) get no default.

  **Correction history:** an earlier build (based only on `TAK26024 ES LEADER`, which happened to be a
  single principal-only document) had Free Out mapped to "PDA 1 only". The KASSIOPI.GR pair — same vessel,
  Free Out, *with* a receiver PDA — showed that was backwards: Free Out is exactly when a receiver PDA IS
  needed. The rule was reversed accordingly.
- **Rules engine** (`pda_engine/rules_engine.py`) checks the selected liner term first; otherwise falls
  back to a keyword scan of pasted appointment text; otherwise defaults to Principal + Receiver (since
  Takoradi bulk clinker is Free Out by default). Every decision is logged with the term/clue that fired.
- **Receiver (PDA 2) charges match `TAK26063A` exactly** (`data/rate_library_takoradi_clinker.json`,
  `group` = "Cargo Related Expenses" / "Others General"). Cargo Related: Port Dues on Cargo (GPHA
  $3.71/t), GPHA Stevedoring ($4.63/t), Stevedoring Labour Overtime ($0.70/t), **Estimated Labour Delays
  = 1% of the Stevedoring cost** (editable), GETFUND+NHIL & VAT on Stevedoring (**stated as lines with
  their rate but no amount and excluded from the total**, matching the real doc), Port Cleaning/Cargo
  Documentation ($0.30/t), GSA Levy ($0.20/t). Others General: Admin/Release Fee ($0.20/t) + its
  GETFUND+NHIL/VAT, Draft Survey ($1,200) + its GETFUND+NHIL/VAT, HB service fee on 3rd-party bills (8%).
  GSA Levy, Admin/Release, Draft Survey and the HB fee are **pre-filled editable defaults** from the
  reference PDA (not GPHA statutory rates). Verified: for 58,420 MT clinker the Receiver PDA reconciles to
  Cargo Related **$560,031.65** + Others General **$15,460.80** = **$575,492.45**, matching TAK26063A.
- **Two new rate-engine bases** power the above (`pda_engine/rate_engine.py`): `percent_of_charge`
  (amount = rate × an earlier line's amount, used for the 1%-of-stevedoring delay estimate and every
  GETFUND/VAT tax line) and `stated_only` (line shown with its rate but no amount, excluded from the
  subtotal — the GPHA stevedoring taxes).
- **Cargo-differentiated rates, auto-selected by the system but still user-editable** (`rate_table.cargo_match`
  column, `rate_engine.py::_select_cargo_rows()`). A charge can have multiple rate_table rows sharing one
  `charge_code` — one or more tagged with an exact `cargo_match` (a carve-out rate for that specific cargo)
  plus one left blank (the generic fallback for every other cargo). The engine picks exactly one row per
  call automatically based on the call's Cargo Type, while every row stays independently visible and
  editable on the Rate Library page. First use: `GSALEVY` (GSA Levy) — $0.20/tonne for Bulk Clinker,
  $0.35/tonne (the general Bulk Cargo/Tanker rate) for every other cargo. Verified: a 30,500 MT clinker call
  and an identical-quantity gypsum call correctly select $0.20 vs $0.35 respectively, and the original
  58,420 MT clinker regression total ($560,031.65 Cargo Related) is unchanged.
- **Second use of the same mechanism: Port Dues on Cargo (`1B1002`) is now cargo-differentiated across the
  9 dry-bulk cargoes**, sourced from the real per-cargo rows in GPHA Schedule 1.B (checked against
  `tariff_reference` before building): Clinker & **Slag $3.71/t** (GPHA's own remark on 1B1002 groups Slag
  with Clinker — "Including Pozzolana and Slags"), **Gypsum $5.04/t** (1B1003), **Limestone $3.71/t**
  (1B1004), **Wheat $2.66/t** (1B1001 "Bulk Grains" — Wheat has no dedicated code), and a **Dry Bulk
  Imports NOS fallback $5.04/t** (1B1008) for Quicklime or "Other". **Bauxite, Manganese, and Cocoa are
  deliberately left as $0.00 PLACEHOLDER rows, not silently priced** — GPHA only tariffs those as *export*
  cargo (codes 1B8001–1B8003); this whole Receiver-PDA/Free-Out architecture assumes an import/discharge
  call, so bolting an export rate onto an import-framed PDA would be structurally wrong, not just a wrong
  number. Verified all 9 cargo types individually plus the 58,420 MT clinker regression (unchanged).
- **Both PDAs render as tabs and export together.** Under a Free Out call the Review page shows an active
  **Principal (PDA 1)** tab and **Receiver (PDA 2)** tab (each split into its own two sections with
  subtotals + grand total), and the Excel/PDF export contains both a PDA1 and a PDA2 sheet — the Receiver
  sheet addressed to the consignee with ref `<OurRef>A`. Liner-out terms still produce PDA 1 only.
- **Environmental Charge (`ENV01`) was mislabeled and mispriced (fixed 2026-07-15)**: sourced only as
  "TAK26063 KASSIOPI.GR.xls" and flat-rated at $1,942.50, it's actually **GPHA's Garbage Collection Charge**
  (Twelfth Schedule, Ship Waste Reception Facilities / MARPOL 73/78) — a **5-tier GRT-banded charge**
  (12A1001–12A1005: $1,050 up to 3,000 GT, $1,050 for 3,001–6,000, $1,575 for 6,001–12,000, $1,785 for
  12,001–25,000, $1,942.50 above 25,000). Every call priced so far happened to fall in the top band, which
  is exactly why the flat rate never looked wrong. "Environmental Charge" stays the clean printed PDA
  label (per the user: that's a platform label, not a GPHA term) — only the `unit_label`/`source`/
  `tariff_ref_code` carry the band and real GPHA code. Built as **5 rate_table rows with new `grt_min`/
  `grt_max` columns**, selected by a new `rate_engine.py::_select_grt_band_rows()` (same pattern as the
  cargo-match mechanism, one row wins per call based on GRT), kept editable per band in the Rate Library —
  not hardcoded Python. **Bug caught and fixed during this build**: `_select_cargo_rows()` was collapsing
  the 5 ENV01 rows down to one *before* the GRT selector ever ran, since it mistook "5 rows, none with a
  cargo_match" for "a cargo-varying charge with no match, use the first fallback." Fixed so a group only
  collapses by cargo when at least one row in it actually sets `cargo_match` — otherwise every row passes
  through unchanged for the GRT selector to choose from. Verified: all 5 bands select correctly at their
  exact GT boundaries, both historical regression calls (GRT 34,542 and 35,607) still resolve to $1,942.50,
  and the fix didn't disturb GSA Levy / Port Dues on Cargo cargo-differentiation or the ES LEADER totals.
- **Rate Library page reorganized (2026-07-15) to read like the real PDA structure**, not a flat list:
  four sections in order — *Principal PDA: Vessel Related Expenses*, *Principal PDA: Others General*, a
  visual "Receiver PDA" divider, then *Receiver PDA: Cargo Related Expenses*, *Receiver PDA: Others
  General*. `app.py::rates()` buckets rows by `(pda_type, group_name)` in Python (order preserved from
  `rate_id`, so cargo variants of the same charge — e.g. all 9 Port Dues on Cargo rows, both GSA Levy rows
  — stay grouped together); `templates/rates.html` renders each bucket as its own headed table. The
  intent: open the Rate Library and see every charge for an Import/Discharge Bulk Cargo call at Takoradi,
  Clinker's rate sitting right next to every other bulk cargo's rate for the same charge, extendable as
  more cargoes get their own rows.
- **GETFUND Levy + NHIL (5%) and VAT (15%) are now charged on the company's own local service fees** —
  Agency Fee and Gangway Watchmen (Day + Night combined) — not on GPHA statutory dues. Four line items
  appear in PDA 1's "Others General" table. **As of 2026-07-15 these are proper, independently editable
  Rate Library rows** (`GET-AGENCY`, `VAT-AGENCY`, `GET-GANGWAY`, `VAT-GANGWAY`), not hardcoded Python —
  matching how the Receiver-side taxes (Admin/Release, Draft Survey) already worked, so every tax rate on
  both PDAs now lives in one place. The Gangway pair uses a comma-separated `driver` (`"GW-DAY,GW-NIGHT"`)
  since the tax applies to the *combined* Day + Night charge — `percent_of_charge` now sums every
  charge_code listed in `driver`, not just one. Verified against `TAK26024 ES LEADER.xls`: Others General
  subtotal still reproduces the real document's **$6,048.00** exactly (Agency 3600 + GETFUND/NHIL 180 +
  VAT 540 + Gangway Day 480 + Gangway Night 960 + GETFUND/NHIL 72 + VAT 216), and PDA 1's Grand Total is
  still **$38,814.02** — unchanged after the conversion from code to data.
- **Review page shows Ship Related Expenses and Others General as two separate sub-tables**, each with
  its own subtotal plus a Grand Total line (`templates/review.html`) — matching the Excel/PDF export's
  layout instead of one flat undifferentiated list. Applies to PDA 1 only; PDA 2 keeps a single table.
- **Review page is now tabbed: Principal (PDA 1) / Receiver (PDA 2).** PDA 2 is always computed and saved
  in the database regardless of the billing decision — nothing is thrown away — but when the call is
  `PDA1_ONLY` (e.g. Free Out liner terms), the Receiver tab is shown disabled ("not applicable") and its
  figures aren't rendered at all, matching real the company practice of not preparing a receiver account
  under those terms. **Exports follow the same rule**: `app.py::_pda_types_for()` now returns `["PDA1"]`
  only when `billing_decision == "PDA1_ONLY"`, so the downloaded Excel/PDF for a Free Out call contains a
  single PDA 1 sheet — matching what a real the company free-out PDA document actually looks like — instead
  of always bundling an always-unbilled PDA 2 sheet.
- **Generated PDA letterhead reads "AUTOMATED PRO FORMA DISBURSEMENT ACCOUNT" / "Under Development by
  Lormy"** (both Excel and PDF, both PDA1 and PDA2), replacing the earlier "THE COMPANY" + Takoradi
  office address letterhead — `pda_engine/pda_export.py`. Verified live against a real user call.
- **PDA layout redesigned (2026-07-15) to match the real reference document's actual visual structure**
  (`TAK26024 ES LEADER.xls`, inspected cell-by-cell for borders/font colour/size, not just data), on
  **both Excel and PDF**:
  - **Boxed "To:"/"Att:" address block, top-left** (bordered, matching the real document), agent
    letterhead top-right (plain, unbordered).
  - **The GPHA/GSA/GMA prefunding note is genuinely red and bold** in the source — was previously
    small italic red at the very end of the document; now bold red, positioned right after Vessel
    Particulars, **before** the expense tables (matching the source's actual order).
  - **The "PLEASE QUOTE OUR REFERENCE NUMBER..." note is bold black** (not red) and sits **after the
    Others General subtotal, before Grand Total** — previously positioned near the very end, after the
    bank block.
  - **The banking/remittance block is noticeably larger and bold** (12pt) in the source, a deliberately
    emphasized closing block — previously rendered in the same small body text as everything else.
  - Full corrected order: boxed address + letterhead → title/particulars → red bold prefunding note →
    Ship Related (or Cargo Related) table → Others General table → bold "quote ref" note → Grand Total →
    emphasized banking block → Berthed/Sailed line.
  - Verified: all regression totals unchanged (Ship Related $32,766.02, Others General $6,048.00, Grand
    Total $38,814.02), address box border and red-bold/12pt-bold styling all confirmed applied via direct
    openpyxl cell inspection, and the new layout verified live against a real user call (call_id 19).
- **PDF was missing the entire Vessel Particulars grid (fixed 2026-07-15)** — the PDF export never had a
  proper particulars table at all, only a one-line summary (Our Ref/Vessel/Cargo/Port); IMO, Flag, GRT,
  LOA, Draft, ETA, Vessel Type, Provisional/Actual Cargo Qty and Port Stay never appeared on the PDF.
  Found by the user pasting the real reference document's particulars block and asking why none of it
  showed up. Built a proper `particulars_table()` for the PDF mirroring the Excel grid, plus added fields
  **both formats were missing entirely**: Date rcvd Deposit, Amount Deposited, Exchange Rate, Agency Fee
  (cross-referenced from the priced `AGY01` line), Berthed Date/Time, Sailed Date/Time, and Owner's
  Details — all blank/manual-fill placeholders except Agency Fee, matching the real document's own
  pre-arrival "some fields filled in later" convention. Removed the old single "Date & Time Vessel
  Berthed/Sailed" line that previously sat at the very end of both documents, now superseded by the
  properly-placed Berthed/Sailed Date+Time rows in the particulars block. Verified: Grand Total unchanged
  ($38,814.02), all fields present on both Excel and PDF, confirmed live against the user's real call.
- **PDF/Excel made print-ready (2026-07-17)** — the full layout redesign above made the documents visually
  correct but not print-clean: the PDF spilled a single PDA across 2+ pages with no break between PDA1 and
  PDA2 (3 pages total for a real 2-PDA call), and the Excel had no print setup at all (no orientation/scale/
  margins — Print Preview would clip the 8-column sheet in unscaled portrait).
  - **Excel**: `ws.page_setup` set to landscape, `fitToWidth=1`/`fitToHeight=0` with `pageSetUpPr.fitToPage`,
    tight `PageMargins`, centered, gridlines off — verified via an openpyxl round-trip load.
  - **PDF**: tightened `SimpleDocTemplate` margins and inter-section `Spacer`s, and replaced the plain
    `Spacer` between PDA1 and PDA2 with a real `PageBreak()` so each PDA always starts on its own page.
  - **Found and fixed a real (pre-existing, not a regression from this session) text-collision bug** while
    verifying: `expense_table()`'s Code/Basis cells were plain strings in columns too narrow for real values
    (`GSA-BULK-TANKER`, `GMA-SL-BULK`, `GET-GANGWAY`, etc., and Basis text like "Minimum (12,001-25,000 GT)")
    — plain strings in a reportlab Table never wrap, so the text silently overflowed into the next column
    instead (e.g. rendered as "GMA-SL-BULKGhana Maritime..."). Fixed by wrapping Code/Description/Basis cells
    in `Paragraph` (so they wrap instead of overflow) and re-sizing all 6 columns to real measured widths
    (`stringWidth` against the actual rate library) so ordinary rows still render on one line; only the one
    genuinely long GSA Levy description now wraps to 2 lines, which is normal typesetting, not a defect.
    (Landscape orientation was tried for the PDF too, matching Excel, but rejected — it trades vertical room
    for horizontal, and vertical room is the scarce resource for one-page-per-PDA fitting; portrait with
    correctly-sized columns fit both requirements.)
  - Verified live against call_id 19 (NALUHU): PDF is exactly 2 pages (1 per PDA, clean break), Excel print
    setup round-trips correctly, both PDA totals unchanged ($41,205.10 / $354,557.92), no more text overlap.
- **Principal billing address is now extracted and rendered as a full multi-line address, not just a company
  name (2026-07-17)** — the AI extraction schema (`ai_extraction.py`) previously treated `principal` as a
  bare string with no guidance, so Claude just grabbed whatever read like a company name and ignored VAT
  numbers, street, postal code, and country even when the source document stated them under cues like
  "Invoice to:" / "Bill to:". Confirmed against a real call (NORD AGANO, principal only ever captured
  "Dampskibsselskabet NORDEN A/S", nothing else). Added an explicit field description instructing Claude to
  capture the full billing block (company, VAT/reg. no., street, postal code + city, country), one per line
  separated by `\n`, only falling back to a bare company name if no further address is stated. The New Call
  form's Principal field is now a `<textarea>` (was a single-line `<input>`) so the block is visible/editable
  pre-save; `app.py::create_call()` normalizes CRLF to `\n` before storing (no DB migration needed — `principal`
  was already an unrestricted TEXT column). Both exports render it properly: Excel's "To:" cell gets
  `wrap_text=True` plus a row height sized to the number of lines; the PDF's `Paragraph` needed a new
  `_pdf_text()` helper (XML-escapes the address, then turns `\n` into `<br/>`, since raw newlines are just
  collapsed whitespace to reportlab's mini-markup parser, not real line breaks) — also closes a latent
  XML-escaping gap for any principal name containing `&`/`<`/`>`. **A multi-line address costs real vertical
  budget**, so re-tightened the print-readiness fix above to keep 1-page-per-PDA working for the common case
  of a genuinely multi-line address (fixed the `small` paragraph style's inherited ~12pt leading down to 9.5pt
  for its 8pt font, trimmed a few more table paddings/margins) — verified both a 5-line address call and the
  original single-line regression call (call_id 19) still export as exactly 2 pages (1 per PDA).
- **Bank remittance block is now a placeholder, not real banking details** (`pda_export.py::BANK_REMITTANCE`).
  It previously hardcoded the company's actual Barclays account number, sort code, and IBAN into every
  generated PDA — fine while this was a the company-only tool, wrong now that the direction is a general PDA
  engine any Ghana port agent could use. Now reads simply "Bank / Remittance details to be provided by the
  Agent." Per-operator configurable banking is real future work (tracked alongside company
  name/letterhead/address as part of making the platform multi-operator), not built yet — this is
  deliberately just the interim fix: stop shipping one company's real account details as the default.
- **PDA 1 Excel/PDF output matches the reference `TAK26063 KASSIOPI.GR - Digitalised.xlsx` layout
  exactly** (as of 2026-07-12): letterhead + address, To/Att/Date/Our Ref/Your Ref block, 7-row Vessel
  Particulars (including Provisional and Actual Cargo Qty/Port Stay rows), a separate **Ship Related
  Expenses** table and **Others General** table each with their own subtotal, Grand Total Payable, a
  remittance block (see banking note below), the GPHA/GSA/GMA prefunding note, and a Berthed/Sailed date line.
  Every charge line's Code column shows the real GPHA tariff code (via the `tariff_ref_code` linking
  column) rather than an internal disambiguator — e.g. both Tug In and Tug Out show `2A3004`, matching
  the tariff (and the reference file), not `2A3004B`. One deliberate correction versus the reference:
  Harbour Rent's code is picked per the vessel's actual LOA band (`2A1002` for 150-200m) instead of the
  reference's hardcoded `2A1003`, which is actually the 200-250m band code — see the Harbour Rent note
  above. **PDA 2 (Receiver) now uses the same two-section layout** (Cargo Related Expenses + Others
  General), addressed to the receiver/consignee with ref `<OurRef>A`, matching the `TAK26063A` reference.
- **Bagged Ammonium Nitrate module added (2026-07-18)** — the largest single feature so far, built entirely
  from 5 real the company PDAs (3 Principal: Free Out >10K GT, Free Out <10K GT, Liner Out <10K GT; 2 Receiver:
  Free Out via MAXAM Ghana, Liner Out via MAXAM Ghana). Surfaced and fixed a platform-wide bug along the way,
  plus several new mechanisms:
  - **Platform-wide fix, not cargo-specific**: Pilotage/Tug Assistance/Mooring/Shifting (`2A2xxx`-`2A5xxx`)
    were flat rates matching only the 30,000-40,000 GT band — every reference vessel used before this had
    happened to be in that exact band. GPHA's real Second Schedule GT-bands them 11 ways; now modeled with
    the same `grt_min`/`grt_max` mechanism built for the Environmental Charge, reused as-is.
  - **Extra 50% tug charge for any vessel GT < 10,000**, any cargo (GPHA General Terms B(6): one tug
    compulsory up to 10,000 GT, two above; an extra tug is 50% of the applicable Towage charge).
  - **`cargo_qty_cbm`** — GPHA bills bagged Ammonium Nitrate's Port Dues on Cargo, Stevedoring, and
    Stevedoring Labour O'time per CBM, not per tonne (a genuine post-tariff GPHA policy change, confirmed
    by the user) — the platform's other cargoes are all tonne-driven, so this is a new call-level field.
  - **`per_unit_with_minimum` basis** — Craneage (GPHA 3H6001 + General Terms D(2)-D(4)): greater of a flat
    $5,200 MHC minimum or $3.34/tonne, but only when a crane is actually deployed. Drives off a new
    `vessel_geared` field (geared/gearless) via a synthetic `cargo_qty_mt_gearless_only` driver — geared
    vessels use their own gear, so the charge doesn't apply at all, not even the minimum.
  - **`liner_routing` + `_select_liner_routed_rows()`** — a third selector (alongside `cargo_match` and
    `grt_min`/`grt_max`) that moves Port Dues on Cargo/Stevedoring/Estimated Labour Delays/Stevedoring
    Labour O'time/Cranage between the Principal and Receiver PDA depending on the call's liner-terms tier:
    Free Out keeps them on the Receiver; Liner Out/LILO moves the stevedoring-family charges (not Port
    Dues) to the Principal; the new **Full Liner Terms** option (added to the liner terms dropdown) also
    moves Port Dues. GSA Levy and Admin/Release Fee always stay on the Receiver regardless of tier — they're
    purely local charges, per the user. `rules_engine.decide_billing_structure()` is now cargo-aware
    (`_ALWAYS_DUAL_PDA_CARGO`): Ammonium Nitrate always gets a Receiver PDA, however small, even under
    Liner Out/Full Liner Terms, since GSA+Admin never disappear — other cargoes' existing PDA1_ONLY
    behavior under Liner Out is completely unchanged.
  - **BL-scoped Receiver PDAs** — Ammonium Nitrate's Receiver PDA is prepared per Bill of Lading, not per
    call (a single vessel call can have several BLs to different receivers/portions). New `bill_of_lading`
    table; a call with zero BL rows behaves exactly as every other cargo always has (one Receiver PDA off
    the call's own fields). `build_pda_excel`/`build_pda_pdf` gained an optional `bl_docs` param that
    renders one sheet/page-set per BL instead, each with its own BL # in the particulars grid and ref.
    TALLY is a free-entry per-BL lumpsum (not a rate_table row) — real practice apportions one call-wide
    Tally figure across BLs, which the platform doesn't automate yet (deliberately deferred, per the user).
  - **Two real double-counting bugs caught during verification, not after**: (1) `_select_grt_band_rows()`
    and `_select_liner_routed_rows()` both had the same latent gap as the earlier `_select_cargo_rows()`
    fix — a charge_code with exactly ONE row that had a restrictive tag (grt band / liner tier) was passed
    through unconditionally instead of being checked against the call, so the new extra-tug surcharge
    briefly fired for a 32,315 GT vessel in testing. Fixed with the same "drop if the lone row's tag doesn't
    match" pattern already used for `cargo_match`. (2) The existing bulk-cargo generic-fallback rows (Port
    Dues, Stevedoring, Labour O'time, Port Cleaning, Draft Survey — none of them cargo-scoped) were firing
    *alongside* the new dedicated `*-BAGGED` charges, since they're different charge_codes with no
    cargo_match at all. Fixed with explicit `cargo_match="Bagged Ammonium Nitrate"` × $0 "not applicable"
    override rows (same pattern as the earlier Bauxite/Manganese/Cocoa placeholders) — then, since a client
    document showing a dozen visible "$0.00 Not applicable" lines is not something the real reference PDAs
    ever have, `price_call()` now skips appending a line entirely when a row's `source` starts with "Not
    applicable" (still records it as 0 in `computed` so any dependent tax line resolves correctly).
  - **Verified against all 5 real documents, exactly**: Free Out >10K Principal $20,333.32 (after the
    confirmed new-tax/agency-fee deltas), Liner Out Principal Ship Related $18,294.97 + folded Cargo Related
    $123,036.48, Free Out Receiver (BALTIC ERICA) Cargo Related $7,244.72, Liner Out Receiver (MV TANJA)
    Port Dues $1,493.86 — plus the full existing clinker regression (NALUHU PDA1 $41,205.10) unchanged.

- **Second-stage document upload: cargo manifest / Bill of Lading extraction (2026-07-18)** — the appointment
  email rarely states the real receiver, BL number, or exact cargo weight/piece count, which Ammonium
  Nitrate's BL-scoped Receiver PDAs need. New upload box on the Review page (`/calls/<id>/bl/extract`) reads
  a manifest/BL document with a dedicated, narrower AI extraction schema (`ai_extraction.extract_bl_manifest_ai`)
  — BL number, receiver + address, receiver attn, net weight (auto-converts kg → MT), and piece count — then
  computes a default CBM (`compute_bl_cbm`: weight-per-bag decides a default GPHA multiplier, 1.3 near
  1.25mt/1250kg bags else 1.0 near 1mt/1000kg bags, `cbm = pieces × multiplier`) and pre-fills the "Add a
  Bill of Lading" form below it — badged the same way the appointment upload badges New Call fields, nothing
  saved until the operator reviews and clicks Add. `_run_extraction()` was generalized to accept a
  schema/prompt/numeric-fields set (previously hardcoded to the vessel-particulars one) so this reuses the
  same Claude API plumbing. `bill_of_lading` gained `bags`/`cbm_multiplier` columns — both editable, with a
  live JS recompute of CBM (bags × multiplier) mirroring the existing auto-port-stay pattern, still directly
  overridable. Verified end-to-end with a synthetic manifest matching the real MV TANJA BL: correctly
  extracted BL number `YAG360M020002`, receiver, attn, converted 216,216 KG → 216.216 MT, 173 bags, defaulted
  multiplier 1.3 (weight-per-bag 1.2498 ≈ 1.25) flagged low-confidence since it's a default not an extraction,
  computed CBM 224.9 — all correctly pre-filled and saved through the real `/bl/extract` → `/bl/add` round trip.
- **Fixed: extracted appointment data disappeared on browser back-navigation (2026-07-18)** — `new_call()`
  was popping the one-shot prefill token out of `_PENDING_EXTRACTIONS` on its first read, so revisiting the
  same pre-filled New Call URL (e.g. after creating the call, then hitting Back) showed a blank form. Changed
  `.pop()` to `.get()` — the token now persists for the life of the server process instead of being consumed
  once. Same pattern reused for the new BL prefill token above.

- **Rate Library: per-cargo filter (2026-07-18)** — the table had grown to 130 rows across 10 cargo types
  and wasn't answering "what does a Bulk Clinker call actually incur" at a glance. New "Show charges for
  cargo" dropdown on `/rates` reuses `rate_engine._select_cargo_rows()` directly (the exact function the
  pricing engine itself uses) so the filtered view can never drift from what a real call actually prices.
  Deliberately does NOT collapse GT-band or liner-terms-routing variants — those depend on the vessel/terms,
  not the cargo, so every GT band and every Principal/Receiver variant of a routed charge stays visible and
  editable; only the cargo dimension narrows (94 rows for Bulk Clinker, 97 for Bagged Ammonium Nitrate, vs.
  130 unfiltered). Also hides each cargo's own "Not applicable" $0 override rows (real for pricing, pure
  noise on a "what applies" list). Edit-and-Save preserves the active filter via a hidden field instead of
  bouncing back to the unfiltered view.

- **Review page decluttered + document upload moved to the top (2026-07-18)** — with multiple BLs and the
  new charge families, the page had gotten long. `line_table()` now wraps each expense table in a
  collapsible `<details>` (subtotal shown in the one-line summary, line items tucked away, collapsed by
  default), and each Bill of Lading is its own collapsible card the same way — the Grand Total and BL
  totals stay visible either way, only the line-item detail is hidden until clicked. The "Upload
  Documents" box (relabeled to cover Cargo Manifest / Bill of Lading / Packing List, not just "manifest/BL")
  and the "Add a Bill of Lading" form both moved from the bottom of the page to right after the Billing
  Decision, before Drivers/calculations — since the whole point is filling in receiver/BL/weight data
  *before* the numbers below are computed, not after.

- **Multi-BL manifest extraction + Tally apportionment (2026-07-18)** — a real cargo manifest (BALTIC ERICA)
  carries several Bills of Lading, one per "MR number", each its own receiver/weight/piece line. The
  manifest extractor now returns a **list** of bills (`BL_MANIFEST_SCHEMA` with a `bills` array;
  `extract_bl_manifest_ai` → `[derive_bl_fields(b), ...]`) instead of one. Upload → the Review page shows an
  **editable preview table** of every extracted BL → "Create all ticked" inserts them in one go (per-row
  duplicate-number guard, per-row skip checkbox), rather than silently auto-inserting. Charges are on **gross**
  weight, so `cargo_qty_mt` = gross; net weight is only a fallback to derive weight-per-bag → the default CBM
  multiplier (the manifest usually states the bag size outright, e.g. "BIG BAGS OF 1250 KG" → ×1.3). New
  **call-level Tally apportionment**: enter one lumpsum (e.g. $850), and `distribute_tally` splits it across
  the call's BLs by gross-MT share (largest-remainder rounding so the cents sum back to exactly the total)
  and writes each slice into that BL's existing `tally_amount` — so the pricing engine and exports don't
  change, they just read the per-BL value as before. `calls.tally_total` remembers the entered lumpsum.
  Verified end-to-end against the real BALTIC ERICA.CM.pdf: 4 MR numbers extracted (GH005/BF003/BF004/GH006,
  including reading the OCR-garbled "GH00S" correctly), correct gross weights and 1.3/1.0 multipliers by bag
  size, $850 split to $109.65/$219.31/$274.23/$246.81 (= exactly $850.00), 4 Receiver PDAs exported (Excel
  sheets PDA2-BL1..4; PDF one page each) plus the Principal PDA.

- **New Call / Review UX pass from operator testing (2026-07-18)** — a batch of workflow refinements while
  test-driving the Ammonium Nitrate flow: cargo type is now required (native prompt + a "wasn't detected"
  note when the upload didn't fill it); Provisional Port Stay auto-fills for Bagged Ammonium Nitrate at
  MT ÷ 1200; the call-level "Cargo Quantity (CBM)" field is removed from New Call (CBM is per-BL from the
  manifest); "Vessel Geared / Gearless" became "Is the vessel geared?" Yes/No, with a hover tooltip (GPHA
  D(3) text) and note shown only on "No"; Parties & References → a collapsible "References" section; "Billing
  Logic Input" → "Select Loading / Discharging Liner Terms"; "Operational Drivers" → "Review and confirm
  Vessel's Marine Operations" with Shifting/Anchorage/3rd-Party removed (they persist their stored values —
  reprice no longer touches them — pending direct editing on the generated PDA); the Create button →
  "Create Pro Forma Disbursement"; "Upload Documents" → "Upload Cargo Documents"; the Review Drivers form is
  now collapsible; and the manual appointment box is no longer auto-filled from an uploaded document.
  Rate/engine: unit rates now display at full precision (Light Dues shows $0.095, not a 2-dp-rounded $0.10)
  via `fmt_rate`/`RATE_MONEY`; Agency Fee defaults to $2,800 for Bagged Ammonium Nitrate (cargo_match variant,
  $3,600 stays for everything else); and gearless Craneage presents as a clean flat "Min Crane Hire" $5,200
  line when the minimum binds (still "greater of $5,200 or $3.34/t" under the hood). Clinker regression
  unchanged ($41,205.10).

## Structure

```
app.py                  Flask routes / UI
pda_engine/
  db.py                 SQLite schema + init (calls, rate_table, tariff_reference, pda_lines, documents, reviews, outputs)
  extraction.py          Vessel-particulars field extraction (offline heuristic)
  ai_extraction.py       Field extraction via Claude API (pasted text, email body+attachments, PDF/image/docx/xls; needs ANTHROPIC_API_KEY)
  email_intake.py        Parse .eml (stdlib) / .msg (extract-msg) into body text + attachment files
  rules_engine.py        PDA1-only vs PDA1+PDA2 decision
  rate_engine.py          Charge-line pricing (rate x qty per driver) + Harbour Rent LOA-band lookup
  port_stay.py            Provisional Port Stay auto-calc (Takoradi cargo-type discharge rates)
  pda_export.py           Excel (openpyxl) + PDF (reportlab) rendering
data/
  rate_library_takoradi_clinker.json   Seed rate table (curated, pricing-ready subset)
  gpha_tariff_reference.json           Full digitized GPHA tariff (all schedules, browsable/searchable)
  pda_platform.db          SQLite database (created on first run)
templates/                Jinja2 pages: history, new_call, review, rates, tariff
storage/
  documents/              Uploaded files
  outputs/                Generated PDA exports
```

## Known gaps vs. the full PRD scope

- No document classification step (Module B) — files are only used for vessel-particulars extraction.
- No login/role-based access (Entra ID in the PRD) — this is single-user, local only.
- No confidence-threshold auto-routing to a review queue — everything lands on one Review screen.
- Only the Takoradi Dry Bulk Terminal clinker rates from the GPHA tariff are loaded. The tariff covers
  every cargo type, terminal, and Tema as well — extending to another cargo/port means adding more rows
  to `data/rate_library_takoradi_clinker.json` (or a new rate library file) with the matching GPHA codes.
- Test call in the History list (MV KASSIOPI.GR / TAK26063) is a demo entry from building this platform
  — delete it from the History page's underlying `calls` table, or just ignore it, once you start using
  this for real calls.
