"""Run SQL from a file against one or both DBs. usage: python q.py <sqlfile> [SLB|LVH|both]"""
import duckdb, sys, pandas as pd
pd.set_option("display.width", 250)
DBS = {"SLB": "data/stlukes_bethlehem.duckdb", "LVH": "data/lvh_cedar_crest.duckdb"}
sql = open(sys.argv[1], encoding="utf-8").read()
which = sys.argv[2] if len(sys.argv) > 2 else "both"
for k, p in DBS.items():
    if which not in ("both", k):
        continue
    con = duckdb.connect(p, read_only=True)
    print(f"===== {k}")
    for stmt in [s for s in sql.split(";") if s.strip()]:
        try:
            print(con.execute(stmt).fetchdf().to_string(max_rows=300, max_colwidth=55))
        except Exception as e:
            print("ERR", e)
        print()
