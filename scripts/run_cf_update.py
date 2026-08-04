import sys
import os
sys.path.insert(0, ".")

import codeforces

codeforces.update(
    users_csv="data/users.csv",
    subs_parquet="data/cf_submissions.parquet",
    rating_parquet="data/cf_rating.parquet",
    users_parquet="data/cf_users.parquet",
)