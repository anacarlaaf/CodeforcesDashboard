import requests
from bs4 import BeautifulSoup
from pathlib import Path
import streamlit as st
import pandas as pd
import time
import json
import os

BASE_URL = "https://cses.fi"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

_raw = os.environ.get("CSES_ACCOUNTS")

if not _raw:
    try:
        _raw = st.secrets.get("CSES_ACCOUNTS")
    except Exception:
        pass

if not _raw:
    raise RuntimeError("CSES_ACCOUNTS não encontrado.")

accounts = json.loads(_raw)

users = pd.read_csv("data/users.csv")

users_codes = users["cses_code"]

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
def get_cses_sessions():
    """
    Cria pool de sessões autenticadas.
    """

    sessions = []

    for acc in accounts:

        user = acc["user"]
        password = acc["password"]

        try:

            session = login_cses(
                user=user,
                password=password,
            )

            sessions.append(session)

        except Exception as e:

            print(
                f"Erro login {user}: {e}"
            )

    if len(sessions) == 0:

        raise RuntimeError(
            "Nenhuma sessão autenticada."
        )

    print(
        f"\n✅ {len(sessions)} sessões autenticadas."
    )

    return sessions

def get_rotating_session(
    sessions,
    index: int,
):
    """
    Rotaciona sessões.
    """

    return sessions[
        index % len(sessions)
    ]

def update_cses_stats(
    html: str,
    csv_file: str = "data/cses_stats.csv"
):
    """
    Extrai user + solved tasks
    e atualiza/cria um CSV.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    rows = []

    table = soup.find("table", class_=None)

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

    # cria arquivo
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

    # atualiza existente
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


def get_solved_tasks_by_user(
    users_csv: str,
    sleep_time: float = 0.1,
):

    users_df = pd.read_csv(users_csv)

    sessions = get_cses_sessions()

    result = {}

    total = len(users_df)

    for idx, row in users_df.iterrows():

        if pd.isna(row["cses_code"]) or pd.isna(row["cses_user"]):
            continue

        cses_user = row["cses_user"]
        cses_code = int(row["cses_code"])

        print(
            f"\n[{idx+1}/{total}] USER: {cses_user}"
        )

        # sessão rotativa
        session = get_rotating_session(
            sessions,
            idx,
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

                # apenas:
                # /problemset/task/<id>/
                if (
                    len(parts) >= 3
                    and parts[0] == "problemset"
                    and parts[1] == "task"
                ):

                    try:

                        task_id = int(parts[2])

                        solved.add(task_id)

                    except ValueError:
                        pass

            solved = sorted(solved)

            result[cses_user] = solved

            print(
                f"Solved: {len(solved)}"
            )

        except Exception as e:

            print("ERROR:", e)

            result[cses_user] = []

        time.sleep(sleep_time)

    return result

def get_last_accepted_for_codes(
    user: str,
    codes: list[int],
    users_csv: str,
    problems_csv: str,
    sleep_time: float = 0.2,
):
    """
    Para cada código em `codes`, consulta:

    https://cses.fi/problemset/queue/{code}/1/
        ?lang=0&status=2
        &user={user}
        &by=0
        &order=1

    e extrai:
        - sent at
        - user
        - user_code
        - problem_code
        - category

    Retorna:
        DataFrame(
            user,
            user_code,
            problem_code,
            time,
            category
        )
    """

    users_df = pd.read_csv(users_csv)
    problems_df = pd.read_csv(problems_csv)

    user_code_map = dict(
        zip(
            users_df["cses_user"],
            users_df["cses_code"],
        )
    )

    category_map = dict(
        zip(
            problems_df["task_id"],
            problems_df["category"],
        )
    )

    sessions = get_cses_sessions()
    session = sessions[0]

    user_code = user_code_map.get(user)

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
                    "user_code": user_code,
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

def get_new_problem_codes(
    users_csv: str,
    cses_all_csv: str = "cses_all.parquet",
):
    """
    Retorna apenas os problemas ainda não presentes
    em cses_all.parquet.

    Retorno:

    {
        user: [problem_codes_novos]
    }
    """

    solved_tasks = get_solved_tasks_by_user(
        users_csv=users_csv
    )

    # primeira execução
    if not Path(cses_all_csv).exists():

        return {
            user: sorted(codes)
            for user, codes in solved_tasks.items()
        }

    df = pd.read_parquet(cses_all_csv)

    result = {}

    for user, current_codes in solved_tasks.items():

        current_codes = set(current_codes)

        user_df = df.loc[
            df["user"] == user
        ]

        saved_codes = set(
            user_df["problem_code"]
            .dropna()
            .astype(int)
            .tolist()
        )

        new_codes = sorted(
            current_codes - saved_codes
        )

        print(
            f"{user}: "
            f"{len(saved_codes)} salvos | "
            f"{len(current_codes)} atuais | "
            f"{len(new_codes)} novos"
        )

        result[user] = new_codes

    return result


def update(
    users_csv: str,
    problems_csv: str,
    cses_all_csv: str = "cses_all.parquet",
):
    """
    Atualiza cses_all.parquet apenas com
    os problemas novos encontrados.
    """

    new_problems = get_new_problem_codes(
        users_csv=users_csv,
        cses_all_csv=cses_all_csv,
    )

    dfs = []

    for user, codes in new_problems.items():

        if len(codes) == 0:
            continue

        print(
            f"{user}: "
            f"{len(codes)} novos problemas"
        )

        df_user = get_last_accepted_for_codes(
            user=user,
            codes=codes,
            users_csv=users_csv,
            problems_csv=problems_csv,
        )

        if not df_user.empty:
            dfs.append(df_user)

    if len(dfs) == 0:

        print(
            "Nenhuma atualização necessária."
        )

        return pd.DataFrame()

    df_new = pd.concat(
        dfs,
        ignore_index=True,
    )

    # primeira execução
    if not Path(cses_all_csv).exists():

        df_new.to_parquet(
            cses_all_csv,
            index=False,
        )

        print(
            f"Criado {cses_all_csv}"
        )

        return df_new

    df_old = pd.read_parquet(
        cses_all_csv
    )

    df_final = pd.concat(
        [df_old, df_new],
        ignore_index=True,
    )

    # proteção extra contra duplicatas
    df_final = df_final.drop_duplicates(
        subset=[
            "user",
            "problem_code",
        ],
        keep="last",
    )

    df_final = df_final.sort_values(
        ["user", "time"]
    )

    df_final.to_parquet(
        cses_all_csv,
        index=False,
    )

    print(
        f"Adicionados {len(df_new)} registros."
    )

    return df_new

@st.cache_data(ttl=3600)
def sync_cses_data(
    users_csv="data/users.csv",
    problems_csv="data/cses_problems.csv",
    cses_all_csv="data/cses_all.parquet",
):
    """
    Verifica se existem novas soluções no CSES.
    Se existirem, atualiza cses_all.parquet.
    """

    try:
        update(
            users_csv=users_csv,
            problems_csv=problems_csv,
            cses_all_csv=cses_all_csv,
        )

    except Exception as e:
        print(f"Erro ao sincronizar CSES: {e}")

def load_submissions(
    cses_all_csv="data/cses_all.parquet",
    users_csv="data/users.csv",
    problems_csv="data/cses_problems.csv",
):
    
    # garante atualização antes de carregar
    # agora atualiza por fora
    # sync_cses_data(
    #     users_csv=users_csv,
    #     problems_csv=problems_csv,
    #     cses_all_csv=cses_all_csv,
    # )

    df = pd.read_parquet(cses_all_csv)

    if df.empty:
        return pd.DataFrame()

    users = pd.read_csv(users_csv)

    # mapa cses -> codeforces
    users = users[
        ["codeforces", "cses_user"]
    ].dropna(subset=["cses_user"])

    df = df.merge(
        users,
        left_on="user",
        right_on="cses_user",
        how="left",
    )

    df["handle"] = df["codeforces"]

    # remover quem não possui handle CF cadastrado
    df = df.dropna(subset=["handle"])

    df["date"] = pd.to_datetime(
        df["time"],
        utc=True,
    )

    df["problem.contestId"] = "CSES"

    df["problem.index"] = (
        df["problem_code"]
        .astype(str)
    )

    df["problem.rating"] = pd.NA

    df["problem.tags"] = (
        df["category"]
        .fillna("CSES")
        .apply(lambda x: [x])
    )

    df["verdict"] = "OK"

    df["source"] = "CSES"

    return df[
        [
            "handle",
            "date",
            "problem.contestId",
            "problem.index",
            "problem.rating",
            "problem.tags",
            "verdict",
            "source",
        ]
    ]