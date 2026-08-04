import streamlit as st
import pandas as pd
import requests
import time
import hashlib
import json
import os
from pathlib import Path

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
# FETCH (bate na API do Codeforces)
# -----------------------------------

def fetch_cf_data(handles, submissions_count=2000, last_known_sub_id=None):
    """
    Busca dados brutos da API do Codeforces para os handles informados.
    Não usa cache do Streamlit — é chamada por `update()`, que roda
    externamente (ex: GitHub Action) ou sob demanda.

    `last_known_sub_id`: dict {handle: id da submissão mais recente já
    salva no parquet}. Se informado, antes de baixar tudo o código
    checa apenas a submissão mais recente na API (1 chamada leve); se
    o id bater com o já salvo, pula o download completo daquele handle.
    """

    if last_known_sub_id is None:
        last_known_sub_id = {}

    all_subs = []
    all_rating = []
    users = []

    for h in handles:

        # -------------------------
        # USER INFO
        # -------------------------

        print(f"[CF] Buscando {h}...", flush=True)

        info_result = cf_request(
            "user.info",
            handle=h,
            params={
                "handles": h
            }
        )

        if not info_result:

            print(
                f"[WARNING] Sem info para {h} "
                f"(handle inválido, sem credenciais válidas, ou erro da API — "
                f"veja a mensagem [CF ERROR] acima)"
            )

            continue

        users.append(info_result[0])

        # -------------------------
        # CHECA SE HÁ SUBMISSÃO NOVA
        # (1 chamada leve, count=1, antes de baixar tudo)
        # -------------------------

        latest = cf_request(
            "user.status",
            handle=h,
            params={
                "handle": h,
                "count": 1,
            }
        )

        latest_id = latest[0]["id"] if latest else None
        known_id = last_known_sub_id.get(h)

        if latest_id is not None and latest_id == known_id:

            print(
                f"[CF] {h}: submissão mais recente já salva (id={latest_id}). "
                f"Pulando download completo."
            )

        else:

            # -------------------------
            # SUBMISSIONS (download completo)
            # -------------------------

            subs = cf_request(
                "user.status",
                handle=h,
                params={
                    "handle": h,
                    "count": submissions_count
                }
            )

            for s in subs:
                s["handle"] = h

            all_subs.extend(subs)

            print(f"[CF] {h}: {len(subs)} submissões baixadas.")

        # -------------------------
        # RATING
        # -------------------------

        rating = cf_request(
            "user.rating",
            handle=h,
            params={
                "handle": h
            }
        )

        for r in rating:
            r["handle"] = h

        all_rating.extend(rating)

        # evita rate limit
        time.sleep(0.2)

    subs_df = pd.json_normalize(all_subs)
    rating_df = pd.json_normalize(all_rating)
    users_df = pd.json_normalize(users)

    return subs_df, rating_df, users_df

# -----------------------------------
# UPDATE (fetch + merge + salva em parquet)
# -----------------------------------

def update(
    users_csv="data/users.csv",
    subs_parquet="data/cf_submissions.parquet",
    rating_parquet="data/cf_rating.parquet",
    users_parquet="data/cf_users.parquet",
    submissions_count=2000,
):
    """
    Busca dados novos na API do Codeforces e atualiza os arquivos
    parquet locais (mesmo padrão usado para o CSES em cses.py::update).

    - cf_submissions.parquet: histórico de submissões (deduplicado por handle+id)
    - cf_rating.parquet: histórico de mudanças de rating (deduplicado por handle+contestId)
    - cf_users.parquet: snapshot mais recente de cada usuário (rating atual, rank, etc)
    """

    users_df_csv = pd.read_csv(users_csv)

    handles = (
        users_df_csv["codeforces"]
        .dropna()
        .astype(str)
        .str.strip()
    )
    handles = handles[handles != ""].tolist()

    print(f"[CF] {len(handles)} handles carregados de {users_csv}: {handles}")

    if not handles:
        print(f"[CF] Nenhum handle encontrado na coluna 'codeforces' de {users_csv}. Abortando.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # -------------------------
    # última submissão já salva por handle
    # (usada pra decidir se pula o download completo)
    # -------------------------

    last_known_sub_id = {}

    if Path(subs_parquet).exists():

        existing_subs = pd.read_parquet(subs_parquet)

        if not existing_subs.empty:

            idx_mais_recente = (
                existing_subs
                .groupby("handle")["creationTimeSeconds"]
                .idxmax()
            )

            last_known_sub_id = (
                existing_subs
                .loc[idx_mais_recente]
                .set_index("handle")["id"]
                .to_dict()
            )

    subs_df, rating_df, users_df = fetch_cf_data(
        handles,
        submissions_count=submissions_count,
        last_known_sub_id=last_known_sub_id,
    )

    print(
        f"[CF] Resultado do fetch: "
        f"{len(subs_df)} submissões, "
        f"{len(rating_df)} registros de rating, "
        f"{len(users_df)} usuários."
    )

    # -------------------------
    # SUBMISSÕES
    # -------------------------

    if not subs_df.empty:

        Path(subs_parquet).parent.mkdir(parents=True, exist_ok=True)

        if Path(subs_parquet).exists():
            old = pd.read_parquet(subs_parquet)
            combined = pd.concat([old, subs_df], ignore_index=True, sort=False)
        else:
            combined = subs_df

        combined = combined.drop_duplicates(
            subset=["handle", "id"],
            keep="last",
        )

        combined.to_parquet(subs_parquet, index=False)

        print(
            f"[CF] {len(combined)} submissões salvas em {subs_parquet} "
            f"(+{len(subs_df)} buscadas nesta execução)"
        )

    else:
        print("[CF] Nenhuma submissão retornada pela API.")

    # -------------------------
    # RATING
    # -------------------------

    if not rating_df.empty:

        Path(rating_parquet).parent.mkdir(parents=True, exist_ok=True)

        if Path(rating_parquet).exists():
            old = pd.read_parquet(rating_parquet)
            combined_rating = pd.concat([old, rating_df], ignore_index=True, sort=False)
        else:
            combined_rating = rating_df

        combined_rating = combined_rating.drop_duplicates(
            subset=["handle", "contestId"],
            keep="last",
        )

        combined_rating.to_parquet(rating_parquet, index=False)

        print(f"[CF] {len(combined_rating)} registros de rating salvos em {rating_parquet}")

    else:
        print("[CF] Nenhum registro de rating retornado pela API.")

    # -------------------------
    # USERS (snapshot mais recente)
    # -------------------------

    if not users_df.empty:

        Path(users_parquet).parent.mkdir(parents=True, exist_ok=True)

        users_df.to_parquet(users_parquet, index=False)

        print(f"[CF] {len(users_df)} usuários salvos em {users_parquet}")

    else:
        print("[CF] Nenhum usuário retornado pela API.")

    return subs_df, rating_df, users_df

# -----------------------------------
# LOAD (lê do parquet, rápido, cacheado)
# -----------------------------------

@st.cache_data(ttl=300)
def load_data(
    handles=None,
    subs_parquet="data/cf_submissions.parquet",
    rating_parquet="data/cf_rating.parquet",
    users_parquet="data/cf_users.parquet",
):
    """
    Carrega os dados do Codeforces a partir dos arquivos parquet
    (que são mantidos atualizados por `update()`, chamada externamente
    via GitHub Action, igual ao fluxo do CSES).

    Não bate na API do Codeforces — se os parquets ainda não existirem
    (primeira execução), retorna DataFrames vazios.
    """

    subs_df = (
        pd.read_parquet(subs_parquet)
        if Path(subs_parquet).exists()
        else pd.DataFrame()
    )

    rating_df = (
        pd.read_parquet(rating_parquet)
        if Path(rating_parquet).exists()
        else pd.DataFrame()
    )

    users_df = (
        pd.read_parquet(users_parquet)
        if Path(users_parquet).exists()
        else pd.DataFrame()
    )

    if handles:

        if not subs_df.empty:
            subs_df = subs_df[subs_df["handle"].isin(handles)].reset_index(drop=True)

        if not rating_df.empty:
            rating_df = rating_df[rating_df["handle"].isin(handles)].reset_index(drop=True)

        if not users_df.empty:
            users_df = users_df[users_df["handle"].isin(handles)].reset_index(drop=True)

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
        "🟩" * filled
        + "🟥" * (size - filled)
    )

def progress_bar(done, total):

    done = min(done, total)

    return (
        "🟩" * done
        + "🟥" * (total - done)
    )