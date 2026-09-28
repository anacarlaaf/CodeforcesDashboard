import os
import sys
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

# Carrega variáveis do .env
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Validação das variáveis críticas
if not SUPABASE_URL or not SERVICE_ROLE_KEY:
    sys.exit("❌ Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no .env")

# Cliente com service role: ignora RLS
sb: Client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

CSV_PATH = "data/users.csv"

df = pd.read_csv(CSV_PATH)


def to_int_or_none(value):
    """Converte valores como 237535.0 (float) ou '237535.0' (string) para
    int puro, e trata NaN/None retornando None."""
    if pd.isna(value):
        return None
    return int(float(value))


def to_str_or_none(value):
    """Evita mandar 'nan' como string para colunas de texto quando o
    campo estiver vazio no CSV."""
    if pd.isna(value):
        return None
    return str(value)


sucesso = 0
erros = 0

for _, row in df.iterrows():
    try:
        sb.table("members").insert({
            "codeforces_handle": row["codeforces"],
            "cses_user": to_str_or_none(row.get("cses_user")),
            "cses_code": to_int_or_none(row.get("cses_code")),
            "cf_verified": True,
        }).execute()
        sucesso += 1
    except Exception as e:
        erros += 1
        print(f"❌ Erro ao inserir {row['codeforces']}: {e}")

print(f"\n✅ Inseridos: {sucesso}")
print(f"❌ Erros: {erros}")