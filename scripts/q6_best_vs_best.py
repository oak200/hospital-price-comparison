"""Step 8: best plan vs. best plan, St. Luke's against LVHN (Q6).

Best plans are read from q5_plan_ranking (rank 1 at each hospital).
Compared on procedures that both best plans price.

Measures
  - Counts: procedures compared, cheaper at each hospital, ties (within $1).
  - Typical difference: the median per-procedure difference, always stated as
    LVHN relative to St. Luke's ($ = LVHN - SLB; % = (LVHN - SLB) / SLB).
    Positive = LVHN costs more.
  - Totals: the sum of all compared procedure prices at each hospital (one
    unit of each procedure), with LVHN vs. St. Luke's % difference.
  - Limitation: the two best plans are Medicaid plans, which price inpatient
    stays by APR-DRG rather than MS-DRG, so almost no inpatient procedures overlap.

Outputs: tables q6_detail, q6_summary, q6_by_care_type; matching CSVs in output/
"""
import duckdb

con = duckdb.connect("work/analysis.duckdb")
show = lambda sql: print(con.execute(sql).fetchdf().to_string(index=False), "\n")

best = con.execute("""
SELECT CASE r.hospital WHEN 'St. Luke''s' THEN 'SLB' ELSE 'LVH' END AS hosp, p.payer, p.plan, r.carrier || ' ' || r.plan AS label
FROM q5_plan_ranking r JOIN plans p
  ON p.hosp = CASE r.hospital WHEN 'St. Luke''s' THEN 'SLB' ELSE 'LVH' END
 AND p.carrier = r.carrier AND p.plan = r.plan
WHERE r.rank = 1
""").fetchall()
best = {h: (payer, plan, label) for h, payer, plan, label in best}
print("Best plans:", {h: v[2] for h, v in best.items()}, "\n")

con.execute(f"""
CREATE OR REPLACE TABLE q6_detail AS
SELECT s.code_type, s.code, c.care_type, sc.description,
       s.price AS slb_price, l.price AS lvh_price,
       s.price - l.price AS diff,
       CASE WHEN abs(s.price - l.price) <= 1 THEN 'Tie'
            WHEN s.price < l.price THEN 'St. Luke''s' ELSE 'LVHN' END AS cheaper
FROM plan_prices s
JOIN plan_prices l USING (code_type, code)
JOIN compared_codes c USING (code_type, code)
JOIN shared_codes sc USING (code_type, code)
WHERE s.hosp = 'SLB' AND s.payer = '{best['SLB'][0]}' AND s.plan = '{best['SLB'][1]}'
  AND l.hosp = 'LVH' AND l.payer = '{best['LVH'][0]}' AND l.plan = '{best['LVH'][1]}'
""")

def summarize(group_col, group_label):
    return f"""
    WITH t AS (
        SELECT {group_col} AS grp,
               count(*) AS procedures_compared,
               count(*) FILTER (WHERE cheaper = 'St. Luke''s') AS slb_cheaper,
               count(*) FILTER (WHERE cheaper = 'LVHN') AS lvh_cheaper,
               count(*) FILTER (WHERE cheaper = 'Tie') AS ties,
               sum(slb_price) AS slb_total, sum(lvh_price) AS lvh_total
        FROM q6_detail GROUP BY 1
    ),
    med AS (
        SELECT {group_col} AS grp,
               median(lvh_price - slb_price) AS typical_dollar_diff,
               median((lvh_price - slb_price) / slb_price) AS typical_pct
        FROM q6_detail GROUP BY 1
    )
    SELECT t.grp AS {group_label}, procedures_compared, slb_cheaper, lvh_cheaper, ties,
           round(slb_total) AS slb_total, round(lvh_total) AS lvh_total,
           CASE WHEN slb_total <= lvh_total THEN 'St. Luke''s' ELSE 'LVHN' END AS cheaper_in_total,
           round(100 * (lvh_total - slb_total) / slb_total, 1) AS lvh_vs_slb_total_pct,
           round(typical_dollar_diff) AS lvh_minus_slb_typical_dollar,
           round(100 * typical_pct, 1) AS lvh_vs_slb_typical_pct
    FROM t JOIN med USING (grp)
    ORDER BY procedures_compared DESC
    """

all_sql = summarize("'All procedures'", "scope")
setting_sql = summarize("CASE code_type WHEN 'MS-DRG' THEN 'Inpatient (DRG)' ELSE 'Outpatient (CPT/HCPCS)' END", "scope")
con.execute(f"CREATE OR REPLACE TABLE q6_summary AS SELECT * FROM ({all_sql}) UNION ALL SELECT * FROM ({setting_sql})")
con.execute(f"CREATE OR REPLACE TABLE q6_by_care_type AS {summarize('care_type', 'care_type')}")

for t in ["q6_detail", "q6_summary", "q6_by_care_type"]:
    con.execute(f"COPY {t} TO 'output/{t}.csv' (HEADER)")

show("SELECT * FROM q6_summary")
show("SELECT * FROM q6_by_care_type")

s = con.execute("SELECT * FROM q6_summary WHERE scope = 'All procedures'").fetchdf().iloc[0]
if s.cheaper_in_total == "St. Luke's":
    wins, pct = s.slb_cheaper, 100 * (s.lvh_total - s.slb_total) / s.lvh_total
else:
    wins, pct = s.lvh_cheaper, 100 * (s.slb_total - s.lvh_total) / s.slb_total
print(f"Bottom line: {s.cheaper_in_total} is less expensive on {wins:,} of {s.procedures_compared:,} procedures, "
      f"about {pct:.0f}% lower overall (by total).")
