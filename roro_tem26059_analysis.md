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
