import sys
import os
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import logging
import datetime

from tucanito import check_and_send_reminders, application, reminder_manager

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_local():
    """
    Testa localmente o envio de lembretes
    """
    print("=" * 50)
    print("🧪 TESTE LOCAL DO BOT DE LEMBRETES")
    print("=" * 50)
    
    # 1. Verifica se o token está configurado
    token = os.environ.get("TELEGRAM_BOT_ID")
    if not token:
        print("❌ TELEGRAM_BOT_ID não encontrado no ambiente!")
        print("   Configure com: export TELEGRAM_BOT_ID='seu_token'")
        return
    
    print(f"✅ Token encontrado: {token[:10]}...")
    
    # 2. Verifica os dados dos usuários
    print("\n📊 Usuários cadastrados:")
    for user_id, data in reminder_manager.data.items():
        handle = data.get("handle", "N/A")
        reminders = data.get("reminders", [])
        print(f"   • {user_id} - {handle} - {len(reminders)} lembretes")
        
        for i, r in enumerate(reminders, 1):
            print(f"     {i}. Dias: {', '.join(r['days'])} - Horário: {r['time']}")
    
    # 3. Verifica o horário atual
    now = datetime.datetime.now()
    print(f"\n⏰ Horário atual: {now.strftime('%H:%M')}")
    print(f"   Dia da semana: {now.strftime('%A')}")
    
    # 4. Verifica se há lembretes para agora
    print("\n🔍 Verificando lembretes para agora...")
    reminders = reminder_manager.get_reminders_for_time(now)
    
    if reminders:
        print(f"✅ {len(reminders)} lembretes encontrados!")
        for user_id, user_data in reminders:
            print(f"   • {user_id} - {user_data.handle}")
    else:
        print("ℹ️ Nenhum lembrete para este horário")
        print("   Para testar, você pode:")
        print("   1. Configurar um lembrete para o horário atual")
        print("   2. Ou modificar manualmente o arquivo data/telegram_users.json")
    
    # 5. Pergunta se quer forçar o envio
    print("\n" + "=" * 50)
    choice = input("Deseja forçar o envio de lembretes agora? (s/N): ")
    
    if choice.lower() == 's':
        print("\n📨 Enviando lembretes...")
        
        # Inicializa o bot
        app = application
        app.bot = app.bot
        
        # Força a verificação
        check_and_send_reminders(app)
        print("✅ Envio concluído!")
    
    print("\n" + "=" * 50)
    print("✅ Teste finalizado!")

if __name__ == "__main__":
    test_local()