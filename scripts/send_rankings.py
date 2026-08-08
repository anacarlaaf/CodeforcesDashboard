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
import rankings
from bot_config import BOT_TOKEN

# Caminhos absolutos: como este script agora roda direto na VM (via
# cron), não podemos depender do diretório de onde ele foi chamado.
DATA_DIR = project_root / "data"


def build_dataset(start: datetime.datetime, end: datetime.datetime):
    """
    Reproduz a mesma lógica de carregamento/filtro do dashboard.py,
    lendo direto dos parquets locais (sem Streamlit/UI).

    Importante: este script roda na mesma VM que atualiza os dados
    (via run_cf_update.py / run_cses_update.py), então ele sempre lê
    os arquivos mais recentes — sem precisar de git pull e sem risco
    de divergir do que o dashboard/bot mostram (esse era o motivo dos
    números baterem errado quando isso rodava pelo GitHub Actions).
    """

    users = pd.read_csv(DATA_DIR / "users.csv")

    handles = (
        users["codeforces"]
        .dropna()
        .astype(str)
        .str.strip()
    )
    handles = handles[handles != ""].tolist()

    subs, rating, cf_users = codeforces.load_data(
        handles=handles,
        subs_parquet=str(DATA_DIR / "cf_submissions.parquet"),
        rating_parquet=str(DATA_DIR / "cf_rating.parquet"),
        users_parquet=str(DATA_DIR / "cf_users.parquet"),
    )

    subs["date"] = pd.to_datetime(
        subs["creationTimeSeconds"],
        unit="s",
        utc=True,
    )

    cses_subs = cses.load_submissions(
        cses_all_csv=str(DATA_DIR / "cses_all.parquet"),
        users_csv=str(DATA_DIR / "users.csv"),
        problems_csv=str(DATA_DIR / "cses_problems.csv"),
    )
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
    """
    Usa o mesmo BOT_TOKEN de bot_config.py — o mesmo token que o
    tucanito.py já usa com sucesso para os lembretes individuais.
    Antes esse script montava a URL com TELEGRAM_BOT_ID lido direto do
    ambiente do GitHub Actions, que estava diferente/desatualizado em
    relação ao valor real da VM. O Telegram responde 404 quando o
    token não corresponde a nenhum bot, o que bate com o erro visto.
    """

    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not chat_id:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID não encontrado no ambiente."
        )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

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
    main()git 