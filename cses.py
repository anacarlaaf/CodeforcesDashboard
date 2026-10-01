import requests
from bs4 import BeautifulSoup
from pathlib import Path
import streamlit as st
import pandas as pd
import time
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

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

# -----------------------------------
# SESSÃO (conta mestre)
# -----------------------------------
# Guardada no módulo (não em st.cache_resource) pra funcionar igual no
# dashboard, no bot e nos scripts: num processo de longa duração (bot,
# servidor do Streamlit) o login é feito uma vez só e reaproveitado.
# Se a sessão expirar, _get_page refaz o login automaticamente.

_session = None
_session_lock = threading.Lock()


def get_cses_session(force_login: bool = False):
    """Sessão autenticada com a conta mestre, reaproveitada para
    consultar os dados de TODOS os usuários (via `user=<nick>` na URL)."""

    global _session

    with _session_lock:

        if _session is None or force_login:

            try:
                _session = login_cses(
                    user=MASTER_USER,
                    password=MASTER_PASSWORD,
                )
            except Exception as e:
                raise RuntimeError(
                    f"Erro ao logar com a conta mestre ({MASTER_USER}): {e}"
                )

        return _session


def _get_page(path: str) -> str:
    """GET autenticado. As páginas de usuário/fila só trazem dados com
    login; se a resposta vier sem sessão (expirou), loga de novo uma
    vez e repete."""

    for attempt in range(2):

        session = get_cses_session(force_login=attempt > 0)

        r = session.get(f"{BASE_URL}{path}", timeout=20)

        if r.status_code == 200 and "/logout" in r.text:
            return r.text

        if r.status_code not in (200, 401, 403):
            raise RuntimeError(f"HTTP {r.status_code} em {path}")

    raise RuntimeError(f"Sessão do CSES inválida ao abrir {path}")


def update_cses_stats(
    html: str,
    csv_file: str = "utils/cses_stats.csv"
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


# -----------------------------------
# CATÁLOGO DE PROBLEMAS
# -----------------------------------

CATALOG_TTL = 86400  # 1 dia
_catalog = None
_catalog_at = 0.0


def _catalog_from_csv(path: str) -> dict:
    try:
        df = pd.read_csv(path, dtype={"task_id": str})
    except FileNotFoundError:
        return {}

    return df.set_index("task_id")[["name", "category", "url"]].to_dict("index")


def get_task_catalog(fallback_csv: str = "utils/cses_problems.csv") -> dict:
    """
    {task_id: {name, category, url}} de todos os problemas do CSES,
    lido de /problemset/list/ (uma página só) e guardado por um dia.
    Assim problemas novos do CSES aparecem com nome e categoria sem
    precisar atualizar o CSV na mão — o CSV fica só como fallback se o
    CSES estiver fora do ar (e esse fallback não é guardado em cache,
    pra tentar o site de novo na próxima chamada).
    """

    global _catalog, _catalog_at

    if _catalog is not None and time.time() - _catalog_at < CATALOG_TTL:
        return _catalog

    try:
        soup = BeautifulSoup(_get_page("/problemset/list/"), "html.parser")

        catalog = {}

        for h2 in soup.find_all("h2"):

            ul = h2.find_next_sibling("ul")

            if ul is None or "task-list" not in (ul.get("class") or []):
                continue

            category = h2.get_text(strip=True)

            for a in ul.select('li.task a[href^="/problemset/task/"]'):
                task_id = a["href"].strip("/").split("/")[-1]
                catalog[task_id] = {
                    "name": a.get_text(strip=True),
                    "category": category,
                    "url": f"{BASE_URL}/problemset/task/{task_id}",
                }

        if not catalog:
            raise RuntimeError("lista de problemas vazia")

        _catalog, _catalog_at = catalog, time.time()

        return catalog

    except Exception as e:
        print(f"[CSES] Falha ao ler lista de problemas ({e}), usando {fallback_csv}")
        return _catalog or _catalog_from_csv(fallback_csv)


# -----------------------------------
# SCRAPING POR USUÁRIO
# -----------------------------------

def fetch_user_tasks(cses_code) -> tuple[set, set]:
    """
    (resolvidos, tentados_sem_accept) de um usuário, lidos da página
    /problemset/user/{code}/ — um request só. Na página, o ícone de
    cada problema tem a classe `full` (resolvido) ou `zero` (tentou e
    não passou); sem nenhuma das duas, nunca tentou.
    """

    soup = BeautifulSoup(
        _get_page(f"/problemset/user/{int(cses_code)}/"),
        "html.parser",
    )

    solved, attempted = set(), set()

    for a in soup.select("a.task-score"):

        parts = a.get("href", "").strip("/").split("/")

        if len(parts) < 3 or parts[:2] != ["problemset", "task"]:
            continue

        try:
            code = int(parts[2])
        except ValueError:
            continue

        classes = a.get("class") or []

        if "full" in classes:
            solved.add(code)
        elif "zero" in classes:
            attempted.add(code)

    return solved, attempted


def fetch_first_accept(cses_user: str, code: int):
    """
    Horário (texto, fuso do CSES) do PRIMEIRO accept do usuário no
    problema, ou None. order=0 = mais antiga primeiro. O filtro
    `user=` da fila pode casar com outros nicks parecidos, então a
    linha é conferida pelo nick exato.
    """

    html = _get_page(
        f"/problemset/queue/{code}/1/"
        f"?lang=0&status=2&user={cses_user}&by=0&order=0"
    )

    table = BeautifulSoup(html, "html.parser").find("table")

    if table is None:
        return None

    for tr in table.find_all("tr"):

        tds = tr.find_all("td")

        if len(tds) < 7:
            continue

        if tds[1].get_text(strip=True) != cses_user:
            continue

        # coluna 0: "2024-04-14 20:45:03"
        return tds[0].get_text(" ", strip=True).replace("\xa0", " ")

    return None


# A fila de submissões do CSES mostra o horário sem fuso, no horário
# da Finlândia (servidor) — com horário de verão. Conferido comparando
# a submissão mais recente da fila com o horário atual.
CSES_TIMEZONE = "Europe/Helsinki"


def _submitted_at_iso(time_value):
    ts = pd.Timestamp(time_value)

    if ts.tzinfo is None:
        ts = ts.tz_localize(
            CSES_TIMEZONE,
            ambiguous=True,
            nonexistent="shift_forward",
        )

    ts = ts.tz_convert("UTC")

    return ts.isoformat()


# -----------------------------------
# SINCRONIZAÇÃO
# -----------------------------------

# Intervalo mínimo entre duas sincronizações do MESMO usuário. Evita
# repetir o scraping quando vários lembretes caem no mesmo horário,
# quando alguém chama /stats várias vezes ou a cada rerun do
# Streamlit. force=True ignora (botão "Atualizar dados", cron).
SYNC_INTERVAL = 600  # segundos

# Requests simultâneos ao CSES. Mais que isso arrisca bloqueio da
# conta mestre.
MAX_WORKERS = 4

_last_sync = {}  # handle do CF -> time.time() da última sincronização
_sync_lock = threading.Lock()


def needs_sync(handles) -> bool:
    """True se algum dos handles não é sincronizado há mais de
    SYNC_INTERVAL. Checagem só em memória (sem banco nem rede), pra
    quem chama decidir se vale mostrar um "sincronizando..."."""

    now = time.time()

    return any(now - _last_sync.get(h, 0) >= SYNC_INTERVAL for h in handles)


def sync(handles=None, force: bool = False) -> int:
    """
    Sincroniza o CSES com a tabela `submissions` (source='CSES').

    - `handles`: handles do Codeforces (coluna `codeforces` de
      `members`) a sincronizar; None = todos os membros com CSES.
    - Usuários sincronizados há menos de SYNC_INTERVAL são pulados,
      salvo force=True.

    Custo: 1 consulta ao banco + 1 request por usuário + 1 request por
    problema novo (pra pegar a data do primeiro accept), com até
    MAX_WORKERS requests em paralelo.

    Retorna quantos problemas novos foram gravados.
    """

    if not force and handles is not None and not needs_sync(handles):
        return 0

    members = db.load_members_df()

    members = members[
        members["codeforces"].notna()
        & members["cses_user"].notna()
        & members["cses_code"].notna()
    ].copy()

    members["codeforces"] = members["codeforces"].astype(str).str.strip()
    members["cses_user"] = members["cses_user"].astype(str).str.strip()

    now = time.time()

    if handles is None:
        handles = members["codeforces"].tolist()

    handles = set(handles)

    with _sync_lock:

        if not force:
            handles = {
                h for h in handles
                if now - _last_sync.get(h, 0) >= SYNC_INTERVAL
            }

        # marca antes de começar: outra chamada simultânea (outra
        # sessão do Streamlit, outro lembrete) não repete o trabalho.
        # Handles sem CSES também são marcados, pra needs_sync não
        # ficar pedindo sincronização deles pra sempre.
        for h in handles:
            _last_sync[h] = now

    members = members[members["codeforces"].isin(handles)]

    if members.empty:
        return 0

    saved = db.get_saved_cses_problems(members["codeforces"].tolist())

    users = list(members[["codeforces", "cses_user", "cses_code"]].itertuples(index=False))

    def _user_tasks(m):
        try:
            return fetch_user_tasks(m.cses_code)[0]
        except Exception as e:
            print(f"[CSES] {m.cses_user}: erro ao ler perfil: {e}")
            _last_sync.pop(m.codeforces, None)  # tenta de novo na próxima
            return None

    with ThreadPoolExecutor(MAX_WORKERS) as ex:
        solved_by_user = list(ex.map(_user_tasks, users))

    pending = []

    for m, solved in zip(users, solved_by_user):

        if solved is None:
            continue

        new_codes = sorted(solved - saved.get(m.codeforces, set()))

        print(
            f"[CSES] {m.cses_user}: {len(solved)} resolvidos | "
            f"{len(new_codes)} novos"
        )

        pending.extend((m, code) for code in new_codes)

    if not pending:
        return 0

    def _first_accept(item):
        m, code = item
        try:
            return fetch_first_accept(m.cses_user, code)
        except Exception as e:
            print(f"[CSES] {m.cses_user} {code}: erro ao ler fila: {e}")
            return None

    with ThreadPoolExecutor(MAX_WORKERS) as ex:
        accepted_times = list(ex.map(_first_accept, pending))

    catalog = get_task_catalog()

    rows = []

    for (m, code), accepted_time in zip(pending, accepted_times):

        if accepted_time is None:
            # fica de fora e é tentado de novo na próxima sincronização
            continue

        task = catalog.get(str(code), {})
        category = task.get("category")

        rows.append({
            "source": "CSES",
            "source_id": f"{m.cses_user}:{code}",
            "handle": m.codeforces,
            "contest_id": "CSES",
            "problem_index": str(code),
            "problem_name": task.get("name"),
            "problem_rating": None,
            "problem_tags": [category] if category else ["CSES"],
            "verdict": "OK",
            "submitted_at": _submitted_at_iso(accepted_time),
            "cf_id": None,
        })

    for i in range(0, len(rows), 500):
        db.save_submissions(rows[i:i + 500])

    print(f"[CSES] {len(rows)} problemas novos gravados.")

    return len(rows)


def update(**_ignored) -> int:
    """Sincronização completa de todos os membros, ignorando o
    intervalo mínimo — usada pelo cron, pelo botão "Atualizar dados" e
    pelo ranking. `_ignored` absorve kwargs antigos (ex: problems_csv)."""

    return sync(force=True)
