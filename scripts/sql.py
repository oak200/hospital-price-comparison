"""Run SQL (from a .sql file or literal string) against work/analysis.duckdb with both hospitals attached."""
import duckdb, os, sys, pandas as pd
pd.set_option("display.width", 250)
arg = sys.argv[1]
sql = open(arg, encoding="utf-8").read() if os.path.exists(arg) else arg
con = duckdb.connect("work/analysis.duckdb")
con.execute("ATTACH IF NOT EXISTS 'data/stlukes_bethlehem.duckdb' AS slb (READ_ONLY)")
con.execute("ATTACH IF NOT EXISTS 'data/lvh_cedar_crest.duckdb' AS lvh (READ_ONLY)")
for stmt in [s for s in sql.split(";") if s.strip()]:
    r = con.execute(stmt)
    if r.description:
        print(r.fetchdf().to_string(max_rows=300, max_colwidth=60, index=False))
        print()
