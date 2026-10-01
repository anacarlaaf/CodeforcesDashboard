"""
Camada de acesso ao Supabase compartilhada entre codeforces.py e
cses.py.

Três tabelas:
  - telegram_users: cadastro do bot do Telegram (handle, fuso,
    lembretes e controle de último envio), uma linha por chat_id.
  - members: cadastro dos membros (handle do Codeforces, usuário do
    CSES, etc).
  - submissions: histórico UNIFICADO de submissões, tanto do
    Codeforces quanto do CSES, na mesma tabela — diferenciadas pela
    coluna `source` ('CF' ou 'CSES'). Isso evita ter que fazer
    concat/merge manual dessas duas fontes toda vez que o dashboard
    precisa ler o histórico de alguém.

Schema esperado (SQL já criado no Supabase):

    create table submissions (
      source text not null check (source in ('CF', 'CSES')),
      source_id text not null,
      handle text not null,
      contest_id text,
      problem_index text,
      problem_name text,
      problem_rating integer,
      problem_tags text[],
      verdict text not null,
      submitted_at timestamptz not null,
      cf_id bigint,
      inserted_at timestamptz default now(),
      primary key (source, source_id)
    );
"""

import os
import streamlit as st
import pandas as pd
from supabase import create_client


def _get_secret(name):
    value = os.environ.get(name)
    if value:
        return value
    try:
        return st.secrets.get(name)
    except Exception:
        return None


SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = _get_secret("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError(
        "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY não encontrados. "
        "Verifique as variáveis de ambiente ou .streamlit/secrets.toml."
    )

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

MEMBERS_TABLE = "members"
SUBMISSIONS_TABLE = "submissions"
TELEGRAM_USERS_TABLE = "telegram_users"

PAGE_SIZE = 1000  # limite de linhas por resposta do Supabase


# -----------------------------------
# MEMBERS
# -----------------------------------

def load_members_df() -> pd.DataFrame:
    """Mesmas colunas que data/users.csv tinha: codeforces, cses_user,
    cses_code."""

    rows = sb.table(MEMBERS_TABLE).select(
        "codeforces_handle, cses_user, cses_code"
    ).execute()

    df = pd.DataFrame(rows.data).rename(
        columns={"codeforces_handle": "codeforces"}
    )

    for col in ("codeforces", "cses_user", "cses_code"):
        if col not in df.columns:
            df[col] = pd.NA

    return df


# -----------------------------------
# TELEGRAM USERS (bot)
# -----------------------------------

def load_telegram_users() -> dict:
    """{chat_id: {handle, timezone, reminders, last_sent}} — mesmo
    formato que o antigo data/telegram_users.json tinha."""

    res = sb.table(TELEGRAM_USERS_TABLE).select(
        "chat_id, handle, timezone, reminders, last_sent"
    ).execute()

    return {
        row["chat_id"]: {
            "handle": row.get("handle"),
            "timezone": row.get("timezone"),
            "reminders": row.get("reminders") or [],
            "last_sent": row.get("last_sent") or {},
        }
        for row in (res.data or [])
    }


def save_telegram_user(chat_id, data, default_timezone):
    """Upsert de um usuário do bot. `updated_at` só tem default no
    insert, então é enviado explicitamente."""

    row = {
        "chat_id": chat_id,
        "handle": data.get("handle"),
        "timezone": data.get("timezone") or default_timezone,
        "reminders": data.get("reminders") or [],
        "last_sent": data.get("last_sent") or {},
        "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }

    sb.table(TELEGRAM_USERS_TABLE).upsert(
        row, on_conflict="chat_id"
    ).execute()


# -----------------------------------
# SUBMISSIONS (tabela unificada CF + CSES)
# -----------------------------------

def _select_all(table, handles, extra_filters=None, page_size=PAGE_SIZE):
    """Pagina a busca — o Supabase limita ~1000 linhas por resposta e
    o histórico do grupo todo passa disso rápido.

    IMPORTANTE: o .order(...) abaixo não é sobre ordenar pra exibição —
    é OBRIGATÓRIO pra paginação com .range() ser estável. Sem uma
    ordenação explícita e determinística, o Postgres não garante que
    a "página 2" comece exatamente onde a "página 1" parou; o plano de
    execução pode variar entre uma chamada e outra, fazendo linhas
    sumirem (ou duplicarem) bem na fronteira entre páginas. Isso é
    ainda mais provável com muitas linhas/handles (várias páginas)."""

    all_rows = []
    start = 0

    while True:

        q = (
            sb.table(table)
            .select("*")
            .in_("handle", handles)
            .order("handle")
            .order("source")
            .order("source_id")
        )

        if extra_filters:
            for col, val in extra_filters.items():
                q = q.eq(col, val)

        res = q.range(start, start + page_size - 1).execute()

        rows = res.data or []
        all_rows.extend(rows)

        if len(rows) < page_size:
            break

        start += page_size

    return all_rows


def load_submissions(handles, source=None) -> pd.DataFrame:
    """
    Lê o histórico de submissões do Supabase, já no formato que o
    dashboard espera (colunas 'problem.contestId', 'problem.index',
    etc). Sem `source`, devolve CF + CSES juntos numa tabela só — não
    precisa mais de concat manual entre as duas fontes.

    Passe source="CF" ou source="CSES" pra filtrar só uma fonte.
    """

    if not handles:
        return pd.DataFrame()

    extra_filters = {"source": source} if source else None

    rows = _select_all(SUBMISSIONS_TABLE, handles, extra_filters=extra_filters)

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df = df.rename(columns={
        "contest_id": "problem.contestId",
        "problem_index": "problem.index",
        "problem_name": "problem.name",
        "problem_rating": "problem.rating",
        "problem_tags": "problem.tags",
        "submitted_at": "date",
    })

    df["date"] = pd.to_datetime(df["date"], utc=True)

    return df


def save_submissions(rows):
    """Upsert de uma lista de dicts no formato da tabela `submissions`.
    (source, source_id, handle) é a chave primária — reenviar uma
    submissão que já existe só atualiza a linha, nunca duplica.

    IMPORTANTE: o `handle` faz parte da chave (não só source+source_id)
    porque em contests de time/gym uma mesma submissão (mesmo `id`
    global do Codeforces) aparece no histórico de VÁRIOS membros do
    time ao mesmo tempo. Sem o handle na chave, o upsert de um membro
    sobrescrevia a linha do outro — cada sincronização "roubava" a
    submissão de volta pra quem rodou por último no loop."""

    if not rows:
        return

    result = (
        sb.table(SUBMISSIONS_TABLE)
        .upsert(rows, on_conflict="source,source_id,handle")
        .execute()
    )

    saved = len(result.data) if getattr(result, "data", None) else 0

    if saved != len(rows):
        print(
            f"[db] AVISO: upsert enviou {len(rows)} linhas mas a resposta "
            f"do Supabase confirmou apenas {saved}. Isso indica que a "
            f"gravação NÃO está sendo persistida como esperado."
        )


def get_last_cf_submission_id(handle):
    """Maior `cf_id` já salvo para esse handle (fonte CF), ou None se
    o handle ainda não tem nada salvo. Usado pelo codeforces.py pra
    decidir se precisa chamar a API de novo.

    IMPORTANTE: o PostgREST às vezes devolve colunas bigint como
    string no JSON (pra evitar perda de precisão em números grandes).
    Por isso o cast explícito para int aqui — sem ele, comparar esse
    valor com o id (int puro) vindo da API do CF nunca dava match,
    fazendo o código achar "tem submissão nova" em toda sincronização,
    mesmo sem nada de novo."""

    res = (
        sb.table(SUBMISSIONS_TABLE)
        .select("cf_id")
        .eq("handle", handle)
        .eq("source", "CF")
        .order("cf_id", desc=True)
        .limit(1)
        .execute()
    )

    if not res.data:
        return None

    value = res.data[0].get("cf_id")

    if value is None:
        return None

    return int(value)


def get_saved_cses_problems(handles):
    """{handle: {problem_index (int)}} dos problemas do CSES já salvos,
    para vários handles numa consulta só (paginada). Usado pelo
    cses.sync pra descobrir o que ainda não está no banco."""

    result = {h: set() for h in handles}

    if not handles:
        return result

    start = 0

    while True:

        res = (
            sb.table(SUBMISSIONS_TABLE)
            .select("handle, problem_index")
            .in_("handle", list(handles))
            .eq("source", "CSES")
            .order("handle")
            .order("problem_index")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )

        rows = res.data or []

        for r in rows:
            if r.get("problem_index") is not None:
                result.setdefault(r["handle"], set()).add(int(r["problem_index"]))

        if len(rows) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    return result
