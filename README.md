# Smart PDA Generator v2 — Automated PDA Generator

**Developed by Lormy** · Takoradi & Tema · Ghana port agency pro forma / final disbursement accounts.

A single-file, browser-based platform for preparing Pro Forma (and Final) Disbursement
Accounts for vessel calls at Ghana's ports. Upload or paste the appointment letter and cargo
documents, the system reads them, prices every charge against the published tariffs, and
produces issue-ready documents — on screen, in print, as Excel, and as PDF.

Everything runs in one HTML file (`Smart_PDA_GeneratorV2.html`). No server logic, no
database, no accounts: state lives in the browser (`localStorage`) with a full JSON
backup/restore cycle under Settings. Document reading (AI) and the export libraries load
from CDNs and degrade gracefully — without a network the app still prices, edits and prints.

## Run it

```
python serve.py          # serves the app at http://localhost:5500
python serve.py 8080     # …or any other port
```

`serve.py` is a small threaded, fault-tolerant static server with no-cache headers, so a
plain refresh always picks up the latest build. It also accepts a `PUT` of a new regression
baseline from the harness (localhost only, one exact path — see *Verification* below).
Opening `Smart_PDA_GeneratorV2.html` directly in a browser works too.

## The workflow (Job wizard)

1. **Documents** — drop the appointment letter, cargo documents or a packing list into
   their boxes and the system reads them (AI, via an API key in Settings — Anthropic or
   OpenAI — or by pasting text and filling in by hand without one).
2. **Call details** — vessel particulars, port, berth, movements, liner terms, port stay.
3. **Cargo** — cargo lines for bulk and bagged trades; a container intake that reads box
   lists, classifies each movement and bills per box / per TEU.
4. **Packing list** — for breakbulk, project and heavy-lift cargo: every package priced on
   its own lift, the way the terminal does.
5. **Parties** — the agency (letterhead), the principal, and the cargo interest.
6. **Pro forma** — the documents themselves: Principal account plus one document per cargo
   interest (per B/L where the trade splits). Every line carries a ⋯ menu that explains
   its arithmetic, names the authority that publishes it, and opens the tariff page it
   came from. Lines can be switched off, reordered, overridden, or moved between
   documents — every change survives recalculation and printing.

Exports live beside Print on the Pro forma step bar: **Excel** (one styled worksheet per
document, currency figures as real numbers) and **PDF** (one file per document — the way
they get sent — each fitted to exactly one A4 page, however many charges the call carries).
Printing holds the same promise: a two-stage fit scales the type and then the sheet so a
long account closes on one page, and the Print button's tooltip always states the scale.

## Home

Ten trade tiles start a job with the right profile: build from scratch, dry bulk, bagged /
breakbulk & project, liquid bulk, containers, oil & gas / offshore, cruise & passenger,
non-cargo operations, RoRo, and a blank sheet. Below them, the recent-work list re-opens
saved records.

## The other tabs

- **Library** — every saved PDA: search, re-open, delete.
- **Verify** — the learning loop. *The tariff gives the rate; only a PDA somebody issued
  shows which lines get billed, on what basis, and to whom.* Drop an issued PDA beside the
  matching open call and every difference is listed — missed charges, extra charges,
  disagreeing amounts, and lines whose own rate × qty ≠ amount. Saving the comparison
  stores it as a **fixture** (issued PDA + the call inputs that priced it) and re-checks it
  after every future change.
- **Statistics** — the nomination database: every saved enquiry and appointment with
  filters, totals and CSV export.
- **Tariff reference** — GPHA Port Tariff (Aug 2023), GMA Safety Levy, Ghana Shippers'
  Authority, GRA taxes and agency estimates, each browsable as rate tables, a charge
  registry, General Terms & Conditions, and the 88-page source scan itself
  (`GPHA_PORT_TARIFF_AUG_2023.pdf`).
- **Settings** — AI document reading (API key, provider, session-only or remembered),
  agency details, bank accounts, a principals directory, cargo interests, custom
  commodities, and the full backup / restore / erase controls.

## Pricing principles

- **No rate is ever invented.** Every figure is wired to the digitized tariff
  (`data/gpha_tariff.json` feeds the engine; `data/gpha_tariff_reference.json` is the full
  reference catalog) and each line can name its source page.
- Manual overrides are first-class: any rate, quantity, amount or payer can be overridden
  per job, and the override survives recalculation until deliberately cleared.
- A house style governs the copy (the system speaks, never "we"), and every exported or
  printed document states exactly what the operator arranged — the sorted screen is a view,
  never the print.

## Verification

`data/regression_baseline.json` is the golden snapshot of the trusted engine — 95 cases
across dry bulk (import/export, all liner-terms families), liquid bulk, bagged cargo,
project cargo packing lists, containers (including private-terminal rules and mixed
movements), non-cargo calls and passenger calls, plus operator-edit regressions.
`regression_matrix_v2.html` re-runs the matrix in a browser and can re-lock the baseline
through `serve.py`'s guarded PUT endpoint. Any future change must reproduce every line
exactly.

**Beta.** Automated calculations are designed to assist and not replace professional
review — every charge should be reviewed before issuing.

## Files

```
Smart_PDA_GeneratorV2.html   the entire application
serve.py                     threaded no-cache static server + baseline PUT endpoint
regression_matrix_v2.html    regression harness (browser)
data/
  gpha_tariff.json           digitized tariff the ENGINE prices from
  gpha_tariff_reference.json full reference catalog for the Tariff tab
  agency_charges_reference.json  agency-set charges (not published by the port)
  regression_baseline.json   the golden 95-case baseline
GPHA_PORT_TARIFF_AUG_2023.pdf    the published source scan (embedded in the Tariff tab)
GPHA Rate Schema/            schema for the digitized tariff
```

## Known gaps

- **RoRo is not priced yet** — the tile exists, the rates don't.
- Excel/PDF export libraries and AI document reading load from CDNs at run time; fully
  offline use keeps every core function except those three.
