import pandas as pd

df = pd.read_parquet("data/cses_all.parquet")
print(df["time"].dtype)
print(df[df["user"].isin(["anacarlaaf", "alejr"])][["user", "problem_code", "time"]])