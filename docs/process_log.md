# Hospital Price Comparison: St. Luke's vs. LVHN

**Goal:** Compare prices at St. Luke's Bethlehem and Lehigh Valley Hospital Cedar Crest, using their federally required price transparency files, and produce summary answers for management.

**Tools:** Python, DuckDB, SQL

---

### Step 1: Data sourcing
- Got both hospitals' price files from Trilliant Oria, already converted to DuckDB databases.
- St. Luke's file is dated Feb 2026 and LVH's is dated Jul 2026.

### Step 2: Data exploration
- Profiled both files:
  - St. Luke's: 75K items and 1.3M insurer prices across 27 plans.
  - LVH: 31K items and 1.7M insurer prices across 57 plans.
- Key data issues found:
  - The two hospitals format billing codes differently.
  - LVH adds modifiers to codes and wraps text in stray quote marks.
  - Carrier names don't match between the files.
  - **LVH's cash prices aren't linked to billing codes.** This needs a workaround before cash can be compared.

### Step 3: Code matching and care-type lookup
- Standardized billing codes across both files: combined CPT/HCPCS fields, stripped LVH's modifiers to a 5-character base code and zero-padded DRGs.
- **4,350 codes are priced at both hospitals:** 3,580 outpatient CPT/HCPCS codes and 770 inpatient DRGs.
- Built a care-type lookup that groups codes into 20 types of care by CPT range, HCPCS prefix, DRG range and revenue code. Every shared code maps to a type.
- Revenue codes agreed with CPT grouping only 58% of the time, because they describe the department (e.g. "operating room") rather than the specialty. Used them as a fallback only.

- **Lookup approved** on 2026-11-23.

### Step 4: Data cleaning
- Excluded drugs and supplies, where one code can cover hundreds of different items.
- Compared like with like: outpatient rates for procedures, inpatient rates for DRGs, and facility fees only.
- Reduced each plan to one median price per procedure, and removed placeholder prices and plan rates more than 10× away from the hospital's median.
- Dropped 109 codes where the hospitals differed by more than 10×. These were mostly add-on codes that one hospital prices as a full procedure.
- **Result: 4,003 procedures compared** (3,233 outpatient + 770 inpatient), from 301K price rows down to 189K clean plan-level prices.

### Step 5: About the data (Q1–Q4)
- Built a carrier crosswalk to match payer names across files (e.g. "IBC" = Independence Blue Cross; Gateway is now Highmark Wholecare). Plan types were derived from plan names.
- **Carriers:** 13 at both hospitals, 13 at LVHN only, 2 at St. Luke's only (Horizon BCBS NJ, Oscar). LVHN lists 57 plans and St. Luke's 27.
- **Prices published:** St. Luke's lists more items (75K vs 31K) and attaches cash prices to 3,804 billing codes. LVHN lists more billing codes (13,456 vs 6,077) but attaches no cash price to any of them.
- **Comparability:** 4,350 codes priced at both → 4,003 fairly compared after cleaning.
- **File dates:** St. Luke's Feb 26, 2026 and LVHN Jul 1, 2026.

### Step 6: Best plan at each hospital (Q5)
- Ranked every plan type (commercial, Medicare Advantage, Medicaid, CHIP) that prices at least half of the 4,003 compared procedures: 22 plans at St. Luke's and 40 at LVHN.
- Built a **price index** so cheap and expensive procedures count equally: each plan's price divided by the hospital's median across plans for that procedure (100 = typical).
- **The best plan at St. Luke's is Highmark Wholecare (Medicaid). The best plan at LVHN is UnitedHealthcare Managed Medicaid.** Both price about 25% below their hospital's typical rate.
- Medicare Advantage plans come next at both hospitals. Commercial plans pay 1.3–5× the typical rate.

### Step 7: Recovering LVHN cash prices
- LVHN publishes cash prices only on internal chargemaster rows that have no billing code. I parsed the CPT code from the descriptions (e.g. "HB 23570 CLOSED TX…").
- That recovered LVHN cash prices for **558 compared procedures**. St. Luke's has 2,115, and **404** have cash at both hospitals.
- I tested capping cash against plan prices and rejected it: St. Luke's cash is normally 1–46× its plan rates, so a cap would delete real prices. Instead I dropped 9 codes where the two hospitals' cash prices differ by more than 10×.
- The cheapest plans pay about 10% of cash at St. Luke's and about 30% at LVHN.

### Step 8: Best plan vs. best plan (Q6)
- Compared Highmark Wholecare Medicaid (St. Luke's) with UnitedHealthcare Medicaid (LVHN) on the **1,422 procedures both plans price**. All are outpatient: Medicaid pays hospital stays by APR-DRG, so the plans share almost no inpatient DRG prices.
- **The result is split.** St. Luke's is cheaper on **763** procedures and LVHN on **390** (269 ties). But LVHN is **8% lower in total** ($648K vs $704K).
- The typical procedure costs about the same at both: LVHN is +2.5%, about $1 more, because both plans follow similar Medicaid fee schedules.
- LVHN's total-dollar lead comes from cardiac catheterization, which its plan pays at a flat $954 vs $6K–$16K at St. Luke's. St. Luke's is much cheaper for surgery: orthopedics, GI and general surgery.

### Step 9: Best plans and cash, four ways (Q7)
- Compared four prices per procedure (each hospital's best plan and each hospital's cash price) on the **234 procedures that have all four**. LVHN's limited cash coverage sets the size of this basket.
- **St. Luke's best plan is the least expensive option:** lowest on 185 of 234 procedures and about **37% lower in total** than the next option, LVHN's best plan ($107K vs $171K).
- Cash is far more expensive at both hospitals: LVHN cash totals $664K and St. Luke's cash $742K, 4–7× the plan totals.
- On this smaller basket the Q6 result flips: LVHN's flat-rate heart caths have no LVHN cash price, so they drop out. This shows how sensitive the result is to which procedures are compared.

### Step 10: Cash vs. best plan (Q8–Q9)
- **St. Luke's:** the negotiated rate beats cash on **all 1,953** procedures compared and is **85% lower in total**. Its best plan pays 17% of the list price and cash is 83% of the list price, so cash is consistently about 4.9× the plan rate.
- **LVHN:** the negotiated rate beats cash on **393 of 450** procedures and is **78% lower in total**. Cash wins on 57, mostly minor surgery and maternity.
- Maternity at LVHN is the only care type where cash comes out cheaper overall (13% lower, 4 procedures).

### Step 11: Detail tables (Q10–Q12)
- **Top 10 procedures:** the files have no volume data, so "top" means common, shoppable services: a CMS shoppable-services selection for outpatient and common admissions for inpatient.
  - **Outpatient:** St. Luke's best plan is lowest on all 10.
  - **Inpatient:** LVHN is lowest on 9 of 10, about 5–13% below St. Luke's. Medicaid plans don't price inpatient stays, so I used each hospital's best plan that does (Medicare Advantage).
- **By carrier:** compared each carrier like for like by plan type. St. Luke's is cheaper for **14 of 20** carrier/plan-type pairs, often by 25–68%. LVHN wins mainly in Medicare Advantage, by only 2–5%.
- **Facility fees:** best-plan clinic visits cost about the same at both hospitals ($24–$96). St. Luke's best plan pays a flat $300 for ER levels 3–5, versus $70–$171 at LVHN. Cash for an ER visit is roughly double at St. Luke's ($878–$4,401 vs $550–$2,015).

### Step 12: Management report
- Compiled all 12 answers into a shareable report: [Hospital Price Comparison: St. Luke's vs. LVHN](https://claude.ai/artifact/5gMomEK6csXvz7zVFqzvAs).
- Each section leads with the bottom line, then gives the supporting counts, dollar and percent differences, and a breakdown by type of care.
- A final review caught three fixes: an empty cell turned out to be a real finding (LVHN's Valley Preferred plan pays 207% of LVHN's cash price), two rounding slips, and two empty cash columns that were removed.

### Step 13: Publishing to GitHub
- Published the project as a public repository: [oak200/hospital-price-comparison](https://github.com/oak200/hospital-price-comparison).
- Added a README, a download script for the data, and `run_all.py`, which runs the whole pipeline in order. A fresh run from an empty database reproduced every result.
- Kept the large hospital files (190 MB) out of the repo. Anyone can re-download them with `scripts/download_data.py`.
