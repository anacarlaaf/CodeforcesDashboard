import pandas as pd

df = pd.read_parquet("data/cses_all.parquet")
print(df.sort_values("time").tail(10))
print(f"\nTotal: {len(df)} registros")

print(df[df["user"] == "anacarlaaf"].sort_values("time").tail(5)[["user", "problem_code", "time"]])