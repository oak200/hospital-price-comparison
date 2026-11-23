"""Step 3: build a normalized billing-code inventory for both hospitals.

Output: work/analysis.duckdb, table `code_inventory`
  one row per hospital x code_type x code, with flags for whether a
  negotiated (payer) price and a cash price exist.

Normalization rules
  - Strip the literal quote marks LVH puts around text values.
  - CPT/HCPCS: St. Luke's splits these across `cpt` and `hcpcs`; combine them.
    LVH appends modifiers to the code (e.g. 9928327 = 99283 + mod 27), so keep
    the first 5 characters as the base code and the rest as the modifier.
  - MS-DRG: zero-padded 3-digit code.
"""
import duckdb, os

os.makedirs("work", exist_ok=True)
con = duckdb.connect("work/analysis.duckdb")
con.execute("ATTACH 'data/stlukes_bethlehem.duckdb' AS slb (READ_ONLY)")
con.execute("ATTACH 'data/lvh_cedar_crest.duckdb' AS lvh (READ_ONLY)")

con.execute("""
CREATE OR REPLACE TABLE item_codes AS
WITH raw AS (
    SELECT 'SLB' AS hosp, charge_id,
           upper(coalesce(cpt, hcpcs)) AS hcpcs_raw,
           ms_drg AS drg_raw, rc, setting,
           discounted_cash, payer_count
    FROM slb.standard_charges
    UNION ALL
    SELECT 'LVH', charge_id,
           upper(replace(hcpcs, '"', '')),
           replace(ms_drg, '"', ''), replace(rc, '"', ''), replace(setting, '"', ''),
           discounted_cash, payer_count
    FROM lvh.standard_charges
)
SELECT hosp, charge_id, setting, rc, discounted_cash, payer_count,
       CASE WHEN regexp_matches(hcpcs_raw, '^[0-9A-Z][0-9]{3}[0-9A-Z]') THEN left(hcpcs_raw, 5) END AS hcpcs,
       CASE WHEN length(hcpcs_raw) > 5 THEN substr(hcpcs_raw, 6) END AS modifier,
       CASE WHEN regexp_matches(drg_raw, '^[0-9]{1,3}$') THEN lpad(drg_raw, 3, '0') END AS drg
FROM raw
""")

# Does each item have at least one negotiated dollar price?
con.execute("""
CREATE OR REPLACE TABLE item_has_rate AS
SELECT 'SLB' AS hosp, charge_id, count(standard_charge_dollar) > 0 AS has_rate
FROM slb.standard_charge_details GROUP BY charge_id
UNION ALL
SELECT 'LVH', charge_id, count(standard_charge_dollar) > 0
FROM lvh.standard_charge_details GROUP BY charge_id
""")

con.execute("""
CREATE OR REPLACE TABLE code_inventory AS
WITH x AS (
    SELECT i.*, coalesce(r.has_rate, false) AS has_rate
    FROM item_codes i LEFT JOIN item_has_rate r USING (hosp, charge_id)
),
codes AS (
    SELECT hosp, 'CPT/HCPCS' AS code_type, hcpcs AS code, has_rate,
           discounted_cash IS NOT NULL AS has_cash, modifier IS NOT NULL AS has_mod
    FROM x WHERE hcpcs IS NOT NULL
    UNION ALL
    SELECT hosp, 'MS-DRG', drg, has_rate, discounted_cash IS NOT NULL, false
    FROM x WHERE drg IS NOT NULL
)
SELECT hosp, code_type, code,
       count(*) AS items,
       bool_or(has_rate) AS has_rate,
       bool_or(has_cash) AS has_cash,
       bool_and(has_mod) AS modifier_only
FROM codes GROUP BY ALL
""")

print(con.execute("""
SELECT hosp, code_type,
       count(*) AS codes_listed,
       count(*) FILTER (WHERE has_rate) AS with_payer_price,
       count(*) FILTER (WHERE has_cash) AS with_cash,
       count(*) FILTER (WHERE modifier_only) AS modifier_only
FROM code_inventory GROUP BY ALL ORDER BY code_type, hosp
""").fetchdf().to_string(index=False))

print()
print(con.execute("""
WITH s AS (SELECT * FROM code_inventory WHERE hosp='SLB'),
     l AS (SELECT * FROM code_inventory WHERE hosp='LVH')
SELECT coalesce(s.code_type, l.code_type) AS code_type,
       count(*) FILTER (WHERE s.code IS NOT NULL AND l.code IS NOT NULL) AS listed_both,
       count(*) FILTER (WHERE s.has_rate AND l.has_rate) AS priced_both,
       count(*) FILTER (WHERE l.code IS NULL) AS slb_only,
       count(*) FILTER (WHERE s.code IS NULL) AS lvh_only
FROM s FULL JOIN l USING (code_type, code)
GROUP BY 1 ORDER BY 1
""").fetchdf().to_string(index=False))
