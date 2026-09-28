"""
Reproduz, fora do Streamlit, o mesmo caminho que dashboard.py usa pra
ler e processar as submissões de um handle — pra ver em qual etapa o
dado desaparece.

Uso:
    python diagnostico_dashboard.py lip33
"""

import sys
import pandas as pd
import db

handle = sys.argv[1] if len(sys.argv) > 1 else "lip33"

print(f"1) db.load_submissions(['{handle}'])")
subs = db.load_submissions([handle])
print(f"   -> {len(subs)} linhas no total (CF+CSES)")

if subs.empty:
    print("   !! Veio vazio já aqui — o problema é no load_submissions/consulta.")
    sys.exit(0)

print(f"   colunas: {list(subs.columns)}")

cses_subs = subs[subs["source"] == "CSES"]
print(f"   -> dessas, {len(cses_subs)} são CSES")

if cses_subs.empty:
    print("   !! Nenhuma linha com source == 'CSES' — confere se a coluna")
    print("      'source' veio como string 'CSES' mesmo (maiúscula certa, sem espaço).")
    print(f"   valores únicos de 'source' encontrados: {subs['source'].unique()}")
    sys.exit(0)

print("\n2) Conversão de data (subs['date'])")
subs = subs.copy()
subs["date"] = pd.to_datetime(subs["date"], utc=True)
print(subs.loc[subs["source"] == "CSES", ["problem.index", "date"]].sort_values("date", ascending=False).head(10))

print("\n3) Filtro por período (últimos 30 dias, pra bater com o teste do SQL)")
end = pd.Timestamp.now(tz="UTC")
start = end - pd.Timedelta(days=30)
filtered = subs[(subs["date"] >= start) & (subs["date"] <= end)]
print(f"   -> {len(filtered)} linhas no período (todas as fontes)")
print(f"   -> {len(filtered[filtered['source'] == 'CSES'])} são CSES no período")

print("\n4) verdict == 'OK' (equivalente ao 'solved' do dashboard)")
solved = filtered[filtered["verdict"] == "OK"]
print(f"   -> {len(solved)} linhas com verdict OK")

print("\n5) drop_duplicates (equivalente ao 'unique_solved')")
unique_solved = solved.drop_duplicates(["handle", "problem.contestId", "problem.index"])
print(f"   -> {len(unique_solved)} linhas após dedup")
print(unique_solved[["handle", "source", "problem.contestId", "problem.index", "problem.rating"]])