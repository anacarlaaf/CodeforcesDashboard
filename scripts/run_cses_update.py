import sys
import os
sys.path.insert(0, ".")

raw = os.environ.get("CSES_ACCOUNTS", "")
print(f"CSES_ACCOUNTS len: {len(raw)}")
print(f"CSES_ACCOUNTS preview: {raw[:30] if raw else 'VAZIO'}")

import cses

cses.update(
    users_csv="data/users.csv",
    problems_csv="data/cses_problems.csv",
    cses_all_csv="data/cses_all.parquet",
)