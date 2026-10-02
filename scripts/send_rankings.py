import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

import argparse
import datetime
import os

import pandas as pd
import requests

import codeforces
import cses
import db
import rankings


# Mesmo fuso padrão do dashboard e do bot — define onde começa e
# termina cada dia do período do ranking.
RANKING_TIMEZONE = "America/Manaus"


def sync_cses():
    """
    Sincroniza o CSES direto no Supabase antes de montar o ranking.
    O Codeforces não precisa: codeforces.load_data já sincroniza o que
    for novo.
    """

    print("[Sync] Sincronizando CSES...")

    try:
        cses.update()
    except Exception as e:
        print(f"[Sync] ❌ Falha ao sincronizar CSES: {e}")
        print("[Sync] Continuando com os dados já salvos...")


def build_dataset(start: datetime.datetime, end: datetime.datetime):
    """
    Reproduz a mesma lógica de carregamento/filtro do dashboard.py,
    lendo do Supabase (sem Streamlit/UI).
    """

    users = db.load_members_df()

    handles = (
        users["codeforces"]
        .dropna()
        .astype(str)
        .str.strip()
    )
    handles = handles[handles != ""].tolist()

    # já vem UNIFICADO (Codeforces + CSES), com a coluna `source`
    subs, _, _ = codeforces.load_data(handles=handles)

    if subs is None or subs.empty or "date" not in subs.columns:
        subs = pd.DataFrame(
            columns=["handle", "date", "verdict", "source",
                     "problem.contestId", "problem.index"]
        )

    all_subs = subs.copy()
    all_subs["date"] = pd.to_datetime(all_subs["date"], utc=True).dt.tz_convert(RANKING_TIMEZONE)

    subs = all_subs[
        (subs["date"] >= start)
        & (subs["date"] <= end)
    ]

    solved = subs[subs["verdict"] == "OK"]

    unique_solved = solved.drop_duplicates(
        ["handle", "problem.contestId", "problem.index"]
    ).copy()

    return all_subs, subs, unique_solved


def format_top(title: str, df: pd.DataFrame, value_col: str, n: int = 5) -> str:
    lines = [f"*{title}*"]

    if df.empty:
        lines.append("_sem dados no período_")
        return "\n".join(lines)

    top = df.reset_index(drop=True).head(n)
    
    # Encontra o maior handle para definir a largura
    max_handle_len = max(len(str(row["handle"])) for _, row in top.iterrows())
    # Define largura mínima e adiciona padding
    handle_width = max(max_handle_len + 2, 10)  # +2 para espaçamento
    
    # Encontra o maior valor para alinhar à direita
    max_value_len = max(len(str(row[value_col])) for _, row in top.iterrows())
    
    code_lines = []
    
    for i, row in top.iterrows():
        pos = f"{i+1}."
        handle = str(row["handle"])
        value = str(row[value_col])
        
        # Alinhamento: posição à esquerda, handle à esquerda, valor à direita
        line = f"{pos:<3}{handle:<{handle_width}}{value:>{max_value_len}}"
        code_lines.append(line)
    
    lines.append("```text")
    lines.extend(code_lines)
    lines.append("```")

    return "\n".join(lines)

def build_message(period_label: str, start: datetime.datetime, end: datetime.datetime) -> str:

    all_subs, subs, unique_solved = build_dataset(start, end)

    blocks = [
        "🎈Olá, GPC! Vamos ver como vão os treinos? 🦾🧠",
        "",
        f"🏆 *RANKING {period_label.upper()}* 🏆\n",
        format_top(
            "Mais questões no total",
            rankings.top_total_solved(unique_solved, n=5),
            "questões",
        ),
        "",
        format_top(
            "Mais questões no Codeforces",
            rankings.top_codeforces_solved(unique_solved, n=5),
            "questões",
        ),
        "",
        format_top(
            "Mais questões no CSES",
            rankings.top_cses_solved(unique_solved, n=5),
            "questões",
        ),
        "",
        format_top(
            "Dias de estudo",
            rankings.top_frequency(subs, unique_solved, n=5),
            "dias",
        ),
        "",
        # Ofensiva usa o histórico completo, independente do período
        format_top(
            "Maior ofensiva atual 🔥",
            rankings.top_streaks(all_subs, RANKING_TIMEZONE, n=5),
            "dias",
        ),
    ]

    return "\n".join(blocks)


def send_telegram_message(text: str):

    token = os.environ.get("TELEGRAM_BOT_ID")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN e/ou TELEGRAM_CHAT_ID não encontrados no ambiente."
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    r = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",  # Mantém Markdown para negrito/itálico
        },
        timeout=20,
    )

    if r.status_code != 200:
        raise RuntimeError(
            f"Erro ao enviar mensagem no Telegram: {r.status_code} {r.text}"
        )

    print("[Telegram] Mensagem enviada com sucesso.")


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--period",
        choices=["semanal", "mensal"],
        required=True,
    )
    parser.add_argument(
        "--skip-update",
        action="store_true",
        help="Pula a sincronização do CSES (usa os dados já salvos)"
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Obsoleto (não há mais commit de dados); mantido só para "
             "não quebrar chamadas antigas"
    )
    args = parser.parse_args()

    if not args.skip_update:
        sync_cses()
    else:
        print("[Sync] Pulando sincronização do CSES, usando dados já salvos...")

    today = pd.Timestamp.now(tz=RANKING_TIMEZONE)
    end = today.replace(hour=23, minute=59, second=59, microsecond=999999)

    if args.period == "semanal":
        start = (today - datetime.timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "Semanal"
    else:
        start = (today - datetime.timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "Mensal"

    message = build_message(period_label, start, end)

    print(message)

    send_telegram_message(message)


if __name__ == "__main__":
    main()