"""Step 4: apply the draft care-type lookup to codes both hospitals price.

Rules
  - Inpatient DRGs are grouped by MS-DRG range.
  - CPT/HCPCS codes are grouped by code range. Where several ranges match,
    the most specific one (priority 1) wins over the broad section (priority 2).
  - Revenue codes (St. Luke's only; LVH doesn't publish them) are used as a
    cross-check on the CPT/HCPCS grouping.

Outputs
  work/analysis.duckdb: tables care_type_lookup, shared_codes
  output/care_type_review.csv: every shared code with its care type, for review
"""
import duckdb, os

os.makedirs("output", exist_ok=True)
con = duckdb.connect("work/analysis.duckdb")
con.execute("ATTACH IF NOT EXISTS 'data/stlukes_bethlehem.duckdb' AS slb (READ_ONLY)")

con.execute("""
CREATE OR REPLACE TABLE care_type_lookup AS
SELECT * FROM read_csv('lookup/care_type_lookup.csv', all_varchar=true)
""")

con.execute("""
CREATE OR REPLACE TABLE shared_codes AS
WITH in_both AS (
    SELECT s.code_type, s.code
    FROM code_inventory s JOIN code_inventory l USING (code_type, code)
    WHERE s.hosp = 'SLB' AND l.hosp = 'LVH' AND s.has_rate AND l.has_rate
),
-- one St. Luke's description and most common revenue code per code
slb_desc AS (
    SELECT coalesce(cpt, hcpcs) AS code, 'CPT/HCPCS' AS code_type,
           mode(description) AS description, lpad(mode(rc), 4, '0') AS rc
    FROM slb.standard_charges WHERE coalesce(cpt, hcpcs) IS NOT NULL GROUP BY 1
    UNION ALL
    SELECT ms_drg, 'MS-DRG', mode(description), NULL
    FROM slb.standard_charges WHERE ms_drg IS NOT NULL GROUP BY 1
),
keyed AS (
    SELECT b.*, d.description, d.rc,
           CASE WHEN b.code_type = 'MS-DRG' THEN 'MS-DRG'
                WHEN regexp_matches(b.code, '^[0-9]{5}$') THEN 'CPT'
                WHEN regexp_matches(b.code, '^[0-9]{4}[A-Z]$') THEN 'CPT-suffix'
                ELSE 'HCPCS' END AS code_system,
           CASE WHEN regexp_matches(b.code, '^[0-9]{4}[A-Z]$') THEN right(b.code, 1)
                ELSE b.code END AS match_key
    FROM in_both b LEFT JOIN slb_desc d USING (code_type, code)
),
code_match AS (
    SELECT k.*, l.care_type, l.notes AS rule,
           row_number() OVER (PARTITION BY k.code_type, k.code ORDER BY l.priority) AS rn
    FROM keyed k LEFT JOIN care_type_lookup l
      ON l.code_system = k.code_system AND k.match_key BETWEEN l.code_from AND l.code_to
),
rc_match AS (
    SELECT k.code_type, k.code, l.care_type AS rc_care_type,
           row_number() OVER (PARTITION BY k.code_type, k.code ORDER BY l.priority) AS rn
    FROM keyed k JOIN care_type_lookup l
      ON l.code_system = 'Revenue code' AND k.rc BETWEEN l.code_from AND l.code_to
)
SELECT c.code_type, c.code, c.description, c.care_type, c.rule, c.rc, r.rc_care_type
FROM code_match c LEFT JOIN rc_match r ON r.code_type = c.code_type AND r.code = c.code AND r.rn = 1
WHERE c.rn = 1
""")

con.execute("COPY (SELECT * FROM shared_codes ORDER BY code_type, care_type, code) TO 'output/care_type_review.csv' (HEADER)")

print("Shared codes by care type")
print(con.execute("""
SELECT coalesce(care_type, '** UNMAPPED **') AS care_type,
       count(*) FILTER (WHERE code_type = 'CPT/HCPCS') AS outpatient_codes,
       count(*) FILTER (WHERE code_type = 'MS-DRG') AS inpatient_drgs,
       count(*) AS total
FROM shared_codes GROUP BY ALL ORDER BY total DESC
""").fetchdf().to_string(index=False))

print("\nCross-check: CPT/HCPCS grouping vs St. Luke's revenue code")
print(con.execute("""
SELECT count(*) AS codes_with_rc,
       count(*) FILTER (WHERE care_type = rc_care_type) AS agree,
       round(100.0 * count(*) FILTER (WHERE care_type = rc_care_type) / count(*), 1) AS pct_agree
FROM shared_codes WHERE code_type = 'CPT/HCPCS' AND rc_care_type IS NOT NULL
""").fetchdf().to_string(index=False))

print("\nMost common disagreements")
print(con.execute("""
SELECT care_type AS by_code, rc_care_type AS by_rev_code, count(*) n, min(code) example
FROM shared_codes WHERE code_type = 'CPT/HCPCS' AND rc_care_type IS NOT NULL AND care_type <> rc_care_type
GROUP BY ALL ORDER BY n DESC LIMIT 12
""").fetchdf().to_string(index=False))
