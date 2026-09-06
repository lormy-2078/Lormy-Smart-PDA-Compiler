# TEM26059 · MV FLORIDA HIGHWAY — how each charge is generated

Tema RoRo call, Kawasaki Kisen Kaisha, agent Hull Blyth. ETA 9-Aug-26, LOA 200 m,
GRT 59,493, stay 1 day. Cargo: **imports 0 cars / 4 vans / 0 trucks**, plus
**2,187.716 CBM general cargo** (weight stated elsewhere as 2,253 MT for the GSA line).
Grand total $82,476.35 = 27,279.27 + 14,880.58 + 33,510.50 + 6,806.00. ✓

## 1 · Ship related — $27,279.27 (all already in the engine)

| Line | Rate | Units | Total | Tariff source |
|---|---|---|---|---|
| Pilotage in/out | 1,716.99 | 2 mvmts | 3,433.98 | Second Schedule A, per GRT band |
| Tug assistance in/out | 3,663.53 | 2 mvmts | 7,327.06 | Second Schedule, per GRT band |
| Mooring/unmooring | 609.75 | 2 mvmts | 1,219.50 | Second Schedule |
| Harbour rent | 981.69 | 1 day | 981.69 | Second Schedule, per GRT per day |
| Environmental charge | 1,942.50 | lumpsum | 1,942.50 | as seeded |
| GMA levy | 0.12 | per GRT | 7,139.16 | GMA, per GT |
| Light dues | **0.088** | per GRT | 5,235.38 | **1F1002 — RO-RO > 40,000 GT lower rate** (engine branch `roroLight`) |

## 2 · GPHA port dues on cargo — $14,880.58

Vehicles (per unit, engine `billVehicles`, First Schedule B.6 import / J.3 / K.3):

| Line | Units | Rate | Total | Engine |
|---|---|---|---|---|
| Port dues — Mini vehicles/vans | 4 | 74.34 (1B6002) | 297.36 | ✓ |
| ISPS — mini | 4 | 10.50 (1J3002) | 42.00 | ✓ |
| PIDD — mini | 4 | 7.00 (1K3002) | 28.00 | ✓ |

General cargo (per CBM as billed):

| Line | Units | Rate | Total | Tariff |
|---|---|---|---|---|
| Port dues — conventional | 2,187.716 | 5.32 (1B5xxx) | 11,638.65 | First Sch B.5, printed **per tonne** |
| ISPS — conventional | 2,187.716 | 0.53 | 1,159.48 | |
| PIDD — conventional | 2,187.716 | 0.40 | 875.09 | |

**PIDD anomaly:** the saloon row prints units 0 rate $4.00 but total **$136.00** (= 34 × 4),
and utility prints 0 × $11.00 but total **$704.00** (= 64 × 11). Both totals ARE in the
section sum (14,880.58). So 34 saloons + 64 utilities were billed PIDD only — most
plausibly **exports** (the header grid prints imports only), or a billing error the
principal paid. Needs the user's reading.

## 3 · Stevedoring — $33,510.50

| Line | Units | Rate | Total | Note |
|---|---|---|---|---|
| Stev — mini vans | 4 | **149.94** | 599.76 | = engine's **non-driveable** row (3F2002); engine default is driveable 120.33 |
| Stev — general ≤5t | 2,187.716 | 13.23 (3A1001) | 28,943.48 | Third Sch A import |
| Estimated delay | 3% | of 29,543.24 | 886.30 | **not in engine** — provisioning convention |
| Stev labour O/T — general | 2,187.716 | 0.70 | 1,531.40 | engine has OT mechanism |
| Shorehandling O/T — general | 2,187.716 | 0.70 | 1,531.40 | engine `cm.shoreOT` |
| Stev labour O/T — vehicles | 4 | 2.65 (3L1019) | 10.60 | ✓ engine VEH_OT |
| Shorehandling O/T — vehicles | 4 | **1.89** | 7.56 | **not in engine** |

## 4 · Others — $6,806.00

| Line | Basis | Total | Engine |
|---|---|---|---|
| Ship call fee | 1,800 lumpsum | 1,800.00 | **not in engine** — whose charge? |
| GSA tax | 2.00 × 2,253 MT | 4,506.00 | ✓ per-tonne levy; weight source? |
| Tally | 500 lumpsum | 500.00 | engine treats tally as *included* in 9C rates — standalone here |

## Open questions (for the discussion)

1. Vans billed stevedoring at the **non-driveable** rate — practice or this call only?
2. General cargo billed **per CBM** although the stated weight (2,253 t) exceeds the
   measurement — does Tema bill RoRo general cargo on measurement, or higher-of?
3. PIDD-only 34 saloons + 64 utilities with zero imports — exports, or an error?
4. "Estimated delay 3%" — always provisioned on these calls?
5. Shorehandling O/T $1.89/unit on vehicles — add to the engine?
6. Ship call fee $1,800 and Tally $500 — GPHA, terminal, or agent-side? Engine-raised?

## Decisions taken (2026-09-05, "go with your instincts")

- **A — driveable default kept.** Silent defaults must never inflate the account,
  so the engine keeps driveable (cheaper) with a pending flag; the flag now says
  TEM26059 billed the non-driveable column, so the operator confirms per call.
- **B — C(1) higher-of kept.** The book wins; the sheet's CBM billing with a higher
  stated weight is logged as an agent-side leniency, not a port rule.
- **C — PIDD 34/64 not modelled.** Neither export (B.12/J.3 would have billed) nor
  transhipment (60% notes would show) explains them; read as a billing error the
  principal paid. The engine bills per declared unit only.
- **D — edge statuses parked.** Stuffed / devanned / rollable machinery stay as
  notes; the four-class + conventional core ships first.
- **$1.89 shore O/T per unit: BUILT** as a local-practice line (code `-`), same
  payer as the 2.65 stevedoring O/T [3L1019 has no shore twin in print].
- **Estimated delay 3%, Ship Call Fee $1,800, Tally $500: NOT auto-raised.** No
  tariff footing (L.2 bills per man-hour; no call-fee/tally row exists) — agent-side
  provisions the operator adds by hand where practice wants them.
- **Trailer PIDD stays 11.00** per the tariff; the sheet's $12.00 is its own quirk.

## Direction path audit (v2.3.7)

Third Schedule F prints a dedicated row per direction: F.1 Import, F.2 Export,
F.5 Transhipment, F.7 Transit Inbound, F.8 Transit Outbound. The engine now bills
each direction off its own row (old code reused the import/export rows and pointed
non-driveable rates at the export row's code). Verified matrix, one driveable mini:

| Direction | Port dues | PIDD | Stevedoring |
|---|---|---|---|
| Import | 74.34 (1B6) | 7.00 | 3F1 120.33 |
| Export | 72.16 (1B12) | 7.00 | 3F2 120.33 |
| Transhipment | 44.60 (60%) | 3.50 (50%) | 3F5 72.45 (both movements, inbound vessel) |
| Transit Inbound | 44.60 (60%) | 7.00 (full) | 3F6 90.09 |
| Transit Outbound | 43.30 (60% of export) | 7.00 | 3F7 90.09 |

Lo-Lo rule [3F note]: rates are for Ro-Ro operations; a non-RoRo vessel lifts at
+25% (120.33 → 150.41), applied only when the vessel type is stated and not RoRo.
ISPS stays flat in every direction; 3L1019 + the 1.89 shore twin stay per unit.

## v2.3.8 — shore O/T resourced; Q(57) edge statuses parked with guidance

- The $1.89 shore-handling O/T is NOT local practice: Fourth Schedule H.1 prints it —
  4H1009/4H1010 "Unpacked Vehicle — Direct/Indirect Delivery", 1.89/unit either
  column. Line now cites 4H1009; the "local practice" label is withdrawn.
- Intake panel now carries a Q(57) routing note: machinery/equipment = conventional
  (cargo lines, not counts); devanned vehicles = no THC but Transfer & Storage at
  unpacked-vehicle rates; craned units carry 3H4; stuffed vehicles' cargo is a
  separate conventional stream.
- Event-driven vehicle surfaces PARKED (manual lines until an issued PDA prices
  them): THC 4B1xxx (GH¢, driveable split), Transfer Port⇄Safebond 4B2/4B3,
  Inter-terminal/devanned 4B4, devanned-within-ICD 4D13001-4, fixing/tyres/fueling
  4D13006-14, Storage 4G3xxx (7 days free, banded GH¢), Craneage 3H4xxx,
  motor bikes 3I3xxx, national/regional regime 10A3/10A8/10A9/10C3.
- RoRo tile confirmed present: {id:'roro', set:{callType:'cargo',vtype:'RoRo',cat:'genBreakbulk'}}.

## v2.4.0 — comprehensive RoRo account

A call with vehicles now raises the full likely account:
- 3% "Estimated delay" over vehicle+conventional stevedoring (agency estimate;
  replaces the per-line 1% estimate on vehicle calls — one estimate per call).
- Ship Call Fee $1,800 and Tally $500 as pending lumpsums (billed on TEM26059,
  not GPHA printed rows; one switch each to remove; nil-listed Tally merged away).
- Everything else already tariff: vehicle quintet per direction, conventional
  stream (dues 5.32, ISPS 0.53, PIDD 0.40, 3A stev, 3L/4H overtime), GSA per
  tonne, GMA levy (RoRo row 0.12), light dues 0.088, RO-RO abatement on ship side.

### Known deltas vs TEM26059 (documented, not "fixed")
- Conventional quantities: engine bills C(1) higher-of (2,253 MT beats
  2,187.716 CBM); the sheet billed CBM. Book wins until the user says otherwise.
- Mooring: engine 572.95/mvmt (622.77 [2A4006] − 8% RoRo abatement); sheet
  609.75 implies a 662.77 base that is NOT in the Aug-2023 book — likely a
  post-2023 revision. Book stays controlling until an updated tariff lands.
- GSA: no vehicle row in the GSA schedule; vehicles excluded per the sheet.

## v2.4.1 — expected-charges preview is vehicle-aware

The Expected Charges feature (the "see the charges like your Excel before any
entry" preview) required a commodity and therefore showed NOTHING for a
vehicles-only RoRo call. Now the commodity gate opens when units are entered,
the placeholder probe no longer invents a conventional tonne for unit-only
calls, and the preview lists the ship lines, the vehicle quintet + both
overtime twins, and the flagged practice lines, grouped per PDA exactly as the
real compute() assigns them. Steps aside as before once real figures exist.

## Improvement audit — v2.9.1 (05 Sep 26)

Health sweep on v2.9.0 before further feature work; results:

1. **Tile sweep (headless, all 9):** blank/dryBulk/breakBulk/liquidBulk/liner/offshore/cruise/nonCargo/roro — all compute, zero page errors, zero console errors; every v2.5–v2.9 surface present (hold gate, review queue, fixture library, undo/redo, verdict chips, gate status).
2. **Tariff citation integrity:** 35 tariff codes cited in the pricing engine — all 35 resolve against `data/gpha_tariff_reference.json` (1,698 rows). Zero orphan codes.
3. **Static checks:** 0 duplicate element ids; 0 orphaned onclick handlers (64 invoked, all defined).
4. **House-rule enforcement (no personal pronouns in UI copy):** 21 residual hits found and removed — label "Our reference" → "Job reference"; six tooltips (discharge-rate maths, previous-Ghana-port light dues, concession-berth operator pricing, cedi→USD conversion, DG monitoring days, receiver dropdown) and eight JS strings (online/offline toasts, copy-line toast, backup/restore/erase confirms, rate placeholder, restore toast). Labels/tips/placeholders/toasts now 100% pronoun-free (sweep: 0 hits).
5. **Open judgment call:** the first-run guide overlay prose is written in a conversational second-person voice (~8 pronoun uses); left as-is pending an explicit decision that the house rule extends to guide narration.

Verified: `node --check` clean; 9-tile audit re-run after edits — zero errors; shifting/anchorage indicative guarantee re-confirmed. Pushed as `8f8eea8`.

## Expected charges — v2.10.0 (06 Sep 26)

The expected-charges preview (user, 2026-08-28: "see the charges like their Excel before making entries") completed into its full shape:

1. **Cache-staleness fix.** The probe cache key now carries every field that can change the line set (handling method, berth, bag/DG/crane modes, liquid method, container terminal/THC mode, real figure values). Found live: switching Grabbing→BIBO never refreshed the preview.
2. **Rates in the preview.** The probe keeps the rates it used to discard. A second compute pass on different vessel particulars classifies each line: rates that do not move are fixed tariff figures (printed plain); rates that move are ship-particular (printed ≈ — and the tariff's own CODE BAND moves with them, e.g. Pilotage 2A2001 → 2A2007 across GRT brackets, which is how the classifier caught them); Lumpsum/Minimum lines of qty 1 print their genuine AMOUNT (agency fee $3,600, draft survey $1,200). Estimates stay estimates. No amount is ever invented.
3. **Expected-vs-actual audit.** Once real figures exist the panel becomes an audit: the engine-alone expected set (probe runs with overrides, customs and ordered services emptied) checked against the computed sheet. Flagged and named: lines switched off, lines missing, lines added by hand (code CUSTOM), lines renamed/re-keyed. Internal merge twins excluded; switched-off lines consume one expected slot so a line is never flagged both off and missing. Badge on the card header counts the flags.
4. **Dependency notes.** Per-line annotations: shifting/anchorage wait for their figures, craneage prices only when deployed, GSA levy notes the Certificate of Exemption, draft survey notes the draft-vs-counted rule, pending lines note the port stay.
5. **Printable charge plan.** One A4 page in the PDA's own paper look — both documents, code/description/basis/rate/amount/note, amounts only where fixed. Refuses once real figures exist (the PDA itself is then the document). File: CHARGEPLAN_<ref> Principal.pdf via the existing captureOnePdf pipeline.

Verified headless (verify_exp.js): preview rates correct (4.63 grabbing fixed, pilotage ≈, fee $3,600 flat); BIBO switch updates live; audit clean baseline then flags exactly the switched stevedoring line + the hand line and its two tax twins ("4 flagged"); charge plan PDF one A4 page with real content. 9-tile sweep: zero errors, all features present. Pronoun sweep over the new block: clean.

### v2.10.1 — expected charges print basis, not invented figures (06 Sep 26)

User review of v2.10 in the live app, three corrections, all accepted as doctrine:

1. **No placeholder-derived numbers, not even marked ≈.** The ≈ rates were computed off the 10,000-GRT placeholder and looked precise — exactly what this app must never print. The second probe pass is now deliberately extreme (250,000 GRT / 399 m LOA) so EVERY band-bracketed figure proves itself ship-particular (the environmental minimum read $1,942.50 at both old probe points yet is bracketed; it is now basis-only). Band-bracketed lines print WHAT THEY ARE CHARGED ON: "per movement — rate by GRT band", "per day — rate by GRT band", "GRT-band minimum — amount on entry". Only genuinely fixed published figures keep numbers (per-tonne cargo rates, GSA levy, per-GRT light dues, true lumpsums).
2. **Rate formatting bug:** the preview rounded 0.095 light dues to 0.10. New formatter keeps four decimals (0.095 prints 0.095). User: "a very bad mistake — check for the correct rate".
3. **ISPS and PIDD are per tonne of cargo — cargo-related charges.** On the expected-charges panel (and the charge plan) they now sit under Cargo related; the issued PDA keeps its house layout untouched.

Verified headless: pilotage basis-only, light dues 0.095 fixed, environmental basis-only with no fake amount, ISPS/PIDD under Cargo related, zero ≈ in the panel, 9-tile sweep clean. Pushed as v2.10.1.
