"""
teste_send_rankings.py

Script pra testar a formatação do ranking sem precisar mandar pro grupo.
Envia a mensagem pra um chat_id específico (o seu, por exemplo), usando
a mesma lógica de scripts/send_rankings.py.

NÃO recarrega os dados (não roda git pull nem atualização do CSES) —
usa os parquets/CSVs que já estão na pasta data/ como estão, só pra ver
a formatação da mensagem rapidamente.

Uso:
    python scripts/teste_send_rankings.py --user-id 123456789 --period semanal
    python scripts/teste_send_rankings.py --user-id 123456789 --period mensal

Como pegar seu chat_id:
    Fale com @userinfobot no Telegram, ele te devolve o seu ID.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

import argparse
import datetime
import os

import requests

import send_rankings


def send_telegram_message_to(chat_id: str, text: str):
    """Igual ao send_telegram_message do send_rankings.py, mas manda pra
    um chat_id explícito em vez de usar TELEGRAM_CHAT_ID do ambiente."""

    token = os.environ.get("TELEGRAM_BOT_ID")

    if not token:
        raise RuntimeError("TELEGRAM_BOT_ID não encontrado no ambiente.")

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

    print(f"[Telegram] Mensagem de teste enviada com sucesso para {chat_id}.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--user-id",
        required=True,
        help="chat_id do Telegram que vai receber a mensagem de teste",
    )
    parser.add_argument(
        "--period",
        choices=["semanal", "mensal"],
        default="semanal",
    )
    args = parser.parse_args()

    # Sem sync: usa os dados locais (data/*.parquet, data/*.csv) como
    # já estão, só pra visualizar a formatação da mensagem rapidamente.
    print("[Teste] Usando dados locais, sem recarregar/atualizar nada...")

    today = datetime.datetime.now(datetime.timezone.utc)
    end = today.replace(hour=23, minute=59, second=59, microsecond=999999)

    if args.period == "semanal":
        start = (today - datetime.timedelta(days=6)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        period_label = "Semanal"
    else:
        start = (today - datetime.timedelta(days=29)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        period_label = "Mensal"

    message = send_rankings.build_message(period_label, start, end)

    print("----- PREVIEW DA MENSAGEM -----")
    print(message)
    print("--------------------------------")

    send_telegram_message_to(args.user_id, message)


if __name__ == "__main__":
    main()