import requests
from bs4 import BeautifulSoup
from pathlib import Path
import streamlit as st
import pandas as pd
import time
import json
import os

import db

BASE_URL = "https://cses.fi"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

_raw = os.environ.get("CSES_ACCOUNT") or os.environ.get("CSES_ACCOUNTS")

if not _raw:
    try:
        _raw = st.secrets.get("CSES_ACCOUNT") or st.secrets.get("CSES_ACCOUNTS")
    except Exception as e:
        print("Erro ao carregar CSES_ACCOUNT/CSES_ACCOUNTS:", e)

if not _raw:
    raise RuntimeError(
        "CSES_ACCOUNT (ou CSES_ACCOUNTS) não encontrado. "
        "Verifique a variável de ambiente ou .streamlit/secrets.toml."
    )

try:
    _parsed = json.loads(_raw)
except json.JSONDecodeError as e:
    raise RuntimeError(
        f"CSES_ACCOUNT/CSES_ACCOUNTS contém JSON inválido: {e}"
    )

# -----------------------------------
# CONTA MESTRE ÚNICA
# -----------------------------------
# Uma única conta ("mestre") logada consulta os dados de TODOS os
# usuários — o CSES aceita `user=<nick>` como filtro na URL, não
# precisa estar logado como a própria pessoa pra ver essas páginas.
#
# Formatos aceitos para CSES_ACCOUNT / CSES_ACCOUNTS:
#   {"user": "minha_conta", "password": "minha_senha"}
#   [{"user": "minha_conta", "password": "minha_senha"}, ...]  (usa o 1º item)

if isinstance(_parsed, list):
    if not _parsed:
        raise RuntimeError("CSES_ACCOUNT/CSES_ACCOUNTS está vazio.")
    master_account = _parsed[0]
elif isinstance(_parsed, dict):
    master_account = _parsed
else:
    raise RuntimeError(
        "CSES_ACCOUNT/CSES_ACCOUNTS em formato inesperado "
        "(esperado objeto ou lista de objetos)."
    )

try:
    MASTER_USER = master_account["user"]
    MASTER_PASSWORD = master_account["password"]
except KeyError as e:
    raise RuntimeError(
        f"Conta mestre do CSES incompleta, faltando a chave {e}."
    )


def login_cses(user: str, password: str):

    session = requests.Session()

    session.headers.update(HEADERS)

    r = session.get(
        f"{BASE_URL}/login",
        timeout=20,
    )

    if r.status_code != 200:
        raise RuntimeError(
            f"Erro ao abrir login: {r.status_code}"
        )

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    csrf_input = soup.find(
        "input",
        {"name": "csrf_token"}
    )

    if csrf_input is None:
        raise RuntimeError(
            "CSRF token não encontrado"
        )

    csrf = csrf_input["value"]

    payload = {
        "csrf_token": csrf,
        "nick": user,
        "pass": password,
    }

    login = session.post(
        f"{BASE_URL}/login",
        data=payload,
        headers={
            "Referer": f"{BASE_URL}/login"
        },
        timeout=20,
    )

    if "/logout" not in login.text:

        raise RuntimeError(
            f"Falha no login: {user}"
        )

    print(f"✅ Login realizado: {user}")

    return session

@st.cache_resource
def get_cses_session():
    """
    Loga UMA ÚNICA VEZ com a conta mestre e retorna essa sessão.

    Essa mesma sessão é reaproveitada para consultar os dados de
    TODOS os usuários (via `user=<nick>` na URL), então não é mais
    necessário guardar usuário/senha de cada pessoa.
    """

    try:

        session = login_cses(
            user=MASTER_USER,
            password=MASTER_PASSWORD,
        )

    except Exception as e:

        raise RuntimeError(
            f"Erro ao logar com a conta mestre ({MASTER_USER}): {e}"
        )

    print(
        f"\n✅ Sessão única autenticada com {MASTER_USER}."
    )

    return session

def update_cses_stats(
    html: str,
    csv_file: str = "data/cses_stats.csv"
):
    """
    Extrai user + solved tasks e atualiza/cria um CSV.

    Função independente do fluxo de sincronização de submissões
    abaixo — usada apenas pra snapshot do ranking geral do CSES, não
    mexe na tabela `submissions`.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    rows = []

    tables = soup.find_all("table")

    target_table = None

    for tbl in tables:

        headers = [
            th.get_text(
                strip=True
            ).lower()
            for th in tbl.find_all("th")
        ]

        if (
            "user" in headers
            and "solved tasks" in headers
        ):
            target_table = tbl
            break

    if target_table is None:
        raise RuntimeError(
            "Tabela de ranking não encontrada."
        )

    trs = target_table.find_all("tr")

    for tr in trs[1:]:

        tds = tr.find_all("td")

        if len(tds) < 3:
            continue

        user_link = tds[1].find("a")

        if user_link is None:
            continue

        user = user_link.get_text(
            strip=True
        )

        solved = int(
            tds[2].get_text(
                strip=True
            )
        )

        rows.append(
            {
                "user": user,
                "solved_tasks": solved
            }
        )

    new_df = pd.DataFrame(rows)

    path = Path(csv_file)

    if not path.exists():

        path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        new_df.to_csv(
            path,
            index=False
        )

        print(
            f"Criado {csv_file}"
        )

        return new_df

    old_df = pd.read_csv(path)

    merged = old_df.set_index(
        "user"
    )

    for _, row in new_df.iterrows():

        merged.loc[
            row["user"],
            "solved_tasks"
        ] = row["solved_tasks"]

    merged.reset_index().to_csv(
        path,
        index=False
    )

    print(
        f"Atualizado {csv_file}"
    )

    return merged.reset_index()


def get_solved_tasks_by_user(sleep_time: float = 0.1, **_ignored):
    """
    Retorna {cses_user: [problem_codes_resolvidos]} pra todos os
    membros com cses_user cadastrado. `_ignored` absorve kwargs
    antigos (ex: users_csv) por compatibilidade, caso algum script
    externo ainda passe esse argumento.
    """

    users_df = db.load_members_df()

    users_df = (
        users_df[
            users_df["cses_user"]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
        ]
        .reset_index(drop=True)
    )

    # sessão única (conta mestre), usada para consultar todos os usuários
    session = get_cses_session()

    result = {}

    total = len(users_df)

    for idx, row in users_df.iterrows():

        if (
            pd.isna(row["cses_code"])
            or pd.isna(row["cses_user"])
        ):
            continue

        cses_user = row["cses_user"]
        cses_code = int(row["cses_code"])

        print(
            f"\n[{idx+1}/{total}] USER: {cses_user}"
        )

        url = (
            f"{BASE_URL}/problemset/user/"
            f"{cses_code}/"
        )

        try:

            r = session.get(
                url,
                timeout=20,
            )

            if r.status_code != 200:

                print(
                    "HTTP ERROR:",
                    r.status_code
                )

                result[cses_user] = []

                continue

            soup = BeautifulSoup(
                r.text,
                "html.parser"
            )

            solved = set()

            task_links = soup.select(
                "a.task-score.icon.full"
            )

            for link in task_links:

                href = link.get("href", "")

                parts = href.strip("/").split("/")

                if (
                    len(parts) >= 3
                    and parts[0] == "problemset"
                    and parts[1] == "task"
                ):

                    try:

                        solved.add(
                            int(parts[2])
                        )

                    except ValueError:
                        pass

            solved = sorted(solved)

            result[cses_user] = solved

            print(
                f"Solved: {len(solved)}"
            )

        except Exception as e:

            print(
                f"ERROR {cses_user}: {e}"
            )

            result[cses_user] = []

        time.sleep(sleep_time)

    return result

def get_last_accepted_for_codes(
    user: str,
    codes: list[int],
    problems_csv: str = "data/cses_problems.csv",
    sleep_time: float = 0.2,
    **_ignored,
):
    """
    Para cada código em `codes`, consulta:

    https://cses.fi/problemset/queue/{code}/1/
        ?lang=0&status=2
        &user={user}
        &by=0
        &order=1

    e extrai a data/hora do accept e a categoria do problema.

    Retorna DataFrame(user, problem_code, time, category).

    `_ignored` absorve kwargs antigos (ex: users_csv) por
    compatibilidade.
    """

    problems_df = pd.read_csv(problems_csv)

    category_map = dict(
        zip(
            problems_df["task_id"],
            problems_df["category"],
        )
    )

    # sessão única (conta mestre), usada para consultar todos os usuários
    session = get_cses_session()

    rows = []

    total = len(codes)

    for idx, code in enumerate(codes, start=1):

        print(
            f"[{idx}/{total}] "
            f"{user} - {code}"
        )

        url = (
            f"{BASE_URL}/problemset/queue/"
            f"{code}/1/"
            f"?lang=0"
            f"&status=2"
            f"&user={user}"
            f"&by=0"
            f"&order=1"
        )

        try:

            r = session.get(
                url,
                timeout=20,
            )

            if r.status_code != 200:

                print(
                    "HTTP ERROR:",
                    r.status_code,
                )

                continue

            soup = BeautifulSoup(
                r.text,
                "html.parser",
            )

            table = soup.find("table")

            if table is None:
                continue

            trs = table.find_all("tr")

            accepted_time = None

            for tr in trs:

                tds = tr.find_all("td")

                if len(tds) < 7:
                    continue

                # coluna:
                # 2024-04-14 20:45:03
                accepted_time = (
                    tds[0]
                    .get_text(
                        " ",
                        strip=True,
                    )
                    .replace(
                        "\xa0",
                        " ",
                    )
                )

                break

            if accepted_time is None:
                continue

            rows.append(
                {
                    "user": user,
                    "problem_code": code,
                    "time": accepted_time,
                    "category": category_map.get(
                        code
                    ),
                }
            )

        except Exception as e:

            print(
                f"ERROR {user} {code}: {e}"
            )

        time.sleep(
            sleep_time
        )

    df = pd.DataFrame(rows)

    if not df.empty:

        df["time"] = pd.to_datetime(
            df["time"]
        )

        df = (
            df
            .sort_values("time")
            .reset_index(drop=True)
        )

    return df

def get_new_problem_codes(**_ignored):
    """
    Retorna apenas os problemas ainda não presentes na tabela
    `submissions` (source='CSES') — substitui o diff que antes era
    feito contra cses_all.parquet.

    Retorno:
        { cses_user: [problem_codes_novos] }
    """

    solved_tasks = get_solved_tasks_by_user()

    members_df = db.load_members_df()
    user_to_handle = dict(zip(members_df["cses_user"], members_df["codeforces"]))

    result = {}

    for user, current_codes in solved_tasks.items():

        current_codes = set(current_codes)

        handle = user_to_handle.get(user)

        if not handle:
            print(
                f"[CSES] {user}: sem handle de Codeforces vinculado "
                f"em 'members', pulando."
            )
            result[user] = []
            continue

        saved_codes = db.get_saved_problem_indices(handle, source="CSES")

        new_codes = sorted(current_codes - saved_codes)

        print(
            f"{user}: "
            f"{len(saved_codes)} salvos | "
            f"{len(current_codes)} atuais | "
            f"{len(new_codes)} novos"
        )

        result[user] = new_codes

    return result


def _submitted_at_iso(time_value):
    ts = pd.Timestamp(time_value)

    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")

    return ts.isoformat()


def update(problems_csv: str = "data/cses_problems.csv", **_ignored):
    """
    Busca só os problemas novos (get_new_problem_codes) e grava na
    tabela unificada `submissions` (source='CSES').

    `_ignored` absorve kwargs antigos (ex: users_csv, cses_all_csv) —
    o parquet não é mais usado, tudo vai direto pro Supabase.
    """

    new_problems = get_new_problem_codes()

    members_df = db.load_members_df()
    user_to_handle = dict(zip(members_df["cses_user"], members_df["codeforces"]))

    rows_to_save = []

    for user, codes in new_problems.items():

        if not codes:
            continue

        handle = user_to_handle.get(user)

        if not handle:
            continue

        print(
            f"{user}: "
            f"{len(codes)} novos problemas"
        )

        df_user = get_last_accepted_for_codes(
            user=user,
            codes=codes,
            problems_csv=problems_csv,
        )

        if df_user.empty:
            continue

        for _, row in df_user.iterrows():

            category = row.get("category")

            rows_to_save.append({
                "source": "CSES",
                "source_id": f"{user}:{row['problem_code']}",
                "handle": handle,
                "contest_id": "CSES",
                "problem_index": str(row["problem_code"]),
                "problem_rating": None,
                "problem_tags": [category] if pd.notna(category) else ["CSES"],
                "verdict": "OK",
                "submitted_at": _submitted_at_iso(row["time"]),
                "cf_id": None,
            })

    if not rows_to_save:

        print(
            "Nenhuma atualização necessária."
        )

        return pd.DataFrame()

    db.save_submissions(rows_to_save)

    print(
        f"Adicionados/atualizados {len(rows_to_save)} registros."
    )

    return pd.DataFrame(rows_to_save)

@st.cache_data(ttl=3600)
def sync_cses_data(problems_csv: str = "data/cses_problems.csv", **_ignored):
    """
    Verifica se existem novas soluções no CSES e, se existirem,
    grava na tabela `submissions`. `_ignored` absorve kwargs antigos
    (ex: users_csv, cses_all_csv) por compatibilidade.
    """

    try:
        update(problems_csv=problems_csv)

    except Exception as e:
        print(f"Erro ao sincronizar CSES: {e}")