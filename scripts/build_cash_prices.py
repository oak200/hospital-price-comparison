"""Step 7: build one cash (self-pay) price per procedure for each hospital.

St. Luke's: cash is published on coded rows. Use outpatient facility items
  (professional-fee revenue codes 096x-098x excluded), median per code.
LVHN: cash appears only on chargemaster (CDM) rows, which carry no billing code.
  Many descriptions embed the CPT code, e.g. "HB 23570 CLOSED TX SCAPULAR ..."
  or "HB OT 97552 GROUP CAREGIVER TRAINING". Decision 2026-11-23: parse the code
  from the description.
    - Take the first 5-character CPT/HCPCS-shaped token after "HB".
    - Skip rows where the code carries a modifier suffix (e.g. "27650-50",
      a bilateral procedure priced at 150%), so we keep the base price.
    - Median per code when several CDM rows share a code.
Both hospitals: drop cash of $1 or less. Where both hospitals have a cash price,
drop the code if the two cash prices differ by more than 10x (same logic as
rule R6; catches mis-parsed codes). A cap relative to plan prices was tested and
rejected: St. Luke's cash is legitimately 1-46x its typical plan price.

Output: table cash_prices (hosp, code_type, code, cash, n_items), cash_funnel
"""
import duckdb

con = duckdb.connect("work/analysis.duckdb")
con.execute("ATTACH IF NOT EXISTS 'data/stlukes_bethlehem.duckdb' AS slb (READ_ONLY)")
con.execute("ATTACH IF NOT EXISTS 'data/lvh_cedar_crest.duckdb' AS lvh (READ_ONLY)")
show = lambda sql: print(con.execute(sql).fetchdf().to_string(index=False), "\n")

con.execute(r"""
CREATE OR REPLACE TEMP TABLE cash_raw AS
SELECT 'SLB' AS hosp, coalesce(cpt, hcpcs) AS code, discounted_cash AS cash
FROM slb.standard_charges
WHERE coalesce(cpt, hcpcs) IS NOT NULL AND discounted_cash > 1
  AND setting = 'outpatient' AND NOT (lpad(rc, 4, '0') BETWEEN '0960' AND '0989')
UNION ALL
SELECT 'LVH', code, cash FROM (
    SELECT regexp_extract(replace(description, '"', ''),
               '^HB (?:[A-Z]{1,4} )?([0-9]{4}[0-9A-Z]|[A-Z][0-9]{4})(?:[^-0-9A-Z]|$)', 1) AS code,
           discounted_cash AS cash
    FROM lvh.standard_charges
    WHERE cdm IS NOT NULL AND discounted_cash > 1
) WHERE code <> ''
""")

con.execute("""
CREATE OR REPLACE TEMP TABLE cash_med AS
SELECT hosp, 'CPT/HCPCS' AS code_type, code, median(cash) AS cash, count(*) AS n_items
FROM cash_raw GROUP BY ALL
""")

# Keep compared codes only, and apply the 10x outlier rule against plan prices
con.execute("""
CREATE OR REPLACE TABLE cash_prices AS
WITH c AS (
    SELECT cash_med.* FROM cash_med JOIN compared_codes USING (code_type, code)
),
bad AS (
    SELECT code FROM c GROUP BY code
    HAVING count(*) = 2 AND max(cash) / min(cash) > 10
)
SELECT * FROM c WHERE code NOT IN (SELECT code FROM bad)
""")

print("LVHN cash rows: how many descriptions yielded a code")
show(r"""
SELECT count(*) AS cdm_rows_with_cash,
       count(*) FILTER (WHERE regexp_matches(replace(description, '"', ''),
           '^HB (?:[A-Z]{1,4} )?([0-9]{4}[0-9A-Z]|[A-Z][0-9]{4})(?:[^-0-9A-Z]|$)')) AS code_parsed
FROM lvh.standard_charges WHERE cdm IS NOT NULL AND discounted_cash > 1
""")

print("Cash coverage of the 3,233 compared outpatient codes")
show("""
WITH m AS (SELECT * FROM cash_med JOIN compared_codes USING (code_type, code))
SELECT hosp,
       count(*) AS compared_codes_with_cash,
       (SELECT count(*) FROM cash_prices c WHERE c.hosp = m.hosp) AS after_outlier_rule
FROM m GROUP BY hosp ORDER BY hosp DESC
""")
print("Codes with cash at BOTH hospitals:",
      con.execute("SELECT count(*) FROM (SELECT code FROM cash_prices GROUP BY code HAVING count(*) = 2)").fetchone()[0])
