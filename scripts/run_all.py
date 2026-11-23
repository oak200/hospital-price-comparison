"""Run the whole analysis in order. Run from the project root: python scripts/run_all.py"""
import subprocess, sys

STEPS = [
    "build_code_inventory.py",   # Step 3: normalize billing codes at both hospitals
    "apply_care_type_lookup.py", # Step 3: group shared codes by type of care
    "clean_prices.py",           # Step 4: cleaning rules, one price per plan per procedure
    "data_questions.py",         # Step 5: Q1-Q4 (also builds the plans / carrier table)
    "build_cash_prices.py",      # Step 7: cash prices (LVHN parsed from descriptions)
    "q5_best_plan.py",           # Step 6: Q5 best plan at each hospital
    "q6_best_vs_best.py",        # Step 8: Q6
    "q7_four_way.py",            # Step 9: Q7
    "q8_q9_cash_vs_plan.py",     # Step 10: Q8-Q9
    "q10_top_procedures.py",     # Step 11: Q10
    "q11_by_carrier.py",         # Step 11: Q11
    "q12_facility_fees.py",      # Step 11: Q12
]

for script in STEPS:
    print(f"\n=== {script} ===", flush=True)
    result = subprocess.run([sys.executable, f"scripts/{script}"])
    if result.returncode != 0:
        sys.exit(f"{script} failed")
print("\nDone. Results are in output/.")
