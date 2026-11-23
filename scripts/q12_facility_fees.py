"""Step 11c: facility fees for clinic and ER visits, levels 1-5 (Q12).

Codes
  Clinic visit levels 1-5: CPT 99211-99215 (established patient office visit).
  ER visit levels 1-5:     CPT 99281-99285.
  LVHN lists these codes with modifiers attached (e.g. 99283-27, 99213-U9HD);
  they were matched on the 5-character base code (Step 3). LVHN publishes no
  99281 (ER level 1). Both hospitals also list G0380-G0384 ("Type B" ER visits),
  which apply to part-time EDs and are shown separately for reference.

Prices: each hospital's best plan (rank 1 in Q5) and cash price. St. Luke's has
separate facility and professional-fee rows; only facility rows are used (Step 4).

Outputs: table q12_facility_fees; output/q12_facility_fees.csv
"""
import duckdb

con = duckdb.connect("work/analysis.duckdb")
show = lambda sql: print(con.execute(sql).fetchdf().to_string(index=False), "\n")

VISITS = [
    ("Clinic visit", 1, "99211"), ("Clinic visit", 2, "99212"), ("Clinic visit", 3, "99213"),
    ("Clinic visit", 4, "99214"), ("Clinic visit", 5, "99215"),
    ("ER visit", 1, "99281"), ("ER visit", 2, "99282"), ("ER visit", 3, "99283"),
    ("ER visit", 4, "99284"), ("ER visit", 5, "99285"),
    ("ER visit (Type B)", 1, "G0380"), ("ER visit (Type B)", 2, "G0381"), ("ER visit (Type B)", 3, "G0382"),
    ("ER visit (Type B)", 4, "G0383"), ("ER visit (Type B)", 5, "G0384"),
]
values = ", ".join(f"('{v}', {lvl}, '{c}', {i})" for i, (v, lvl, c) in enumerate(VISITS))

con.execute(f"""
CREATE OR REPLACE TABLE q12_facility_fees AS
WITH v(visit, level, code, ord) AS (VALUES {values}),
best AS (
    SELECT CASE r.hospital WHEN 'St. Luke''s' THEN 'SLB' ELSE 'LVH' END AS hosp, p.payer, p.plan
    FROM q5_plan_ranking r JOIN plans p
      ON p.hosp = CASE r.hospital WHEN 'St. Luke''s' THEN 'SLB' ELSE 'LVH' END
     AND p.carrier = r.carrier AND p.plan = r.plan
    WHERE r.rank = 1
),
bp AS (
    SELECT pp.hosp, pp.code, pp.price FROM plan_prices pp JOIN best USING (hosp, payer, plan)
    WHERE pp.code_type = 'CPT/HCPCS'
)
SELECT v.visit, v.level, v.code,
       round((SELECT price FROM bp WHERE hosp = 'SLB' AND bp.code = v.code)) AS slb_best_plan,
       round((SELECT cash FROM cash_prices c WHERE hosp = 'SLB' AND c.code = v.code)) AS slb_cash,
       round((SELECT price FROM bp WHERE hosp = 'LVH' AND bp.code = v.code)) AS lvh_best_plan,
       round((SELECT cash FROM cash_prices c WHERE hosp = 'LVH' AND c.code = v.code)) AS lvh_cash
FROM v ORDER BY ord
""")
# ER level 1 (99281) isn't in the compared set because LVHN doesn't list it.
# St. Luke's does, so fill its prices from the source file using the same rules
# (outpatient, facility rows only, median per plan).
con.execute("ATTACH IF NOT EXISTS 'data/stlukes_bethlehem.duckdb' AS slb (READ_ONLY)")
slb_payer, slb_plan = con.execute("""
    SELECT p.payer, p.plan FROM q5_plan_ranking r JOIN plans p
      ON p.hosp = 'SLB' AND p.carrier = r.carrier AND p.plan = r.plan
    WHERE r.hospital = 'St. Luke''s' AND r.rank = 1""").fetchone()
con.execute(f"""
UPDATE q12_facility_fees SET
  slb_best_plan = (SELECT round(median(standard_charge_dollar)) FROM slb.standard_charge_details
                   WHERE coalesce(cpt, hcpcs) = '99281' AND setting = 'outpatient'
                     AND NOT (lpad(rc, 4, '0') BETWEEN '0960' AND '0989')
                     AND payer_name = '{slb_payer}' AND plan_name = '{slb_plan}'),
  slb_cash = (SELECT round(median(discounted_cash)) FROM slb.standard_charges
              WHERE coalesce(cpt, hcpcs) = '99281' AND setting = 'outpatient'
                AND NOT (lpad(rc, 4, '0') BETWEEN '0960' AND '0989'))
WHERE code = '99281'
""")
con.execute("COPY q12_facility_fees TO 'output/q12_facility_fees.csv' (HEADER)")
show("SELECT * FROM q12_facility_fees")
