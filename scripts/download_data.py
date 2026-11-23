"""Download both hospitals' parsed price files (DuckDB) from Trilliant Oria into data/."""
import os, urllib.request

BASE = "https://oria-data.trillianthealth.com/data/store/completed"
FILES = {
    "data/stlukes_bethlehem.duckdb":
        f"{BASE}/st_lukes_hospital_bethlehem_campus-c43ea/20260718/st_lukes_hospital_bethlehem_campus-c43ea_parsed.duckdb",
    "data/lvh_cedar_crest.duckdb":
        f"{BASE}/lehigh_valley_hospital_cedar_crest-9591f/20260718/lehigh_valley_hospital_cedar_crest-9591f_parsed.duckdb",
}

os.makedirs("data", exist_ok=True)
for path, url in FILES.items():
    if os.path.exists(path):
        print(f"{path} already present, skipping")
        continue
    print(f"Downloading {path} ...")
    urllib.request.urlretrieve(url, path)
    print(f"  {os.path.getsize(path) / 1e6:.0f} MB")
