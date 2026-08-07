# tucanito.py (versão com interação personalizada)
import sys
import os
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import datetime
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import pytz
import codeforces
import cses
from reminders import ReminderManager
from bot_config import BOT_TOKEN, DAYS_PT, DAYS_EN, DEFAULT_TIMEZONE

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Inicializa o gerenciador de lembretes
reminder_manager = ReminderManager()

# Mapeamento completo de dias (com e sem acento, completo e abreviado)
DAYS_MAP = {
    # Nomes completos
    "segunda": "monday",
    "terça": "tuesday",
    "terca": "tuesday",
    "quarta": "wednesday",
    "quinta": "thursday",
    "sexta": "friday",
    "sábado": "saturday",
    "sabado": "saturday",
    "domingo": "sunday",
    # Abreviações
    "seg": "monday",
    "ter": "tuesday",
    "qua": "wednesday",
    "qui": "thursday",
    "sex": "friday",
    "sab": "saturday",
    "sáb": "saturday",
    "dom": "sunday",
}

# Comandos disponíveis
COMMANDS = {
    "start": "Iniciar o bot e ver instruções",
    "set_handle": "Redefinir seu handle do Codeforces",
    "set_reminder": "Definir lembrete",
    "set_timezone": "Definir fuso horário (padrão: Manaus)",
    "list_reminders": "Listar seus lembretes atuais",
    "remove_reminder": "Remover um lembrete",
    "remove_all": "Remover todos os lembretes",
    "help": "Mostrar esta mensagem"
}

def get_timezones():
    """Retorna lista de timezones comuns para o Brasil"""
    return [
        "America/Manaus",
        "America/Sao_Paulo",
        "America/Cuiaba",
        "America/Recife",
        "America/Fortaleza",
        "America/Belem"
    ]

# ============================================
# FILTRO: APENAS MENSAGENS PRIVADAS
# ============================================

def private_chat_filter(update: Update) -> bool:
    """Verifica se a mensagem é de um chat privado"""
    if update.message:
        chat_type = update.message.chat.type
        return chat_type == "private"
    if update.callback_query:
        chat_type = update.callback_query.message.chat.type
        return chat_type == "private"
    return False

# ============================================
# MENSAGENS PERSONALIZADAS
# ============================================

def get_welcome_message() -> str:
    """Mensagem de boas-vindas inicial"""
    return (
        "👋 Olá! Eu sou o Tucanito, mascote e coach bot do GPC da UFAM\n\n"
        "🎯 Meu objetivo é te ajudar a manter sua rotina de treinos de programação competitiva.\n\n"
        "Para começar, por favor, me informe seu handle do Codeforces com o comando:\n"
        "/set_handle seu_handle"
    )

def get_greeting_message(handle: str) -> str:
    """Mensagem de boas-vindas após definir o handle"""
    return (
        f"🤝 É um prazer te conhecer, {handle}!\n\n"
        "Agora e sempre que você precisar, me envie /help para saber como posso te ajudar a treinar.\n\n"
    )

def get_help_message() -> str:
    """Mensagem de ajuda completa"""
    message = (
        "👋 Olá! Como posso te ajudar hoje?\n\n"
        "Comandos disponíveis:\n"
    )
    
    for cmd, desc in COMMANDS.items():
        message += f"/{cmd} - {desc}\n"
    
    message += (
        "\n📌 Exemplos:\n"
        "/set_reminder 14:30 - Lembrete diário às 14:30\n"
        "/set_reminder seg,qua,sex 15:00 - Lembrete segunda, quarta e sexta às 15:00\n"
        "/set_handle anacarlaaf - Redefine seu handle do Codeforces\n\n"
    )
    
    return message

# ============================================
# HANDLERS COM VERIFICAÇÃO DE CHAT PRIVADO
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensagem de boas-vindas personalizada"""
    if not private_chat_filter(update):
        return
    
    user_id = str(update.effective_user.id)
    user_data = reminder_manager.get_user(user_id)
    
    # Verifica se o usuário já tem handle
    if user_data and user_data.handle:
        # Usuário já configurado - mostra menu completo
        await update.message.reply_text(get_help_message())
    else:
        # Novo usuário - mensagem de boas-vindas
        await update.message.reply_text(get_welcome_message())

async def set_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Define o handle do Codeforces do usuário com mensagem personalizada"""
    if not private_chat_filter(update):
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Por favor, informe seu handle do Codeforces.\n"
            "Exemplo: /set_handle anacarlaaf"
        )
        return
    
    handle = context.args[0].strip()
    user_id = str(update.effective_user.id)
    
    # Verifica se o handle existe
    try:
        subs, _, _ = codeforces.load_data(handles=[handle])
    except Exception as e:
        await update.message.reply_text(
            f"❌ Handle '{handle}' não encontrado ou sem dados.\n"
            "Verifique se o nome está correto."
        )
        return
    
    reminder_manager.set_handle(user_id, handle)
    
    # Mensagem de boas-vindas personalizada
    await update.message.reply_text(get_greeting_message(handle))

async def set_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Define o fuso horário do usuário (apenas privado)"""
    if not private_chat_filter(update):
        return
    
    if not context.args:
        # Mostra opções de timezone
        keyboard = []
        for tz in get_timezones():
            keyboard.append([InlineKeyboardButton(tz, callback_data=f"tz_{tz}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🌍 Escolha seu fuso horário:",
            reply_markup=reply_markup
        )
        return
    
    timezone = context.args[0].strip()
    user_id = str(update.effective_user.id)
    
    # Valida o timezone
    if timezone not in get_timezones():
        await update.message.reply_text(
            f"❌ Fuso horário '{timezone}' não é suportado.\n"
            "Use /set_timezone sem argumentos para ver as opções."
        )
        return
    
    reminder_manager.set_timezone(user_id, timezone)
    
    await update.message.reply_text(
        f"✅ Fuso horário definido para {timezone}"
    )

async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Define um novo lembrete (apenas privado)"""
    if not private_chat_filter(update):
        return
    
    user_id = str(update.effective_user.id)
    user_data = reminder_manager.get_user(user_id)
    
    # Verifica se o usuário tem handle definido
    if not user_data or not user_data.handle:
        await update.message.reply_text(
            "👋 Antes de configurar lembretes, preciso saber seu handle do Codeforces!\n\n"
            "Use /set_handle seu_handle para começar."
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "📝 Como usar o /set_reminder:\n\n"
            "• Diário: /set_reminder 14:30\n"
            "• Dias específicos: /set_reminder seg,qua,sex 15:00\n\n"
            "Dias válidos: seg, ter, qua, qui, sex, sab, dom"
        )
        return
    
    # Processa os argumentos
    args = context.args
    
    # Verifica se tem horário
    time_part = args[-1]  # Último argumento é o horário
    
    # Valida formato do horário
    try:
        datetime.datetime.strptime(time_part, "%H:%M")
    except:
        await update.message.reply_text(
            "❌ Formato de horário inválido. Use HH:MM (ex: 14:30)"
        )
        return
    
    # Verifica se tem dias específicos
    if len(args) == 1:
        # Diário
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        time = args[0]
        days_display = "todos os dias"
    else:
        # Dias específicos (junta tudo antes do horário, pois o Telegram
        # já separa por espaço, mesmo quando há espaço depois da vírgula)
        days_str = "".join(args[:-1]).lower().replace(" ", "")
        days_list = [d for d in days_str.split(",") if d]
        
        # Converte para inglês usando o mapeamento
        days = []
        invalid_days = []
        
        for d in days_list:
            d = d.strip()
            if d in DAYS_MAP:
                days.append(DAYS_MAP[d])
            else:
                invalid_days.append(d)
        
        if invalid_days:
            await update.message.reply_text(
                f"❌ Dias inválidos: {', '.join(invalid_days)}\n"
                "Use: seg, ter, qua, qui, sex, sab, dom\n"
                "Ou: segunda, terça, quarta, quinta, sexta, sábado, domingo"
            )
            return
        
        time = args[-1]
        # Mostra os dias em português para confirmação
        days_display = ", ".join([DAYS_PT[d] for d in days])
    
    # Adiciona o lembrete
    if reminder_manager.add_reminder(user_id, days, time):
        await update.message.reply_text(
            f"✅ Lembrete adicionado!\n"
            f"📅 Dias: {days_display}\n"
            f"⏰ Horário: {time}\n\n"
            f"Você receberá um lembrete para treinar nesses dias e horários!"
        )
    else:
        await update.message.reply_text(
            "❌ Não foi possível adicionar o lembrete. Verifique os dados e tente novamente."
        )

async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todos os lembretes do usuário (apenas privado)"""
    if not private_chat_filter(update):
        return
    
    user_id = str(update.effective_user.id)
    user_data = reminder_manager.get_user(user_id)
    
    if not user_data or not user_data.reminders:
        await update.message.reply_text(
            "📭 Você não tem lembretes configurados.\n"
            "Use /set_reminder para criar um."
        )
        return
    
    message = "📋 Seus lembretes:\n\n"
    
    for i, reminder in enumerate(user_data.reminders, 1):
        days_display = ", ".join([DAYS_PT[d] for d in reminder.days])
        message += f"{i}. 📅 {days_display} ⏰ {reminder.time}\n"
    
    message += f"\n🌍 Fuso horário: {user_data.timezone}\n"
    message += f"👤 Handle: {user_data.handle}\n\n"
    message += "Para remover: /remove_reminder NUMERO"
    
    await update.message.reply_text(message)

async def remove_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove um lembrete pelo índice (apenas privado)"""
    if not private_chat_filter(update):
        return
    
    user_id = str(update.effective_user.id)
    
    if not context.args:
        await update.message.reply_text(
            "❌ Informe o número do lembrete para remover.\n"
            "Use /list_reminders para ver seus lembretes."
        )
        return
    
    try:
        index = int(context.args[0]) - 1  # Converte para 0-based
    except:
        await update.message.reply_text(
            "❌ Número inválido. Use um número inteiro."
        )
        return
    
    if reminder_manager.remove_reminder(user_id, index):
        await update.message.reply_text(
            f"✅ Lembrete #{index + 1} removido com sucesso!"
        )
    else:
        await update.message.reply_text(
            f"❌ Lembrete #{index + 1} não encontrado.\n"
            "Use /list_reminders para ver seus lembretes."
        )

async def remove_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove todos os lembretes (apenas privado)"""
    if not private_chat_filter(update):
        return
    
    user_id = str(update.effective_user.id)
    user_data = reminder_manager.get_user(user_id)
    
    if not user_data or not user_data.reminders:
        await update.message.reply_text(
            "📭 Você não tem lembretes para remover."
        )
        return
    
    # Confirmação
    keyboard = [
        [InlineKeyboardButton("✅ Sim, remover todos", callback_data="remove_all_confirm")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="remove_all_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⚠️ Tem certeza que deseja remover todos os seus {len(user_data.reminders)} lembretes?",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra a ajuda (apenas privado)"""
    if not private_chat_filter(update):
        return
    
    user_id = str(update.effective_user.id)
    user_data = reminder_manager.get_user(user_id)
    
    if user_data and user_data.handle:
        await update.message.reply_text(get_help_message())
    else:
        await update.message.reply_text(get_welcome_message())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lida com callbacks de botões (apenas privado)"""
    if not private_chat_filter(update):
        return
    
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    data = query.data
    
    if data.startswith("tz_"):
        # Seleção de timezone
        timezone = data.replace("tz_", "")
        reminder_manager.set_timezone(user_id, timezone)
        await query.edit_message_text(f"✅ Fuso horário definido para {timezone}")
    
    elif data == "remove_all_confirm":
        # Remove todos os lembretes
        reminder_manager.data[user_id]["reminders"] = []
        reminder_manager._save_data()
        await query.edit_message_text("🗑️ Todos os lembretes foram removidos!")
    
    elif data == "remove_all_cancel":
        await query.edit_message_text("❌ Operação cancelada.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lida com mensagens que não são comandos (apenas privado)"""
    if not private_chat_filter(update):
        return
    
    user_id = str(update.effective_user.id)
    user_data = reminder_manager.get_user(user_id)
    
    # Verifica se é uma mensagem de texto qualquer
    text = update.message.text
    
    # Se o usuário ainda não tem handle, oferece ajuda
    if not user_data or not user_data.handle:
        await update.message.reply_text(
            "👋 Olá! Eu sou o Tucanito, mascote e coach bot do GPC da UFAM. 🎈\n\n"
            "🎯 Meu objetivo é te ajudar a manter sua rotina de treinos de programação competitiva.\n\n"
            "Para começar, por favor, me informe seu handle do Codeforces com o comando /set_handle seu_handle."
        )
        return
    
    # Se já tem handle, responde de forma amigável
    await update.message.reply_text(
        f"👋 Olá, {user_data.handle}! 👋\n\n"
        "Não entendi sua mensagem, mas estou aqui para ajudar!\n\n"
        "Use /help para ver todos os comandos disponíveis ou me envie:\n"
        "• /set_reminder para configurar lembretes\n"
        "• /list_reminders para ver seus lembretes"
    )

def format_daily_stats(total_accepted: int, days_with_submission: int, handle: str) -> str:
    """Formata as estatísticas diárias para a mensagem"""
    if total_accepted >= 1:
        if total_accepted == 1:
            msg = f"🎉 Parabéns, {handle}! Você resolveu {total_accepted} questão hoje!"
        else:
            msg = f"🎉 Parabéns, {handle}! Você resolveu {total_accepted} questões hoje!"
        
        if days_with_submission >= 1:
            msg += f"\n📊 Você treinou em {days_with_submission} dia(s)!"
        
        msg += "\n\nContinue assim! 💪🚀"
    
    else:
        msg = f"😢 Que pena, {handle}! Hoje você não resolveu nenhuma questão."
        msg += "\n\n📝 Dica: Tente resolver pelo menos 1 questão por dia!"
        msg += "\nMesmo uma questão já faz diferença! 🧠"
        msg += "\n\nVamos melhorar amanhã! 💪"
    
    return msg

async def check_and_send_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Verifica periodicamente se há lembretes para enviar"""
    logger.info("🔍 Verificando lembretes...")
    
    now = datetime.datetime.now(datetime.timezone.utc)
    reminders = reminder_manager.get_reminders_for_time(now)
    
    app = context.application
    
    for user_id, user_data in reminders:
        try:
            # Busca as estatísticas do usuário
            total_accepted, days_with_submission = reminder_manager.get_user_stats(user_data.handle, days=1)
            
            # Formata a mensagem (SEM Markdown para evitar erros)
            message = (
                f"🔔 Hora de treinar, {user_data.handle}! 🧠\n\n"
                f"{format_daily_stats(total_accepted, days_with_submission, user_data.handle)}\n\n"
                f"🎯 Meta: 1 questão por dia\n"
                f"\n---\n"
                f"⚙️ Para ajustar seus lembretes, use os comandos:\n"
                f"/list_reminders - Ver seus lembretes\n"
                f"/set_reminder - Definir novo lembrete\n"
                f"/remove_reminder - Remover lembrete"
            )
            
            # Envia a mensagem
            await app.bot.send_message(
                chat_id=user_id,
                text=message
            )
            
            logger.info(f"📨 Lembrete enviado para {user_id} ({user_data.handle})")
            
        except Exception as e:
            logger.error(f"❌ Erro ao enviar lembrete para {user_id}: {e}")

def main():
    """Função principal do bot"""
    
    # Cria a aplicação
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Registra os comandos (todos com filtro de chat privado)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("set_handle", set_handle))
    application.add_handler(CommandHandler("set_reminder", set_reminder))
    application.add_handler(CommandHandler("set_timezone", set_timezone))
    application.add_handler(CommandHandler("list_reminders", list_reminders))
    application.add_handler(CommandHandler("remove_reminder", remove_reminder))
    application.add_handler(CommandHandler("remove_all", remove_all))
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Mensagens não-comandos
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Configura o job para verificar lembretes a cada minuto
    job_queue = application.job_queue
    
    if job_queue:
        # Verifica a cada minuto
        job_queue.run_repeating(
            check_and_send_reminders,
            interval=60,  # 60 segundos
            first=10      # primeira execução em 10 segundos
        )
        logger.info("⏰ Job de lembretes configurado")
    else:
        logger.warning("⚠️ JobQueue não disponível - lembretes não serão enviados automaticamente")
    
    logger.info("🚀 Bot iniciado!")
    
    # Inicia o bot (polling)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
