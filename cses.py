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
