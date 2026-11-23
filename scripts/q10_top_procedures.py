"""Step 11a: top 10 inpatient and top 10 outpatient procedures (Q10).

The files carry no volume data, so "top" means common, shoppable services:
  Outpatient: a selection from CMS's shoppable-services list (imaging, lab,
    endoscopy, common surgery).
  Inpatient: common hospital admissions (deliveries, joint replacement,
    sepsis, heart failure, pneumonia, ...).
All 20 are among the 4,003 compared procedures.

Prices shown: the best plan and the cash price at each hospital; "lowest" names
the cheapest of the four.
  Outpatient best plan = rank 1 in Q5 (the Medicaid plans).
  Inpatient best plan = the highest-ranked Q5 plan that prices at least half of
    the compared DRGs, because the Medicaid plans don't price MS-DRG stays.
  Cash: neither hospital publishes cash prices for inpatient DRGs; LVHN cash is
    parsed from chargemaster descriptions and is missing for many codes.

Outputs: tables q10_outpatient, q10_inpatient; matching CSVs in output/
"""
import duckdb

con = duckdb.connect("work/analysis.duckdb")
show = lambda sql: print(con.execute(sql).fetchdf().to_string(index=False), "\n")

OUTPATIENT = {
    "70450": "CT scan, head (no contrast)",
    "74177": "CT scan, abdomen & pelvis (contrast)",
    "72148": "MRI, lower back (no contrast)",
    "77067": "Screening mammogram",
    "76700": "Ultrasound, abdomen",
    "80053": "Comprehensive metabolic panel",
    "85025": "Complete blood count (CBC)",
    "45378": "Colonoscopy, diagnostic",
    "66984": "Cataract removal with lens",
    "29881": "Knee arthroscopy (meniscectomy)",
}
INPATIENT = {
    "807": "Vaginal delivery",
    "788": "C-section",
    "795": "Normal newborn",
    "470": "Hip or knee replacement",
    "871": "Sepsis (with major complications)",
    "291": "Heart failure (with major complications)",
    "194": "Pneumonia",
    "690": "Kidney / urinary tract infection",
    "392": "Digestive disorders",
    "603": "Cellulitis (skin infection)",
}

n_drgs = con.execute("SELECT count(*) FROM compared_codes WHERE code_type = 'MS-DRG'").fetchone()[0]

def best_plan(hosp, min_drgs=0):
    hosp_name = "St. Luke's" if hosp == "SLB" else "LVHN"
    return con.execute("""
        SELECT p.payer, p.plan, r.carrier || ' ' || r.plan
        FROM q5_plan_ranking r
        JOIN plans p ON p.hosp = ? AND p.carrier = r.carrier AND p.plan = r.plan
        WHERE r.hospital = ?
          AND (SELECT count(*) FROM plan_prices pp WHERE pp.hosp = p.hosp AND pp.payer = p.payer
               AND pp.plan = p.plan AND pp.code_type = 'MS-DRG') >= ?
        ORDER BY r.rank LIMIT 1
    """, [hosp, hosp_name, min_drgs]).fetchone()

def build(table, code_type, codes, slb_best, lvh_best):
    code_list = ", ".join(f"('{c}', {i}, '{name}')" for i, (c, name) in enumerate(codes.items()))
    con.execute(f"""
    CREATE OR REPLACE TABLE {table} AS
    WITH c(code, ord, name) AS (VALUES {code_list}),
    t AS (
        SELECT c.ord, c.code, c.name, s.care_type,
            (SELECT round(price) FROM plan_prices WHERE hosp = 'SLB' AND code_type = '{code_type}' AND code = c.code
                AND payer = '{slb_best[0]}' AND plan = '{slb_best[1]}') AS slb_best_plan,
            (SELECT round(price) FROM plan_prices WHERE hosp = 'LVH' AND code_type = '{code_type}' AND code = c.code
                AND payer = '{lvh_best[0]}' AND plan = '{lvh_best[1]}') AS lvh_best_plan,
            (SELECT round(cash) FROM cash_prices WHERE hosp = 'SLB' AND code_type = '{code_type}' AND code = c.code) AS slb_cash,
            (SELECT round(cash) FROM cash_prices WHERE hosp = 'LVH' AND code_type = '{code_type}' AND code = c.code) AS lvh_cash
        FROM c JOIN shared_codes s ON s.code_type = '{code_type}' AND s.code = c.code
    )
    SELECT code, name AS procedure, care_type,
           slb_best_plan, lvh_best_plan, slb_cash, lvh_cash,
           CASE WHEN (slb_best_plan IS NOT NULL)::INT + (lvh_best_plan IS NOT NULL)::INT
                     + (slb_cash IS NOT NULL)::INT + (lvh_cash IS NOT NULL)::INT < 2 THEN 'Only one price published'
                ELSE CASE least(coalesce(slb_best_plan, 1e12), coalesce(lvh_best_plan, 1e12), coalesce(slb_cash, 1e12), coalesce(lvh_cash, 1e12))
                WHEN slb_best_plan THEN 'St. Luke''s best plan'
                WHEN lvh_best_plan THEN 'LVHN best plan'
                WHEN slb_cash THEN 'St. Luke''s cash'
                WHEN lvh_cash THEN 'LVHN cash' END END AS lowest
    FROM t ORDER BY ord
    """)
    con.execute(f"COPY {table} TO 'output/{table}.csv' (HEADER)")

out_slb, out_lvh = best_plan("SLB"), best_plan("LVH")
in_slb, in_lvh = best_plan("SLB", n_drgs // 2), best_plan("LVH", n_drgs // 2)
print(f"Outpatient best plans: SLB = {out_slb[2]}, LVHN = {out_lvh[2]}")
print(f"Inpatient best plans:  SLB = {in_slb[2]}, LVHN = {in_lvh[2]}\n")

build("q10_outpatient", "CPT/HCPCS", OUTPATIENT, out_slb, out_lvh)
build("q10_inpatient", "MS-DRG", INPATIENT, in_slb, in_lvh)
print("Top 10 outpatient"); show("SELECT * FROM q10_outpatient")
print("Top 10 inpatient"); show("SELECT * FROM q10_inpatient")
