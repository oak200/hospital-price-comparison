import duckdb, sys
DBS = {"SLB": "data/stlukes_bethlehem.duckdb", "LVH": "data/lvh_cedar_crest.duckdb"}
q = sys.argv[1]
for k, p in DBS.items():
    con = duckdb.connect(p, read_only=True)
    print(f"===== {k}")
    try:
        print(con.execute(q).fetchdf().to_string(max_rows=200, max_colwidth=60))
    except Exception as e:
        print("ERR", e)
