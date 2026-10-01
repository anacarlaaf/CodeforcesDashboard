# reminders.py (versão corrigida)
import datetime
import pytz
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from bot_config import DAYS_PT, DAYS_EN, DEFAULT_TIMEZONE
import codeforces
import db
import rankings

@dataclass
class Reminder:
    days: List[str]  # dias em inglês (monday, tuesday, ...)
    time: str        # formato HH:MM

@dataclass
class UserData:
    handle: str
    reminders: List[Reminder]
    timezone: str = DEFAULT_TIMEZONE

class ReminderManager:
    """
    Cadastro dos usuários do bot, persistido na tabela `telegram_users`
    do Supabase (ver db.py). Os dados são carregados uma vez em memória
    (`self.data`, mesmo formato do antigo data/telegram_users.json) e
    cada alteração grava só a linha do usuário que mudou.
    """

    def __init__(self):
        self.data = self._load_data()

    def _load_data(self) -> Dict:
        """Carrega os usuários do Supabase"""
        return db.load_telegram_users()

    def _save_data(self, user_id: str):
        """Grava no Supabase os dados de um usuário"""
        db.save_telegram_user(user_id, self.data[user_id], DEFAULT_TIMEZONE)
    
    def get_user(self, user_id: str) -> Optional[UserData]:
        """Obtém os dados de um usuário"""
        if user_id not in self.data:
            return None
        
        user_data = self.data[user_id]
        return UserData(
            handle=user_data.get("handle", ""),
            reminders=[Reminder(**r) for r in user_data.get("reminders", [])],
            timezone=user_data.get("timezone", DEFAULT_TIMEZONE)
        )
    
    def set_handle(self, user_id: str, handle: str):
        """Define o handle do Codeforces para o usuário"""
        if user_id not in self.data:
            self.data[user_id] = {}
        
        self.data[user_id]["handle"] = handle
        self._save_data(user_id)
    
    def set_timezone(self, user_id: str, timezone: str):
        """Define o fuso horário do usuário"""
        if user_id not in self.data:
            self.data[user_id] = {}
        
        self.data[user_id]["timezone"] = timezone
        self._save_data(user_id)
    
    def add_reminder(self, user_id: str, days: List[str], time: str) -> bool:
        """Adiciona um lembrete para o usuário"""
        # Valida o formato do horário e normaliza (garante zero à
        # esquerda, ex: "9:00" -> "09:00"), pois a comparação em
        # get_reminders_for_time usa strftime("%H:%M"), que sempre
        # gera a versão com zero à esquerda.
        try:
            parsed_time = datetime.datetime.strptime(time, "%H:%M")
        except:
            return False

        time = parsed_time.strftime("%H:%M")
        
        # Valida os dias
        valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        if not all(d.lower() in valid_days for d in days):
            return False
        
        if user_id not in self.data:
            self.data[user_id] = {"reminders": []}
        
        if "reminders" not in self.data[user_id]:
            self.data[user_id]["reminders"] = []
        
        # Evita duplicatas
        new_reminder = Reminder(days=[d.lower() for d in days], time=time)
        # Verifica se já existe um lembrete igual
        for existing in self.data[user_id]["reminders"]:
            if existing["days"] == new_reminder.days and existing["time"] == new_reminder.time:
                return False
        
        self.data[user_id]["reminders"].append(asdict(new_reminder))
        self._save_data(user_id)
        return True
    
    def remove_reminder(self, user_id: str, index: int) -> bool:
        """Remove um lembrete pelo índice"""
        if user_id not in self.data:
            return False
        
        if "reminders" not in self.data[user_id]:
            return False
        
        if 0 <= index < len(self.data[user_id]["reminders"]):
            del self.data[user_id]["reminders"][index]
            self._save_data(user_id)
            return True
        
        return False

    def remove_all_reminders(self, user_id: str):
        """Remove todos os lembretes do usuário"""
        if user_id not in self.data:
            return

        self.data[user_id]["reminders"] = []
        self._save_data(user_id)
    
    def get_reminders_for_time(self, current_time_utc: datetime.datetime) -> List[Tuple[str, UserData]]:
        """
        Retorna os usuários que devem receber lembrete agora.

        `current_time_utc` deve ser um datetime *timezone-aware* em UTC
        (ex: datetime.datetime.now(datetime.timezone.utc)). A comparação
        de dia/horário é feita no fuso horário de CADA usuário, não no
        fuso do servidor onde o processo está rodando — isso evita que
        o lembrete dispare na hora errada quando o servidor não está em
        America/Manaus (ex: VMs que usam UTC por padrão).
        """

        result = []

        for user_id, data in self.data.items():
            if "reminders" not in data:
                continue

            # Verifica se o usuário tem handle
            handle = data.get("handle")
            if not handle:
                continue

            # Converte o horário atual (UTC) para o fuso do usuário
            tz = pytz.timezone(data.get("timezone", DEFAULT_TIMEZONE))
            local_now = current_time_utc.astimezone(tz)

            weekday = local_now.strftime("%A").lower()
            time_str = local_now.strftime("%H:%M")

            for reminder in data["reminders"]:
                if weekday in reminder["days"] and reminder["time"] == time_str:
                    # Verifica se já foi enviado hoje (no fuso do usuário)
                    today = local_now.date()
                    last_sent = data.setdefault("last_sent", {})
                    last_sent_key = f"{','.join(reminder['days'])}_{reminder['time']}"

                    if last_sent.get(last_sent_key) != str(today):
                        last_sent[last_sent_key] = str(today)
                        self._save_data(user_id)
                        
                        # Converte para UserData
                        user_data = UserData(
                            handle=handle,
                            reminders=[Reminder(**r) for r in data["reminders"]],
                            timezone=data.get("timezone", DEFAULT_TIMEZONE)
                        )
                        result.append((user_id, user_data))
        
        return result
    
    def get_reminders_upcoming_in(self, current_time_utc: datetime.datetime, minutes_ahead: int = 10) -> List[Tuple[str, str]]:
        """
        Retorna [(user_id, horario)] para lembretes que vão disparar daqui a
        `minutes_ahead` minutos (calculado no fuso de cada usuário).

        Usado para saber quando atualizar os dados (CF/CSES) ANTES do envio
        do lembrete, para que a mensagem já reflita as submissões recentes.
        """
        result = []
        offset = datetime.timedelta(minutes=minutes_ahead)

        for user_id, data in self.data.items():
            if "reminders" not in data:
                continue

            handle = data.get("handle")
            if not handle:
                continue

            tz = pytz.timezone(data.get("timezone", DEFAULT_TIMEZONE))
            target_local = (current_time_utc + offset).astimezone(tz)

            weekday = target_local.strftime("%A").lower()
            time_str = target_local.strftime("%H:%M")

            for reminder in data["reminders"]:
                if weekday in reminder["days"] and reminder["time"] == time_str:
                    result.append((user_id, reminder["time"]))

        return result

    def _load_combined_submissions(self, handle: str) -> pd.DataFrame:
        """Submissões de Codeforces + CSES de um handle. load_data já
        devolve as duas fontes juntas (tabela unificada no Supabase)."""
        subs, _, _ = codeforces.load_data(handles=[handle])

        if subs is None or subs.empty or 'date' not in subs.columns:
            return pd.DataFrame(
                columns=["handle", "date", "verdict", "problem.contestId", "problem.index"]
            )

        subs = subs.copy()
        subs['date'] = pd.to_datetime(subs['date'], utc=True)
        return subs

    def _count_solved_and_active_days_in_range(
        self, handle: str, start_utc: datetime.datetime, end_utc: datetime.datetime,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> Tuple[int, int]:
        """
        Retorna (questoes_unicas_resolvidas, dias_ativos) para um handle,
        considerando apenas submissões no intervalo [start_utc, end_utc].
        Dia ativo = dia (no fuso do usuário) com pelo menos um accept —
        mesma regra da ofensiva (ver rankings.py).
        """
        all_subs = self._load_combined_submissions(handle)
        if all_subs.empty:
            return 0, 0

        mask = (all_subs['date'] >= start_utc) & (all_subs['date'] <= end_utc)
        subs_in_range = all_subs[mask]

        if subs_in_range.empty:
            return 0, 0

        solved = subs_in_range[subs_in_range['verdict'] == 'OK']
        unique_solved = solved.drop_duplicates(
            ['handle', 'problem.contestId', 'problem.index']
        )
        total_solved = len(unique_solved)
        active_days = int(rankings.count_active_days(subs_in_range, timezone).sum())

        return total_solved, active_days

    def get_user_solved_yesterday(self, handle: str, timezone: str) -> int:
        """
        Retorna quantas questões ÚNICAS o usuário resolveu 'ontem', considerando
        o dia de calendário no fuso horário do próprio usuário (não UTC).
        """
        try:
            tz = pytz.timezone(timezone)
            now_local = datetime.datetime.now(datetime.timezone.utc).astimezone(tz)
            yesterday_local_date = now_local.date() - datetime.timedelta(days=1)

            start_local = tz.localize(datetime.datetime.combine(yesterday_local_date, datetime.time.min))
            end_local = tz.localize(datetime.datetime.combine(yesterday_local_date, datetime.time.max))

            start_utc = start_local.astimezone(datetime.timezone.utc)
            end_utc = end_local.astimezone(datetime.timezone.utc)

            total_solved, _ = self._count_solved_and_active_days_in_range(
                handle, start_utc, end_utc, timezone
            )
            return total_solved

        except Exception as e:
            print(f"Erro ao buscar questões de ontem para {handle}: {e}")
            return 0

    def get_user_stats(self, handle: str, timezone: str = DEFAULT_TIMEZONE) -> Tuple[int, int]:
        """
        Retorna (total_questoes_unicas, dias_com_submissao) referentes ao dia
        de HOJE, no fuso horário local do usuário (não uma janela rolante de
        24h em UTC, que misturava parte de ontem com parte de hoje e dava a
        sensação de dado "desatualizado"/inconsistente).

        Usa a MESMA lógica de contagem do dashboard/ranking:
        - combina Codeforces + CSES
        - conta problemas ÚNICOS resolvidos via drop_duplicates
          (evita contar reenvios aceitos do mesmo problema várias vezes)
        """
        try:
            tz = pytz.timezone(timezone)
            now_local = datetime.datetime.now(datetime.timezone.utc).astimezone(tz)
            today_local_date = now_local.date()

            start_local = tz.localize(datetime.datetime.combine(today_local_date, datetime.time.min))
            # Usa "agora" como fim do intervalo (não faz sentido olhar pro
            # futuro do dia de hoje)
            end_utc = now_local.astimezone(datetime.timezone.utc)
            start_utc = start_local.astimezone(datetime.timezone.utc)

            return self._count_solved_and_active_days_in_range(
                handle, start_utc, end_utc, timezone
            )

        except Exception as e:
            print(f"Erro ao buscar estatísticas de hoje para {handle}: {e}")
            return 0, 0

    def get_user_streak(self, handle: str, timezone: str = DEFAULT_TIMEZONE) -> Tuple[int, int, bool]:
        """
        Retorna (ofensiva_atual, maior_ofensiva, ja_teve_accept_hoje), com
        os dias contados no fuso do usuário. Ver rankings.streaks.
        """
        try:
            all_subs = self._load_combined_submissions(handle)
            streak = rankings.streaks(all_subs, timezone)

            if handle not in streak.index:
                return 0, 0, False

            s = streak.loc[handle]
            return int(s["current"]), int(s["longest"]), bool(s["active_today"])

        except Exception as e:
            print(f"Erro ao calcular ofensiva de {handle}: {e}")
            return 0, 0, False