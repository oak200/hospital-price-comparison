"""Step 4: clean negotiated prices and reduce to one price per plan per procedure.

Approved rules (2026-11-23)
  R1  Scope: codes priced at both hospitals, excluding the Drugs and
      Supplies & devices care types.
  R2  Like-for-like: CPT/HCPCS codes use outpatient rates and DRGs use inpatient
      rates. St. Luke's professional-fee rows (revenue code 096x-098x) are
      dropped, because LVH's file is facility-only.
  R3  Drop prices of $1 or less (placeholders).
  R4  One price per hospital / code / plan = median of that plan's rates.
  R5  Drop a plan price more than 10x above or below the median of all plans
      for that code at the same hospital.
  R6  Drop a code where the two hospitals' median plan prices differ by more
      than 10x (usually a unit mismatch).

Output: work/analysis.duckdb
  plan_prices      hosp, code_type, code, care_type, payer, plan, price, n_rates
  compared_codes   codes that survive all rules, with each hospital's median
  cleaning_funnel  rows/codes remaining after each rule
  excluded_r6      codes removed by R6, for audit
"""
import duckdb

con = duckdb.connect("work/analysis.duckdb")
con.execute("ATTACH IF NOT EXISTS 'data/stlukes_bethlehem.duckdb' AS slb (READ_ONLY)")
con.execute("ATTACH IF NOT EXISTS 'data/lvh_cedar_crest.duckdb' AS lvh (READ_ONLY)")
funnel = []

def log(step, table, where="true"):
    r = con.execute(f"""SELECT count(*), count(DISTINCT code_type || code) FROM {table} WHERE {where}""").fetchone()
    funnel.append((len(funnel) + 1, step, r[0], r[1]))

# All payer rows for shared codes, with normalized code/payer/plan fields
con.execute("""
CREATE OR REPLACE TEMP TABLE raw_rates AS
WITH d AS (
    SELECT 'SLB' AS hosp, coalesce(cpt, hcpcs) AS hcpcs, ms_drg AS drg,
           setting, lpad(rc, 4, '0') AS rc, payer_name AS payer, plan_name AS plan,
           standard_charge_dollar AS price
    FROM slb.standard_charge_details
    UNION ALL
    SELECT 'LVH', left(upper(replace(hcpcs, '"', '')), 5),
           lpad(replace(ms_drg, '"', ''), 3, '0'),
           replace(setting, '"', ''), NULL,
           replace(payer_name, '"', ''), replace(plan_name, '"', ''),
           standard_charge_dollar
    FROM lvh.standard_charge_details
)
SELECT d.hosp, s.code_type, s.code, s.care_type, d.setting, d.rc, d.payer, d.plan, d.price
FROM d JOIN shared_codes s
  ON (s.code_type = 'CPT/HCPCS' AND s.code = d.hcpcs)
  OR (s.code_type = 'MS-DRG' AND s.code = d.drg)
""")
log("All payer rows for the 4,350 shared codes", "raw_rates")

con.execute("CREATE OR REPLACE TEMP TABLE r AS SELECT * FROM raw_rates WHERE price IS NOT NULL")
log("Has a dollar price", "r")

con.execute("DELETE FROM r WHERE care_type IN ('Drugs', 'Supplies & devices')")
log("R1  Exclude drugs and supplies", "r")

con.execute("""DELETE FROM r WHERE (code_type = 'CPT/HCPCS' AND setting <> 'outpatient')
                              OR (code_type = 'MS-DRG' AND setting <> 'inpatient')""")
log("R2a Outpatient rates for CPT, inpatient for DRG", "r")

con.execute("DELETE FROM r WHERE rc BETWEEN '0960' AND '0989'")
log("R2b Drop St. Luke's professional-fee rows", "r")

con.execute("DELETE FROM r WHERE price <= 1")
log("R3  Drop prices of $1 or less", "r")

con.execute("""
CREATE OR REPLACE TEMP TABLE p AS
SELECT hosp, code_type, code, care_type, payer, plan,
       median(price) AS price, count(*) AS n_rates
FROM r GROUP BY ALL
""")
log("R4  One median price per plan per code (plan-level rows)", "p")

con.execute("""
DELETE FROM p WHERE (hosp, code_type, code, payer, plan) IN (
    SELECT hosp, code_type, code, payer, plan FROM (
        SELECT *, median(price) OVER (PARTITION BY hosp, code_type, code) AS code_median FROM p
    ) WHERE price > 10 * code_median OR price < code_median / 10
)""")
log("R5  Drop plan prices >10x from the hospital's code median", "p")

con.execute("""
CREATE OR REPLACE TABLE compared_codes AS
WITH m AS (
    SELECT code_type, code, care_type,
           median(price) FILTER (WHERE hosp = 'SLB') AS slb_median,
           median(price) FILTER (WHERE hosp = 'LVH') AS lvh_median
    FROM p GROUP BY ALL
)
SELECT *, greatest(slb_median, lvh_median) / least(slb_median, lvh_median) AS ratio
FROM m WHERE slb_median IS NOT NULL AND lvh_median IS NOT NULL
""")
con.execute("""
CREATE OR REPLACE TABLE excluded_r6 AS
SELECT c.*, s.description FROM compared_codes c JOIN shared_codes s USING (code_type, code)
WHERE ratio > 10
""")
removed_r6 = con.execute("SELECT count(*) FROM excluded_r6").fetchone()[0]
con.execute("DELETE FROM compared_codes WHERE ratio > 10")
con.execute("""
CREATE OR REPLACE TABLE plan_prices AS
SELECT p.* FROM p JOIN compared_codes c USING (code_type, code)
""")
log("R6  Drop codes where hospitals differ >10x; still priced at both", "plan_prices")

con.execute("CREATE OR REPLACE TABLE cleaning_funnel (step INT, rule VARCHAR, rows BIGINT, codes BIGINT)")
con.executemany("INSERT INTO cleaning_funnel VALUES (?, ?, ?, ?)", funnel)

print("Cleaning funnel")
print(con.execute("SELECT rule, rows, codes FROM cleaning_funnel ORDER BY step").fetchdf().to_string(index=False))
print(f"\nCodes removed by R6 (>10x between hospitals): {removed_r6}")
print("\nCompared codes by type")
print(con.execute("""
SELECT code_type, count(*) codes FROM compared_codes GROUP BY 1 ORDER BY 1
""").fetchdf().to_string(index=False))
