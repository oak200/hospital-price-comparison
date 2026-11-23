"""Step 5: answer the "About the data" questions (Q1-Q4).

Outputs (output/):
  q1_carriers.csv          carrier, plan, plan type, procedures priced, availability
  q2_prices_published.csv  items and codes listed / with cash price per hospital
  q3_comparability.csv     how many codes can be fairly compared
  q4_file_dates.csv        file dates per hospital
"""
import duckdb

con = duckdb.connect("work/analysis.duckdb")
con.execute("ATTACH IF NOT EXISTS 'data/stlukes_bethlehem.duckdb' AS slb (READ_ONLY)")
con.execute("ATTACH IF NOT EXISTS 'data/lvh_cedar_crest.duckdb' AS lvh (READ_ONLY)")
con.execute("CREATE OR REPLACE TABLE carrier_crosswalk AS SELECT * FROM read_csv('lookup/carrier_crosswalk.csv', all_varchar=true)")
show = lambda sql: print(con.execute(sql).fetchdf().to_string(index=False), "\n")

# ---------- Plan list with normalized carrier and plan type ----------
con.execute("""
CREATE OR REPLACE TABLE plans AS
WITH d AS (
    SELECT 'SLB' AS hosp, payer_name AS payer, plan_name AS plan,
           coalesce(cpt, hcpcs, 'DRG' || ms_drg) AS code, standard_charge_dollar AS price
    FROM slb.standard_charge_details
    UNION ALL
    SELECT 'LVH', replace(payer_name, '"', ''), replace(plan_name, '"', ''),
           coalesce(left(upper(replace(hcpcs, '"', '')), 5), 'DRG' || lpad(replace(ms_drg, '"', ''), 3, '0')),
           standard_charge_dollar
    FROM lvh.standard_charge_details
)
SELECT d.hosp, x.carrier, d.payer, d.plan,
       CASE WHEN upper(d.plan) LIKE '%MEDICAID%' OR upper(d.plan) LIKE '%COUNTY%'
                 OR x.carrier = 'Community Care Behavioral Health' THEN 'Medicaid'
            WHEN upper(d.plan) LIKE '%CHIP%' THEN 'CHIP'
            WHEN upper(d.plan) SIMILAR TO '.*(MEDICARE|FREEDOM BLUE|SNP|HEALTHSPRING).*' THEN 'Medicare Advantage'
            WHEN upper(d.plan) SIMILAR TO '.*(MARKETPLACE|ACA).*' OR x.carrier = 'Ambetter' THEN 'Marketplace (ACA)'
            WHEN upper(d.plan) = 'TRANSPLANTS' THEN 'Transplant network'
            WHEN upper(d.plan) = 'BEHAVIORAL' THEN 'Behavioral health'
            WHEN upper(d.plan) = 'MEDICAL RENTAL' THEN 'Rental network'
            ELSE 'Commercial' END AS plan_type,
       count(DISTINCT d.code) FILTER (WHERE d.price IS NOT NULL AND d.code IS NOT NULL) AS codes_priced_in_file
FROM d LEFT JOIN carrier_crosswalk x ON x.hosp = d.hosp AND x.payer_name = d.payer
GROUP BY ALL
""")
unmapped = con.execute("SELECT count(*) FROM plans WHERE carrier IS NULL").fetchone()[0]
assert unmapped == 0, f"{unmapped} payers missing from carrier crosswalk"

con.execute("""
CREATE OR REPLACE TABLE q1_carriers AS
WITH comp AS (
    SELECT hosp, payer, plan, count(*) AS compared_procedures_priced FROM plan_prices GROUP BY ALL
),
avail AS (
    SELECT carrier,
           CASE WHEN count(DISTINCT hosp) = 2 THEN 'Both'
                WHEN max(hosp) = 'SLB' THEN 'St. Luke''s only' ELSE 'LVHN only' END AS availability
    FROM plans GROUP BY 1
)
SELECT CASE p.hosp WHEN 'SLB' THEN 'St. Luke''s' ELSE 'LVHN' END AS hospital,
       p.carrier, p.plan, p.plan_type, a.availability,
       p.codes_priced_in_file AS procedures_priced,
       coalesce(c.compared_procedures_priced, 0) AS of_4003_compared
FROM plans p JOIN avail a USING (carrier)
LEFT JOIN comp c USING (hosp, payer, plan)
ORDER BY hospital DESC, carrier, plan
""")
con.execute("COPY q1_carriers TO 'output/q1_carriers.csv' (HEADER)")

print("Q1  Carriers by availability")
show("""
SELECT availability, count(DISTINCT carrier) AS carriers, string_agg(DISTINCT carrier, ', ' ORDER BY carrier) AS names
FROM q1_carriers GROUP BY 1 ORDER BY 1
""")
show("""
SELECT hospital, count(DISTINCT carrier) carriers, count(*) plans,
       count(*) FILTER (WHERE plan_type = 'Commercial') commercial,
       count(*) FILTER (WHERE plan_type = 'Medicare Advantage') medicare_adv,
       count(*) FILTER (WHERE plan_type IN ('Medicaid', 'CHIP')) medicaid_chip,
       count(*) FILTER (WHERE plan_type NOT IN ('Commercial', 'Medicare Advantage', 'Medicaid', 'CHIP')) other
FROM q1_carriers GROUP BY 1 ORDER BY 1 DESC
""")

# ---------- Q2: prices published ----------
con.execute("""
CREATE OR REPLACE TABLE q2_prices_published AS
SELECT CASE hosp WHEN 'SLB' THEN 'St. Luke''s' ELSE 'LVHN' END AS hospital,
       count(*) AS items_listed,
       count(*) FILTER (WHERE discounted_cash IS NOT NULL) AS items_with_cash,
       count(DISTINCT coalesce(hcpcs, 'DRG' || drg)) FILTER (WHERE hcpcs IS NOT NULL OR drg IS NOT NULL) AS billing_codes_listed,
       count(DISTINCT coalesce(hcpcs, 'DRG' || drg)) FILTER (WHERE (hcpcs IS NOT NULL OR drg IS NOT NULL) AND discounted_cash IS NOT NULL) AS billing_codes_with_cash,
       count(DISTINCT coalesce(hcpcs, 'DRG' || drg)) FILTER (WHERE (hcpcs IS NOT NULL OR drg IS NOT NULL) AND payer_count > 0) AS billing_codes_with_plan_price
FROM item_codes GROUP BY hosp ORDER BY hospital DESC
""")
con.execute("COPY q2_prices_published TO 'output/q2_prices_published.csv' (HEADER)")
print("Q2  Prices published")
show("SELECT * FROM q2_prices_published")

# ---------- Q3: comparability ----------
con.execute("""
CREATE OR REPLACE TABLE q3_comparability AS
WITH s AS (SELECT * FROM code_inventory WHERE hosp = 'SLB'),
     l AS (SELECT * FROM code_inventory WHERE hosp = 'LVH'),
     j AS (SELECT s.code_type, s.code AS s_code, l.code AS l_code, s.has_rate s_rate, l.has_rate l_rate,
                  s.has_cash s_cash, l.has_cash l_cash
           FROM s FULL JOIN l USING (code_type, code))
SELECT 1 AS ord, 'Listed by both hospitals' AS category, count(*) FILTER (WHERE s_code IS NOT NULL AND l_code IS NOT NULL) AS codes FROM j
UNION ALL SELECT 2, 'Listed by St. Luke''s only', count(*) FILTER (WHERE l_code IS NULL) FROM j
UNION ALL SELECT 3, 'Listed by LVHN only', count(*) FILTER (WHERE s_code IS NULL) FROM j
UNION ALL SELECT 4, 'Listed but no price (either hospital)',
       count(*) FILTER (WHERE (s_code IS NOT NULL AND NOT s_rate AND NOT s_cash) OR (l_code IS NOT NULL AND NOT l_rate AND NOT l_cash)) FROM j
UNION ALL SELECT 5, 'Priced at both', (SELECT count(*) FROM shared_codes)
UNION ALL SELECT 6, '  less drugs and supplies', -(SELECT count(*) FROM shared_codes WHERE care_type IN ('Drugs', 'Supplies & devices'))
UNION ALL SELECT 7, '  less outliers / non-comparable codes',
       (SELECT count(*) FROM compared_codes) - (SELECT count(*) FROM shared_codes WHERE care_type NOT IN ('Drugs', 'Supplies & devices'))
UNION ALL SELECT 8, 'Fairly compared', (SELECT count(*) FROM compared_codes)
ORDER BY ord
""")
con.execute("COPY (SELECT category, codes FROM q3_comparability) TO 'output/q3_comparability.csv' (HEADER)")
print("Q3  Comparability (billing codes: CPT/HCPCS + MS-DRG)")
show("SELECT category, codes FROM q3_comparability")

# ---------- Q4: file dates ----------
con.execute("""
CREATE OR REPLACE TABLE q4_file_dates AS
SELECT 'St. Luke''s' AS hospital, h.last_updated_on AS file_last_updated, m.data_downloaded AS downloaded_by_oria, m.file_format
FROM slb.hospitals h, slb.source_metadata m
UNION ALL
SELECT 'LVHN', h.last_updated_on, m.data_downloaded, m.file_format
FROM lvh.hospitals h, lvh.source_metadata m
""")
con.execute("COPY q4_file_dates TO 'output/q4_file_dates.csv' (HEADER)")
print("Q4  File dates")
show("SELECT * FROM q4_file_dates")
