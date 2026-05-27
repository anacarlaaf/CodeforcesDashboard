import requests
from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd
import time
import json

BASE_URL = "https://cses.fi"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


accounts = json.loads(st.secrets["CSES_ACCOUNTS"])

users = pd.read_csv("users.csv")

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

