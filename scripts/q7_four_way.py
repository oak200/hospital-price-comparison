"""Step 9: best plans and cash at both hospitals, compared four ways (Q7).

For each procedure, compare four prices:
  SLB best plan (Highmark Wholecare Medicaid), LVHN best plan (UnitedHealthcare
  Managed Medicaid), SLB cash, LVHN cash.
Only procedures with all four prices are used, so every option is judged on the
same basket. (LVHN cash is parsed from chargemaster descriptions; see Step 7.)

Measures
  - Lowest-on counts: how many procedures each option is the lowest on. An option
    within $1 of the lowest also counts, so ties credit every tied option.
  - Totals: the sum of each option's prices across the basket.
  - Bottom line: the cheapest option by total, and how much lower it is than the
    next-cheapest option.

Outputs: tables q7_detail, q7_summary, q7_by_care_type; matching CSVs in output/
"""
import duckdb

con = duckdb.connect("work/analysis.duckdb")
show = lambda sql: print(con.execute(sql).fetchdf().to_string(index=False), "\n")

OPTIONS = {
    "slb_plan": "St. Luke's best plan",
    "lvh_plan": "LVHN best plan",
    "slb_cash": "St. Luke's cash",
    "lvh_cash": "LVHN cash",
}

con.execute("""
CREATE OR REPLACE TABLE q7_detail AS
WITH d AS (
    SELECT q.code_type, q.code, q.care_type, q.description,
           q.slb_price AS slb_plan, q.lvh_price AS lvh_plan,
           cs.cash AS slb_cash, cl.cash AS lvh_cash
    FROM q6_detail q
    JOIN cash_prices cs ON cs.hosp = 'SLB' AND cs.code_type = q.code_type AND cs.code = q.code
    JOIN cash_prices cl ON cl.hosp = 'LVH' AND cl.code_type = q.code_type AND cl.code = q.code
)
SELECT *, least(slb_plan, lvh_plan, slb_cash, lvh_cash) AS lowest FROM d
""")

def summary_sql(group_col):
    wins = ",\n".join(
        f"count(*) FILTER (WHERE {k} <= lowest + 1) AS {k}_lowest_on" for k in OPTIONS)
    totals = ",\n".join(f"round(sum({k})) AS {k}_total" for k in OPTIONS)
    return f"""
    SELECT {group_col} AS grp, count(*) AS procedures,
           {wins},
           {totals}
    FROM q7_detail GROUP BY 1 ORDER BY procedures DESC
    """

con.execute(f"CREATE OR REPLACE TABLE q7_summary AS {summary_sql(chr(39) + 'All procedures' + chr(39))}")
con.execute(f"CREATE OR REPLACE TABLE q7_by_care_type AS {summary_sql('care_type')}")
for t in ["q7_detail", "q7_summary", "q7_by_care_type"]:
    con.execute(f"COPY {t} TO 'output/{t}.csv' (HEADER)")

s = con.execute("SELECT * FROM q7_summary").fetchdf().iloc[0]
print(f"Procedures with all four prices: {s.procedures}\n")
print(f"{'Option':<22}{'Lowest on':>10}{'Total $':>14}")
for k, label in sorted(OPTIONS.items(), key=lambda kv: s[f'{kv[0]}_total']):
    print(f"{label:<22}{s[f'{k}_lowest_on']:>10,}{s[f'{k}_total']:>14,.0f}")

ranked = sorted(OPTIONS, key=lambda k: s[f"{k}_total"])
best, second = ranked[0], ranked[1]
pct = 100 * (s[f"{second}_total"] - s[f"{best}_total"]) / s[f"{second}_total"]
print(f"\nBottom line: {OPTIONS[best]} is the least expensive option overall, about {pct:.0f}% lower "
      f"than the next-cheapest ({OPTIONS[second]}), and lowest on {s[f'{best}_lowest_on']:,} of {s.procedures:,} procedures.\n")

show("SELECT * FROM q7_by_care_type")
