"""Step 11b: for each major carrier, which hospital is cheaper? (Q11)

Carriers listed at both hospitals are compared plan type by plan type
(commercial vs. commercial, Medicare Advantage vs. Medicare Advantage, ...),
so a carrier's Medicaid rates at one hospital are never set against its
commercial rates at the other.

  - Per hospital: the carrier's price for a procedure = the median across its
    plans of that type (e.g. IBC HMO and PPO pooled as IBC commercial).
  - Compared on procedures both hospitals price for that carrier and plan type.
  - Cheaper hospital = the lower total; % cheaper = (higher - lower) / higher.
  - Groups with fewer than 50 shared procedures are flagged as low coverage.

Outputs: table q11_by_carrier; output/q11_by_carrier.csv
"""
import duckdb

con = duckdb.connect("work/analysis.duckdb")
show = lambda sql: print(con.execute(sql).fetchdf().to_string(index=False), "\n")

con.execute("""
CREATE OR REPLACE TABLE q11_by_carrier AS
WITH cp AS (
    SELECT pp.hosp, pl.carrier, pl.plan_type, pp.code_type, pp.code,
           median(pp.price) AS price, string_agg(DISTINCT pl.plan, ' / ') AS plans
    FROM plan_prices pp JOIN plans pl USING (hosp, payer, plan)
    GROUP BY ALL
),
j AS (
    SELECT s.carrier, s.plan_type, s.code,
           s.price AS slb, l.price AS lvh, s.plans AS slb_plans, l.plans AS lvh_plans
    FROM cp s JOIN cp l USING (carrier, plan_type, code_type, code)
    WHERE s.hosp = 'SLB' AND l.hosp = 'LVH'
),
t AS (
    SELECT carrier, plan_type,
           string_agg(DISTINCT slb_plans, ' / ') AS slb_plans,
           string_agg(DISTINCT lvh_plans, ' / ') AS lvh_plans,
           count(*) AS procedures_compared,
           count(*) FILTER (WHERE slb < lvh - 1) AS slb_cheaper_on,
           count(*) FILTER (WHERE lvh < slb - 1) AS lvh_cheaper_on,
           sum(slb) AS slb_total, sum(lvh) AS lvh_total
    FROM j GROUP BY ALL
)
SELECT carrier, plan_type, slb_plans, lvh_plans, procedures_compared,
       slb_cheaper_on, lvh_cheaper_on,
       round(slb_total) AS slb_total, round(lvh_total) AS lvh_total,
       CASE WHEN slb_total < lvh_total THEN 'St. Luke''s' ELSE 'LVHN' END AS cheaper_hospital,
       round(100 * abs(slb_total - lvh_total) / greatest(slb_total, lvh_total)) AS pct_cheaper,
       procedures_compared < 50 AS low_coverage
FROM t ORDER BY carrier, plan_type
""")
con.execute("COPY q11_by_carrier TO 'output/q11_by_carrier.csv' (HEADER)")

show("""SELECT carrier, plan_type, procedures_compared, slb_cheaper_on, lvh_cheaper_on,
               cheaper_hospital, pct_cheaper, low_coverage FROM q11_by_carrier""")
show("""SELECT cheaper_hospital, count(*) AS carrier_plan_types
        FROM q11_by_carrier WHERE NOT low_coverage GROUP BY 1""")
