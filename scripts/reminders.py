# reminders.py (versão corrigida)
import json
import datetime
import pytz
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from bot_config import DATA_FILE, DAYS_PT, DAYS_EN, DEFAULT_TIMEZONE
import codeforces
import cses

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
    def __init__(self):
        self.data_file = DATA_FILE
        self.data = self._load_data()
    
    def _load_data(self) -> Dict:
        """Carrega os dados do arquivo JSON"""
        if not self.data_file.exists():
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            return {}
        
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def _save_data(self):
        """Salva os dados no arquivo JSON"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
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
        self._save_data()
    
    def set_timezone(self, user_id: str, timezone: str):
        """Define o fuso horário do usuário"""
        if user_id not in self.data:
            self.data[user_id] = {}
        
        self.data[user_id]["timezone"] = timezone
        self._save_data()
    
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
        self._save_data()
        return True
    
    def remove_reminder(self, user_id: str, index: int) -> bool:
        """Remove um lembrete pelo índice"""
        if user_id not in self.data:
            return False
        
        if "reminders" not in self.data[user_id]:
            return False
        
        if 0 <= index < len(self.data[user_id]["reminders"]):
            del self.data[user_id]["reminders"][index]
            self._save_data()
            return True
        
        return False
    
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
                    last_sent_key = f"last_sent_{reminder['days']}_{reminder['time']}"
                    
                    if last_sent_key not in data:
                        data[last_sent_key] = ""
                    
                    if data[last_sent_key] != str(today):
                        data[last_sent_key] = str(today)
                        self._save_data()
                        
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
        """Carrega e combina submissões de Codeforces + CSES para um handle."""
        subs, _, _ = codeforces.load_data(handles=[handle])

        if subs is None or subs.empty:
            subs = pd.DataFrame(
                columns=["handle", "date", "verdict", "problem.contestId", "problem.index"]
            )
        else:
            subs = subs.copy()
            if 'date' not in subs.columns:
                if 'creationTimeSeconds' in subs.columns:
                    subs['date'] = pd.to_datetime(subs['creationTimeSeconds'], unit='s', utc=True)
                else:
                    subs['date'] = pd.NaT

        try:
            cses_subs = cses.load_submissions()
        except Exception:
            cses_subs = pd.DataFrame()

        if cses_subs is not None and not cses_subs.empty:
            cses_subs = cses_subs[cses_subs['handle'] == handle].copy()
        else:
            cses_subs = pd.DataFrame(
                columns=["handle", "date", "verdict", "problem.contestId", "problem.index"]
            )

        all_subs = pd.concat([subs, cses_subs], ignore_index=True, sort=False)

        if all_subs.empty:
            return all_subs

        all_subs['date'] = pd.to_datetime(all_subs['date'], utc=True)
        return all_subs

    def _count_solved_and_active_days_in_range(
        self, handle: str, start_utc: datetime.datetime, end_utc: datetime.datetime
    ) -> Tuple[int, int]:
        """
        Retorna (questoes_unicas_resolvidas, dias_com_submissao) para um
        handle, considerando apenas submissões no intervalo [start_utc, end_utc].
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
        days_with_submission = subs_in_range['date'].dt.date.nunique()

        return total_solved, days_with_submission

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

            total_solved, _ = self._count_solved_and_active_days_in_range(handle, start_utc, end_utc)
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

            return self._count_solved_and_active_days_in_range(handle, start_utc, end_utc)

        except Exception as e:
            print(f"Erro ao buscar estatísticas de hoje para {handle}: {e}")
            return 0, 0