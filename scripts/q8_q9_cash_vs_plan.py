"""Step 10: cash vs. the best plan at each hospital (Q8, Q9).

At each hospital, compare that hospital's cash price with its best plan's price
(rank 1 in Q5) on every procedure that has both.

Measures
  Q8  procedures compared; cash cheaper / plan cheaper / ties (within $1);
      typical difference stated as cash relative to plan
      ($ = cash - plan; % = (cash - plan) / plan; positive = cash costs more).
  Q9  totals at cash and at the best plan; the better option by total, how much
      lower it is ((higher - lower) / higher), and on how many procedures it wins.
      Broken out by type of care.

Outputs: tables q8_q9_detail, q8_q9_summary, q8_q9_by_care_type; CSVs in output/
"""
import duckdb

con = duckdb.connect("work/analysis.duckdb")
show = lambda sql: print(con.execute(sql).fetchdf().to_string(index=False), "\n")

con.execute("""
CREATE OR REPLACE TABLE q8_q9_detail AS
WITH best AS (
    SELECT CASE r.hospital WHEN 'St. Luke''s' THEN 'SLB' ELSE 'LVH' END AS hosp, p.payer, p.plan,
           r.carrier || ' ' || r.plan AS best_plan
    FROM q5_plan_ranking r JOIN plans p
      ON p.hosp = CASE r.hospital WHEN 'St. Luke''s' THEN 'SLB' ELSE 'LVH' END
     AND p.carrier = r.carrier AND p.plan = r.plan
    WHERE r.rank = 1
)
SELECT CASE pp.hosp WHEN 'SLB' THEN 'St. Luke''s' ELSE 'LVHN' END AS hospital,
       b.best_plan, pp.code_type, pp.code, c.care_type, s.description,
       pp.price AS plan_price, cp.cash AS cash_price,
       CASE WHEN abs(cp.cash - pp.price) <= 1 THEN 'Tie'
            WHEN cp.cash < pp.price THEN 'Cash' ELSE 'Plan' END AS cheaper
FROM plan_prices pp
JOIN best b USING (hosp, payer, plan)
JOIN cash_prices cp USING (hosp, code_type, code)
JOIN compared_codes c USING (code_type, code)
JOIN shared_codes s USING (code_type, code)
""")

def summary_sql(extra_group):
    return f"""
    WITH t AS (
        SELECT hospital, {extra_group} AS grp, any_value(best_plan) AS best_plan,
               count(*) AS procedures_compared,
               count(*) FILTER (WHERE cheaper = 'Cash') AS cash_cheaper,
               count(*) FILTER (WHERE cheaper = 'Plan') AS plan_cheaper,
               count(*) FILTER (WHERE cheaper = 'Tie') AS ties,
               round(median(cash_price - plan_price)) AS typical_cash_minus_plan,
               round(100 * median((cash_price - plan_price) / plan_price)) AS typical_cash_vs_plan_pct,
               round(sum(cash_price)) AS cash_total,
               round(sum(plan_price)) AS plan_total
        FROM q8_q9_detail GROUP BY 1, 2
    )
    SELECT *,
           CASE WHEN cash_total < plan_total THEN 'Cash' ELSE 'Negotiated rate' END AS better_overall,
           round(100 * abs(cash_total - plan_total) / greatest(cash_total, plan_total)) AS pct_lower,
           CASE WHEN cash_total < plan_total THEN cash_cheaper ELSE plan_cheaper END AS better_on
    FROM t ORDER BY hospital DESC, procedures_compared DESC
    """

con.execute(f"CREATE OR REPLACE TABLE q8_q9_summary AS {summary_sql(chr(39) + 'All procedures' + chr(39))}")
con.execute(f"CREATE OR REPLACE TABLE q8_q9_by_care_type AS {summary_sql('care_type')}")
for t in ["q8_q9_detail", "q8_q9_summary", "q8_q9_by_care_type"]:
    con.execute(f"COPY {t} TO 'output/{t}.csv' (HEADER)")

show("SELECT * EXCLUDE (grp) FROM q8_q9_summary")
for r in con.execute("SELECT * FROM q8_q9_summary").fetchdf().itertuples():
    choice = "cash" if r.better_overall == "Cash" else "the negotiated rate"
    print(f"At {r.hospital}, {choice} is better overall, about {r.pct_lower:.0f}% lower, "
          f"and better on {r.better_on:,} of {r.procedures_compared:,} procedures.")
print()
show("""SELECT hospital, grp AS care_type, procedures_compared, cash_cheaper, plan_cheaper, ties,
               typical_cash_vs_plan_pct, cash_total, plan_total, better_overall, pct_lower
        FROM q8_q9_by_care_type""")
