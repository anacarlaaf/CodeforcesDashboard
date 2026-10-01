# test_reminder.py
# Script pra testar manualmente o fluxo de atualização + envio de lembrete,
# sem precisar esperar o job_queue rodar (que só dispara 10min antes do
# horário configurado). Roda: python test_reminder.py

import sys
import os
from pathlib import Path

# IMPORTANTE: este script deve ficar na mesma pasta que tucanito.py e
# bot_config.py (ou seja, dentro de scripts/), pelo mesmo motivo do
# tucanito.py: o bot_config.py procura o .env relativo à própria
# localização dele, e os imports (reminders, tucanito, etc.) são
# resolvidos a partir dessa pasta.
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Vários módulos do projeto (ex: cses.py) usam caminhos relativos como
# "data/users.csv", que só funcionam se o processo estiver rodando com
# o diretório de trabalho na raiz do projeto. Como este script pode ser
# chamado de qualquer lugar (de dentro de scripts/, da raiz, etc.),
# forçamos o cwd pra raiz antes de importar qualquer coisa do projeto.
os.chdir(project_root)

# --- Carrega o .toml ANTES de qualquer import do projeto ---
# codeforces.py (e possivelmente outros módulos) leem variáveis de
# ambiente no momento do import (ex: CODEFORCES_USERS). Se as variáveis
# não estiverem no os.environ antes desses imports, eles quebram mesmo
# que o .toml exista, porque a variável ainda não foi carregada.
#
# Procura em .streamlit/secrets.toml (padrão do Streamlit) e também na
# raiz/scripts, caso o .toml esteja em outro lugar.
def _load_toml_into_env(toml_path: Path):
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        import tomli as tomllib  # fallback: pip install tomli

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    def _flatten(d, prefix=""):
        for key, value in d.items():
            if isinstance(value, dict):
                # Seções do TOML (ex: [codeforces]) viram prefixo, mas
                # também tenta a chave "pura" sem prefixo
                _flatten(value, prefix)
            else:
                os.environ.setdefault(key, str(value))

    _flatten(data)
    print(f"✅ Variáveis carregadas de {toml_path}")


_TOML_CANDIDATES = [
    project_root / ".streamlit" / "secrets.toml",
    project_root / "scripts" / ".streamlit" / "secrets.toml",
    project_root / "secrets.toml",
    project_root / "scripts" / "secrets.toml",
]

for _candidate in _TOML_CANDIDATES:
    if _candidate.exists():
        _load_toml_into_env(_candidate)
        break
else:
    print("⚠️ Nenhum .toml encontrado nos caminhos esperados. "
          "Ajuste _TOML_CANDIDATES em test_reminder.py com o caminho certo.")

import asyncio

from telegram import Bot
from bot_config import BOT_TOKEN
from reminders import ReminderManager

# Reaproveita a mesma lógica de atualização de dados do bot
from tucanito import run_data_update, MOTIVATIONAL_MESSAGES, format_daily_stats
import random


async def main():
    reminder_manager = ReminderManager()

    print("Usuários cadastrados:")
    for uid, data in reminder_manager.data.items():
        handle = data.get("handle", "(sem handle)")
        print(f"  - user_id={uid}  handle={handle}")

    user_id = input("\nDigite o user_id (chat_id do Telegram) que vai receber o teste: ").strip()

    user_data = reminder_manager.get_user(user_id)
    if not user_data or not user_data.handle:
        print("❌ Usuário não encontrado ou sem handle definido.")
        print("   Fale com o bot no Telegram e use /set_handle seu_handle primeiro.")
        return

    # 1. Atualiza os dados (mesma função usada pelo job de 10min antes).
    #    Só o CSES precisa de atualização via script — o Codeforces
    #    é sincronizado sob demanda dentro do codeforces.load_data.
    print("\n🔄 Atualizando dados do CSES... isso pode demorar um pouco.")
    await run_data_update([user_data.handle])
    print("✅ Dados do CSES atualizados.")

    # 2. Estatísticas de hoje + ofensiva (mesmas funções do lembrete real)
    total_accepted, _ = reminder_manager.get_user_stats(
        user_data.handle, user_data.timezone
    )
    streak, longest, active_today = reminder_manager.get_user_streak(
        user_data.handle, user_data.timezone
    )
    print(
        f"📊 {user_data.handle}: {total_accepted} resolvido(s) hoje · "
        f"ofensiva {streak} · recorde {longest} · accept hoje: {active_today}"
    )

    # 3. Monta a mensagem (igual ao check_and_send_reminders, mas marcada como teste)
    motivational_msg = random.choice(MOTIVATIONAL_MESSAGES)
    message = (
        f"🧪 [TESTE] 🔥 Bora treinar, {user_data.handle}! 💪\n\n"
        f"{motivational_msg}\n\n"
        f"{format_daily_stats(total_accepted, streak, longest, active_today)}\n\n"
    )

    # 4. Envia via Telegram
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=user_id, text=message)
    print("\n📨 Mensagem de teste enviada com sucesso!")


if __name__ == "__main__":
    asyncio.run(main())