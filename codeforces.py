import streamlit as st
import pandas as pd
import requests
import time
import hashlib
import json
import os
from datetime import datetime, timezone

import db

_raw_cf_users = os.environ.get("CODEFORCES_USERS")

if not _raw_cf_users:
    try:
        _raw_cf_users = st.secrets.get("CODEFORCES_USERS")
    except Exception:
        pass

if not _raw_cf_users:
    raise RuntimeError("CODEFORCES_USERS não encontrado.")

cf_users = json.loads(_raw_cf_users)

# -----------------------------------
# MAPA DE CREDENCIAIS
# -----------------------------------

CF_CREDENTIALS = {
    user["handle"]: {
        "api_key": user["api_key"],
        "api_secret": user["api_secret"],
    }
    for user in cf_users
    if "api_key" in user
    and "api_secret" in user
}

# usuário fallback
DEFAULT_CF_USER = "anacarlaaf"

if DEFAULT_CF_USER not in CF_CREDENTIALS:
    raise RuntimeError(
        f"{DEFAULT_CF_USER} não possui credenciais."
    )

BASE = "https://codeforces.com/api/"

# -----------------------------------
# CONTEST SIZE
# -----------------------------------

@st.cache_data(ttl=3600)
def get_contest_size(contest_id):

    url = (
        "https://codeforces.com/api/"
        "contest.standings"
    )

    params = {
        "contestId": contest_id,
        "from": 1,
        "count": 1
    }

    r = requests.get(
        url,
        params=params
    ).json()

    problems = r["result"]["problems"]

    return len(problems)

# -----------------------------------
# REQUEST CODEFORCES
# -----------------------------------

def cf_request(
    method,
    handle,
    params=None,
):

    if params is None:
        params = {}

    # -----------------------------------
    # pega credenciais do usuário
    # -----------------------------------

    creds = CF_CREDENTIALS.get(handle)

    # fallback
    if creds is None:

        creds = CF_CREDENTIALS[
            DEFAULT_CF_USER
        ]

    api_key = creds["api_key"]
    api_secret = creds["api_secret"]

    # -----------------------------------
    # assinatura
    # -----------------------------------

    rand = "123456"

    now = int(time.time())

    params["apiKey"] = api_key
    params["time"] = now

    sorted_params = "&".join(
        f"{k}={params[k]}"
        for k in sorted(params)
    )

    to_hash = (
        f"{rand}/{method}?"
        f"{sorted_params}"
        f"#{api_secret}"
    )

    sha = hashlib.sha512(
        to_hash.encode()
    ).hexdigest()

    params["apiSig"] = rand + sha

    # -----------------------------------
    # request
    # -----------------------------------
    try:

        r = requests.get(
            BASE + method,
            params=params,
            timeout=20,
        )

        data = r.json()

    except Exception as e:

        print(
            f"[REQUEST ERROR] "
            f"{handle} | {method} | {e}"
        )

        return []

    if data["status"] != "OK":

        print(
            f"[CF ERROR] "
            f"{handle}: "
            f"{data.get('comment')}"
        )

        return []

    return data["result"]

# -----------------------------------
# PERSISTÊNCIA DE SUBMISSÕES (tabela unificada 'submissions' no
# Supabase — ver db.py)
# -----------------------------------

def _cf_submission_to_row(handle, s):
    """Converte uma submissão da API do CF para o formato da tabela
    unificada `submissions`."""

    problem = s.get("problem", {}) or {}

    sub_id = s.get("id")

    creation_ts = s.get("creationTimeSeconds")
    submitted_at = (
        datetime.fromtimestamp(creation_ts, tz=timezone.utc).isoformat()
        if creation_ts is not None
        else None
    )

    contest_id = problem.get("contestId")

    return {
        "source": "CF",
        "source_id": str(sub_id),
        "cf_id": sub_id,  # numérico — usado pra achar "a última submissão" sem cast de texto
        "handle": handle,
        "contest_id": str(contest_id) if contest_id is not None else None,
        "problem_index": problem.get("index"),
        "problem_rating": problem.get("rating"),
        "problem_tags": problem.get("tags", []),
        "verdict": s.get("verdict"),
        "submitted_at": submitted_at,
    }


def _fetch_cf_submissions_until(handle, stop_at_id=None, batch_size=100, max_batches=50):
    """
    Baixa submissões da API em blocos de `batch_size`, começando do
    mais recente (from=1) e paginando pra trás, até encontrar
    `stop_at_id` (a última submissão que já temos salva) ou esgotar o
    histórico do usuário.

    Isso substitui o "baixa só as últimas N" — que deixava buraco no
    histórico se a pessoa fizesse mais submissões que N entre uma
    sincronização e outra (ex: uma contest de gym gerando 200+
    submissões de uma vez).
    """

    collected = []
    start = 1

    for _ in range(max_batches):

        batch = cf_request(
            "user.status",
            handle=handle,
            params={"handle": handle, "from": start, "count": batch_size},
        )

        if not batch:
            break

        collected.extend(batch)

        batch_ids = {s.get("id") for s in batch}

        if stop_at_id is not None and stop_at_id in batch_ids:
            # achamos a última que já tínhamos salva — não precisa
            # continuar paginando, o resto já está no banco.
            break

        if len(batch) < batch_size:
            # acabou o histórico do usuário (menos submissões que um
            # bloco cheio)
            break

        start += batch_size

        # espaça as páginas entre si, evita rate limit da API do CF
        time.sleep(1)

    return collected


def sync_cf_submissions(
    handles,
    backfill_count=2000,
    delta_batch_size=100,
    max_delta_batches=50,
):
    """
    Para cada handle, decide se precisa chamar a API pesada do CF:

      1. Pega o último `cf_id` salvo no banco (None se handle é novo).
      2. Pergunta pra API só a submissão MAIS RECENTE (count=1) —
         chamada leve, sempre feita.
      3. Se o id mais recente da API já for o mesmo do banco, não há
         nada novo — pula, sem baixar mais nada.
      4. Caso contrário, pagina pra trás em blocos de
         `delta_batch_size` (ver _fetch_cf_submissions_until) até
         encontrar a última submissão já conhecida — cobre qualquer
         quantidade de submissões novas, não só as últimas 100.
         Na primeira carga (handle nunca sincronizado), pagina até
         cobrir ~`backfill_count` submissões (não há "última
         conhecida" pra procurar).
      5. Salva (upsert) o que baixou no Supabase.
    """

    for h in handles:

        last_id_db = db.get_last_cf_submission_id(h)

        latest = cf_request(
            "user.status",
            handle=h,
            params={"handle": h, "count": 1},
        )

        if not latest:
            print(f"[CF] {h}: sem submissões na API (ou erro/handle inválido).")
            time.sleep(1)
            continue

        latest_id = latest[0].get("id")
        latest_id = int(latest_id) if latest_id is not None else None

        if last_id_db is not None and latest_id == last_id_db:
            print(f"[CF] {h}: nenhuma submissão nova (última já é {latest_id}).")
            time.sleep(1)
            continue

        is_first_load = last_id_db is None

        if is_first_load:
            print(f"[CF] {h}: primeira carga — paginando histórico completo.")
            max_batches = max(1, -(-backfill_count // delta_batch_size))  # ceil
            subs = _fetch_cf_submissions_until(
                h,
                stop_at_id=None,
                batch_size=delta_batch_size,
                max_batches=max_batches,
            )
        else:
            print(
                f"[CF] {h}: novas submissões detectadas "
                f"(banco tinha até id={last_id_db}, API tem até id={latest_id}) "
                f"— paginando até cobrir tudo."
            )
            subs = _fetch_cf_submissions_until(
                h,
                stop_at_id=last_id_db,
                batch_size=delta_batch_size,
                max_batches=max_delta_batches,
            )

        rows = [
            _cf_submission_to_row(h, s)
            for s in subs
            if s.get("id") is not None
        ]

        db.save_submissions(rows)

        print(f"[CF] {h}: {len(rows)} submissões salvas/atualizadas no banco.")

        # evita rate limit da API do CF
        time.sleep(2)

# -----------------------------------
# FETCH (bate na API do Codeforces só pelo que for necessário)
# -----------------------------------

def fetch_cf_data(handles, submissions_count=2000):
    """
    Sincroniza as submissões do CF com o banco (só baixa da API o que
    for novo — ver sync_cf_submissions) e devolve o histórico de
    submissões JÁ UNIFICADO com o CSES (mesma tabela, ver db.py),
    além de rating/info do usuário, buscados sempre ao vivo por serem
    chamadas leves.
    """

    sync_cf_submissions(handles, backfill_count=submissions_count)

    subs_df = db.load_submissions(handles)  # CF + CSES juntos

    all_rating = []
    users = []

    for h in handles:

        print(f"[CF] Buscando info/rating de {h}...", flush=True)

        info_result = cf_request(
            "user.info",
            handle=h,
            params={"handles": h},
        )

        if not info_result:

            print(
                f"[WARNING] Sem info para {h} "
                f"(handle inválido, sem credenciais válidas, ou erro da API — "
                f"veja a mensagem [CF ERROR] acima)"
            )

            continue

        users.append(info_result[0])

        rating = cf_request(
            "user.rating",
            handle=h,
            params={"handle": h},
        )

        for r in rating:
            r["handle"] = h

        all_rating.extend(rating)

        time.sleep(1)

    rating_df = pd.json_normalize(all_rating)
    users_df = pd.json_normalize(users)

    return subs_df, rating_df, users_df

# -----------------------------------
# LOAD (o banco já funciona como cache persistente; só toca a API do
# CF quando há submissão nova)
# -----------------------------------

@st.cache_data(ttl=300)
def load_data(
    handles=None,
    submissions_count=2000,
):
    """
    Sincroniza e carrega os dados do Codeforces + CSES. As submissões
    (subs_df) já vêm unificadas das duas fontes, lidas do Supabase.
    Rating e info do usuário continuam sendo buscados ao vivo a cada
    chamada, por serem requisições leves.

    O `@st.cache_data(ttl=300)` aqui é só um cache em memória de curta
    duração pra evitar bater no banco/API repetidas vezes a cada
    rerender do Streamlit dentro da mesma sessão — expira em 5 min.

    Para forçar uma sincronização nova antes do TTL expirar, chame
    `st.cache_data.clear()` (ex: botão "Atualizar dados" do dashboard).
    """

    if not handles:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    subs_df, rating_df, users_df = fetch_cf_data(
        handles,
        submissions_count=submissions_count,
    )

    print(
        f"[CF] Dados prontos: "
        f"{len(subs_df)} submissões (CF+CSES, banco), "
        f"{len(rating_df)} registros de rating, "
        f"{len(users_df)} usuários."
    )

    return subs_df, rating_df, users_df

# -----------------------------------
# COLORS
# -----------------------------------

def cf_rank_color(rank):

    colors = {
        "newbie": "#808080",
        "pupil": "#008000",
        "specialist": "#03A89E",
        "expert": "#0000FF",
        "candidate master": "#AA00AA",
        "master": "#FF8C00",
        "international master": "#FF8C00",
        "grandmaster": "#FF0000",
        "international grandmaster": "#CC0000",
        "legendary grandmaster": "#AA0000",
    }

    if isinstance(rank, str):

        return (
            f"color: "
            f"{colors.get(rank.lower(), 'black')}; "
            f"font-weight: bold;"
        )

    return ""

# -----------------------------------
# PROGRESS BARS
# -----------------------------------

def progress_bar_scaled(
    done,
    total,
    size=7,
):

    if total == 0:
        return ""

    ratio = min(done / total, 1)

    filled = int(ratio * size)

    return (
        "🟢" * filled
        + "🔴" * (size - filled)
    )

def progress_bar(done, total):

    done = min(done, total)

    return (
        "🟩" * done
        + "🟥" * (total - done)
    )