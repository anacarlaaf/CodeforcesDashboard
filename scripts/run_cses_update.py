# scripts/run_cses_update.py
import sys
sys.path.insert(0, ".")

import cses

cses.update(
    users_csv="data/users.csv",
    problems_csv="data/cses_problems.csv",
    cses_all_csv="data/cses_all.parquet",
)