import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

import argparse
import datetime
import os
import subprocess

import pandas as pd
import requests

import codeforces
import cses
import rankings


def sync_data():
    """
    Faz git pull no repositório para garantir que os .parquet locais
    estão atualizados com o que foi gerado pelos GitHub Actions
    (update_cf.yml / update_cses.yml) antes de montar o relatório.
    """

    print("[Sync] Atualizando dados (git pull)...")

    result = subprocess.run(
        ["git", "pull", "origin", "main"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(
            f"[Sync] git pull falhou (seguindo com dados locais atuais): "
            f"{result.stderr.strip()}"
        )
    else:
        print(f"[Sync] {result.stdout.strip()}")

def build_dataset(start: datetime.datetime, end: datetime.datetime):
    """
    Reproduz a mesma lógica de carregamento/filtro do dashboard.py,
    mas lendo direto dos parquets (sem Streamlit/UI).
    """

    users = pd.read_csv("data/users.csv")

    handles = (
        users["codeforces"]
        .dropna()
        .astype(str)
        .str.strip()
    )
    handles = handles[handles != ""].tolist()

    subs, rating, cf_users = codeforces.load_data(handles=handles)

    subs["date"] = pd.to_datetime(
        subs["creationTimeSeconds"],
        unit="s",
        utc=True,
    )

    cses_subs = cses.load_submissions()
    cses_subs = cses_subs[cses_subs["handle"].isin(handles)]
    cses_subs["problem.rating"] = -1

    subs = pd.concat(
        [subs, cses_subs],
        ignore_index=True,
        sort=False,
    )

    subs = subs[
        (subs["date"] >= start)
        & (subs["date"] <= end)
    ]

    solved = subs[subs["verdict"] == "OK"]

    unique_solved = solved.drop_duplicates(
        ["handle", "problem.contestId", "problem.index"]
    ).copy()

    return subs, unique_solved


def format_top(title: str, df: pd.DataFrame, value_col: str, suffix: str) -> str:
    medals = ["🥇", "🥈", "🥉"]

    lines = [f"*{title}*"]

    if df.empty:
        lines.append("_sem dados no período_")
        return "\n".join(lines)

    top = df.reset_index(drop=True).head(3)

    # largura máxima dos nomes para alinhar os números
    max_name_len = max(
        len(str(row["handle"]))
        for _, row in top.iterrows()
    )

    lines.append("```")

    for i, row in top.iterrows():
        medal = medals[i]

        handle = str(row["handle"]).ljust(max_name_len)

        value = str(row[value_col])

        lines.append(
            f"{medal} {handle}  {value} {suffix}"
        )

    lines.append("```")

    return "\n".join(lines)


def build_message(period_label: str, start: datetime.datetime, end: datetime.datetime) -> str:

    subs, unique_solved = build_dataset(start, end)

    blocks = [
        "🎈Olá, GCP! Vamos ver como vão os treinos? 🦾🧠",
        "",
        f"🏆 *RANKING {period_label.upper()}* 🏆",
        format_top(
            "Mais questões no total", 
            rankings.top_total_solved(unique_solved),
            "questões", "questões",
        ),
        "",
        format_top(
            "Mais questões no Codeforces",
            rankings.top_codeforces_solved(unique_solved),
            "questões", "questões",
        ),
        "",
        format_top(
            "Mais questões no CSES",
            rankings.top_cses_solved(unique_solved),
            "questões", "questões",
        ),
        "",
        format_top(
            "Maior frequência",
            rankings.top_frequency(subs),
            "dias", "dias com submissão",
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
            "parse_mode": "Markdown",
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
    args = parser.parse_args()

    sync_data()

    today = datetime.datetime.now(datetime.timezone.utc)
    end = today.replace(hour=23, minute=59, second=59, microsecond=999999)

    if args.period == "semanal":
        start = today - datetime.timedelta(days=7)
        period_label = "Semanal"
    else:
        start = today - datetime.timedelta(days=30)
        period_label = "Mensal"

    message = build_message(period_label, start, end)

    print(message)

    send_telegram_message(message)


if __name__ == "__main__":
    main()
