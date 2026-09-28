import sys
import os
sys.path.insert(0, ".")

raw = os.environ.get("CODEFORCES_USERS", "")
print(f"CODEFORCES_USERS len: {len(raw)}")

supabase_url = os.environ.get("SUPABASE_URL", "")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
print(f"SUPABASE_URL: {'OK' if supabase_url else 'VAZIO'}")
print(f"SUPABASE_SERVICE_ROLE_KEY len: {len(supabase_key)}")

import db
import codeforces

members = db.load_members_df()

handles = (
    members["codeforces"]
    .dropna()
    .astype(str)
    .str.strip()
)

handles = handles[handles != ""].tolist()

print(f"Sincronizando {len(handles)} handles: {handles}")

codeforces.sync_cf_submissions(handles)