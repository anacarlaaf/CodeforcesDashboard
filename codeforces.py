import streamlit as st
import pandas as pd
import requests
import time
import hashlib
import json
import os

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

def fetch_cf_data(handles, submissions_count=2000):
    """
    Busca dados brutos da API do Codeforces para os handles informados.
    Não há persistência em parquet — cada chamada bate direto na API do
    Codeforces e retorna os dados atuais, sem comparar com nenhum
    estado salvo anteriormente.
    """

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
        # SUBMISSIONS (sempre baixa tudo, direto da API)
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
# LOAD (sempre busca ao vivo na API — sem persistência em parquet)
# -----------------------------------

@st.cache_data(ttl=300)
def load_data(
    handles=None,
    submissions_count=2000,
):
    """
    Busca os dados do Codeforces direto na API, sem nenhuma persistência
    em disco (sem parquet). O `@st.cache_data(ttl=300)` é só um cache em
    memória de curta duração para evitar bater na API repetidas vezes a
    cada rerender do Streamlit dentro da mesma sessão — não é um cache
    em arquivo, e expira sozinho em 5 minutos.

    Para forçar uma busca nova antes do TTL expirar, chame
    `st.cache_data.clear()` (ex: botão "Atualizar dados" do dashboard).
    """

    if not handles:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    subs_df, rating_df, users_df = fetch_cf_data(
        handles,
        submissions_count=submissions_count,
    )

    print(
        f"[CF] Dados buscados via API: "
        f"{len(subs_df)} submissões, "
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
        "🟩" * filled
        + "🟥" * (size - filled)
    )

def progress_bar(done, total):

    done = min(done, total)

    return (
        "🟩" * done
        + "🟥" * (total - done)
    )