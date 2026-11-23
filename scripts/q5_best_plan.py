"""Step 6: find the best (lowest-priced) plan at each hospital (Q5).

Method
  - All plan types are eligible (decision 2026-11-23), but a plan must price at
    least half of the 4,003 compared procedures to be ranked.
  - Ranking metric, the price index: for each procedure, the plan's price divided
    by the median of all plans' prices for that procedure at that hospital. The
    plan's index is the median of those ratios. 100% = typical, lower = cheaper.
    This puts a $14 lab test and a $30K surgery on the same scale.
  - Typical price as % of cash: the median of plan price / hospital cash price,
    over procedures with a cash price (outpatient codes only; LVHN cash is
    parsed from chargemaster descriptions and covers fewer codes).
  - Cheapest-plan count: the number of procedures where the plan has the lowest
    price among ranked plans at that hospital. Tied plans each get the win.

Outputs: table q5_plan_ranking; output/q5_plan_ranking.csv
"""
import duckdb

con = duckdb.connect("work/analysis.duckdb")
con.execute("ATTACH IF NOT EXISTS 'data/stlukes_bethlehem.duckdb' AS slb (READ_ONLY)")
show = lambda sql: print(con.execute(sql).fetchdf().to_string(index=False), "\n")

# Cash prices come from table cash_prices (scripts/build_cash_prices.py)

total = con.execute("SELECT count(*) FROM compared_codes").fetchone()[0]

con.execute(f"""
CREATE OR REPLACE TABLE q5_plan_ranking AS
WITH pp AS (
    SELECT p.*, pl.carrier, pl.plan_type,
           p.price / median(p.price) OVER (PARTITION BY p.hosp, p.code_type, p.code) AS idx
    FROM plan_prices p JOIN plans pl USING (hosp, payer, plan)
),
coverage AS (
    SELECT hosp, payer, plan, count(*) AS procedures_priced FROM pp GROUP BY ALL
),
ranked_plans AS (
    SELECT * FROM coverage WHERE procedures_priced >= {total} / 2
),
wins AS (
    SELECT hosp, payer, plan, count(*) AS cheapest_on
    FROM (
        SELECT pp.*, min(price) OVER (PARTITION BY pp.hosp, code_type, code) AS min_price
        FROM pp JOIN ranked_plans USING (hosp, payer, plan)
    ) WHERE price = min_price GROUP BY ALL
),
cash_pct AS (
    SELECT pp.hosp, payer, plan, median(price / c.cash) AS pct_of_cash, count(*) AS n_with_cash
    FROM pp JOIN cash_prices c USING (hosp, code_type, code) GROUP BY ALL
)
SELECT CASE pp.hosp WHEN 'SLB' THEN 'St. Luke''s' ELSE 'LVHN' END AS hospital,
       rank() OVER (PARTITION BY pp.hosp ORDER BY median(idx)) AS rank,
       carrier, pp.plan, plan_type,
       r.procedures_priced,
       round(100.0 * r.procedures_priced / {total}, 0) AS pct_of_compared,
       round(100 * median(idx), 0) AS price_index,
       round(100 * any_value(c.pct_of_cash), 0) AS pct_of_cash,
       coalesce(any_value(w.cheapest_on), 0) AS cheapest_on
FROM pp JOIN ranked_plans r USING (hosp, payer, plan)
LEFT JOIN wins w USING (hosp, payer, plan)
LEFT JOIN cash_pct c USING (hosp, payer, plan)
GROUP BY pp.hosp, carrier, pp.plan, plan_type, r.procedures_priced
ORDER BY hospital DESC, rank
""")
con.execute("COPY q5_plan_ranking TO 'output/q5_plan_ranking.csv' (HEADER)")

print(f"Compared procedures: {total}; ranking threshold: {total // 2}+ priced\n")
show("SELECT * FROM q5_plan_ranking")
show(f"""
SELECT CASE hosp WHEN 'SLB' THEN 'St. Luke''s' ELSE 'LVHN' END AS hospital,
       count(*) AS plans_with_prices,
       count(*) FILTER (WHERE n >= {total} / 2) AS plans_ranked
FROM (SELECT hosp, payer, plan, count(*) n FROM plan_prices GROUP BY ALL) GROUP BY 1 ORDER BY 1 DESC
""")
