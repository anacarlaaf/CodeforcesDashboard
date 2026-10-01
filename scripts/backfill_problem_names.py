"""
Preenche `problem_name` nas submissões do Codeforces já salvas no
Supabase (a coluna foi adicionada depois — linhas antigas estão NULL).

Antes de rodar, crie a coluna no Supabase:

    alter table submissions add column if not exists problem_name text;

Rebaixa o histórico completo de cada handle via user.status (que traz
o nome do problema, inclusive de gym/mashup privado) e regrava só as
submissões que já existem no banco — não adiciona histórico novo.

Uso: python scripts/backfill_problem_names.py
"""

import sys
import time
sys.path.insert(0, ".")

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

saved = db.load_submissions(handles, source="CF")

saved_ids = set(
    zip(saved["handle"], saved["source_id"].astype(str))
) if not saved.empty else set()

for h in handles:

    subs = codeforces.cf_request(
        "user.status",
        handle=h,
        params={"handle": h},
    )

    rows = [
        codeforces._cf_submission_to_row(h, s)
        for s in subs
        if s.get("id") is not None
        and (h, str(s["id"])) in saved_ids
    ]

    # upsert em blocos pra não estourar o tamanho da requisição
    for i in range(0, len(rows), 500):
        db.save_submissions(rows[i:i + 500])

    print(f"[backfill] {h}: {len(rows)} submissões atualizadas.")

    time.sleep(2)
