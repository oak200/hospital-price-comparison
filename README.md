# Hospital Price Comparison: St. Luke's vs. LVHN

A comparison of negotiated insurance rates and cash prices at two Lehigh Valley hospitals, **St. Luke's Hospital – Bethlehem** and **Lehigh Valley Hospital – Cedar Crest** (LVHN, now part of Jefferson). It uses the price files hospitals must publish under the CMS Hospital Price Transparency rule.

**Tools:** Python · DuckDB · SQL

## Key findings

- **4,003 procedures** could be fairly compared, out of 4,350 billing codes both hospitals list with a price.
- **Best plan:** Highmark Wholecare (Medicaid) at St. Luke's and UnitedHealthcare Managed Medicaid at LVHN. Both price about 25% below their hospital's typical rate.
- **Hospital vs. hospital:** St. Luke's is cheaper on most procedures, especially surgery, where it is often 50–100%+ cheaper. LVHN is cheaper for heart procedures, ER visits and common inpatient stays.
- **Cash vs. insurance:** the best plan beats cash at both hospitals: 85% lower at St. Luke's (1,953 of 1,953 procedures) and 78% lower at LVHN (393 of 450).
- **By carrier:** St. Luke's is cheaper for 14 of 20 carrier and plan-type pairs. LVHN wins mainly in Medicare Advantage, by 2–5%.

The full write-up with all 12 questions is in the management report. The step-by-step process is in [docs/process_log.md](docs/process_log.md).

## Data challenges solved

- **Different file layouts:** the two hospitals code procedures differently. LVHN attaches modifiers to codes (e.g. `9928327` = ER level 3 + modifier 27), so codes were matched on the 5-character base code.
- **LVHN cash prices aren't linked to billing codes:** I recovered them by reading the CPT code inside chargemaster descriptions (e.g. "HB 23570 CLOSED TX…"), which covers 558 compared procedures.
- **No "type of care" field:** I built a lookup grouping codes by CPT range, HCPCS prefix, DRG range and revenue code ([lookup/care_type_lookup.csv](lookup/care_type_lookup.csv)).
- **Different payer names:** a carrier crosswalk matches names across the files, e.g. "IBC" = Independence Blue Cross ([lookup/carrier_crosswalk.csv](lookup/carrier_crosswalk.csv)).
- **Outliers and non-comparable codes:** the cleaning rules are logged step by step. They remove 109 add-on codes that one hospital prices as a full procedure.

## Project structure

```
scripts/   analysis pipeline (run_all.py runs everything in order)
lookup/    care-type lookup and carrier name crosswalk
output/    result tables for each question (CSV)
docs/      process log
data/      hospital price files (not in the repo; see below)
work/      working database built by the scripts (not in the repo)
```

## How to run

```
pip install -r requirements.txt
python scripts/download_data.py   # about 190 MB, from Trilliant Oria
python scripts/run_all.py
```

Results are written to `output/`.

## Data sources

- [St. Luke's Bethlehem price file](https://oria-data.trillianthealth.com/hospital/st_lukes_hospital_bethlehem_campus-c43ea) (file date Feb 26, 2026)
- [LVH Cedar Crest price file](https://oria-data.trillianthealth.com/hospital/lehigh_valley_hospital_cedar_crest-9591f) (file date Jul 1, 2026)
- [Trilliant Oria data guide](https://oria-data.trillianthealth.com/docs)

Prices are published standard charges, not what a patient owes after deductibles or coinsurance.
