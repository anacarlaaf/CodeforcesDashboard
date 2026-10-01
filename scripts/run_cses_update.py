import sys
import os
sys.path.insert(0, ".")

raw = os.environ.get("CSES_ACCOUNTS", "")
print(f"CSES_ACCOUNTS len: {len(raw)}")
print(f"CSES_ACCOUNTS preview: {raw[:30] if raw else 'VAZIO'}")

supabase_url = os.environ.get("SUPABASE_URL", "")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
print(f"SUPABASE_URL: {'OK' if supabase_url else 'VAZIO'}")
print(f"SUPABASE_SERVICE_ROLE_KEY len: {len(supabase_key)}")

import cses

cses.update()