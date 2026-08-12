# bot_config.py
import os
import json
from pathlib import Path
import sys

# Token do bot
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_ID")

# Se não encontrou no ambiente, tenta carregar do .env
if not BOT_TOKEN:
    try:
        from dotenv import load_dotenv
        # Procura o .env na raiz do projeto
        dotenv_path = Path(__file__).resolve().parent / ".env"
        if dotenv_path.exists():
            load_dotenv(dotenv_path)
            BOT_TOKEN = os.environ.get("TELEGRAM_BOT_ID")
    except:
        pass

# Se ainda não tem, tenta do Streamlit secrets
if not BOT_TOKEN:
    try:
        import streamlit as st
        BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_ID")
    except:
        pass

if not BOT_TOKEN:
    print("❌ TELEGRAM_BOT_ID não encontrado!")
    print("   Configure de uma das seguintes formas:")
    print("   1. Variável de ambiente: export TELEGRAM_BOT_ID='seu_token'")
    print("   2. Arquivo .env: echo 'TELEGRAM_BOT_ID=seu_token' > .env")
    print("   3. Secrets do Streamlit")
    sys.exit(1)

# Arquivo de dados
DATA_FILE = Path("data/telegram_users.json")

# Dias da semana em português
DAYS_PT = {
    "monday": "segunda",
    "tuesday": "terça", 
    "wednesday": "quarta",
    "thursday": "quinta",
    "friday": "sexta",
    "saturday": "sábado",
    "sunday": "domingo"
}

DAYS_EN = {
    "segunda": "monday",
    "terça": "tuesday",
    "quarta": "wednesday",
    "quinta": "thursday",
    "sexta": "friday",
    "sábado": "saturday",
    "domingo": "sunday"
}

# Fuso horário padrão (Manaus)
DEFAULT_TIMEZONE = "America/Manaus"