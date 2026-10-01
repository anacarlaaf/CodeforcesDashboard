# user_stats.py
"""
Monta a mensagem do comando /stats do bot. Separado do tucanito.py pra
poder ser testado sem o Telegram.

Mesmas regras do dashboard: problema resolvido = accept (único por
problema), dia ativo / ofensiva = rankings.py, dias contados no fuso do
usuário.
"""

import time
import threading

import pandas as pd

import codeforces
import cses
import db
import rankings

PERIODS = {
    "semana": ("últimos 7 dias", 7),
    "mes": ("últimos 30 dias", 30),
    "total": ("histórico completo", None),
}

PERIOD_ALIASES = {
    "semana": "semana", "semanal": "semana", "7": "semana",
    "mes": "mes", "mês": "mes", "mensal": "mes", "30": "mes",
    "total": "total", "tudo": "total", "geral": "total",
}

# Rating >= 100000 aparece em alguns problemas de gym; não é dificuldade real
MAX_REAL_RATING = 100000


def parse_period(arg):
    """'semana' (padrão), 'mes' ou 'total'; None se o argumento for inválido."""
    if not arg:
        return "semana"
    return PERIOD_ALIASES.get(arg.strip().lower())


# -----------------------------------
# DADOS DO GRUPO (para a posição no ranking)
# -----------------------------------
# Leitura direta do banco, sem sincronizar a API de todo mundo (isso
# levaria quase um minuto). Os dados do próprio usuário são sempre os
# recém-sincronizados; os dos outros são os já salvos (atualizados pelo
# cron, pelo dashboard e pelos lembretes). Guardado por 5 min.

GROUP_TTL = 300
_group = None
_group_at = 0.0
_group_lock = threading.Lock()


def _member_handles(members: pd.DataFrame) -> list:
    handles = members["codeforces"].dropna().astype(str).str.strip()
    return handles[handles != ""].tolist()


def _group_submissions(handles: list) -> pd.DataFrame:
    global _group, _group_at

    with _group_lock:

        if _group is None or time.time() - _group_at >= GROUP_TTL:
            _group = db.load_submissions(handles)
            _group_at = time.time()

        return _group


def _position(values: pd.Series, handle: str) -> int:
    """Posição do handle (1 = melhor); empates dividem a posição."""
    mine = values.get(handle, 0)
    return int((values > mine).sum()) + 1


# -----------------------------------
# FORMATAÇÃO
# -----------------------------------

def _bar(done: int, total: int, size: int = 7) -> str:
    if not total:
        return ""
    filled = int(min(done / total, 1) * size)
    if done and not filled:
        filled = 1  # qualquer dia ativo aparece na barra
    return "🟢" * filled + "⚪" * (size - filled)


def _dias(n: int) -> str:
    return f"{n} dia" if n == 1 else f"{n} dias"


def _top(counts: pd.Series, n: int = 3) -> str:
    return ", ".join(f"{k} ({v})" for k, v in counts.head(n).items())


def _unique_solved(subs: pd.DataFrame) -> pd.DataFrame:
    return subs[subs["verdict"] == "OK"].drop_duplicates(
        ["handle", "problem.contestId", "problem.index"]
    )


# -----------------------------------
# MENSAGEM
# -----------------------------------

def build_stats_message(handle: str, timezone: str, period: str = "semana") -> str:
    """
    Texto do /stats (sem Markdown, igual aos lembretes). Sincroniza o
    CSES do usuário antes (pulado se foi sincronizado há pouco) — o
    Codeforces é sincronizado pelo próprio load_data.
    """

    label, n_days = PERIODS[period]

    members = db.load_members_df()
    member_handles = _member_handles(members)

    try:
        if cses.sync([handle]) > 0:
            codeforces.load_data.clear()
    except Exception as e:
        print(f"[stats] Falha ao sincronizar CSES de {handle}: {e}")

    subs, rating, users = codeforces.load_data(handles=[handle])

    if subs is None or subs.empty or "date" not in subs.columns:
        subs = pd.DataFrame(columns=[
            "handle", "date", "verdict", "source", "problem.contestId",
            "problem.index", "problem.rating", "problem.tags", "problem.name",
        ])

    subs = subs.copy()
    subs["date"] = pd.to_datetime(subs["date"], utc=True).dt.tz_convert(timezone)

    now = pd.Timestamp.now(tz=timezone)
    today = now.date()

    if n_days is None:
        start = None
        period_subs = subs
    else:
        start = (now - pd.Timedelta(days=n_days - 1)).normalize()
        period_subs = subs[subs["date"] >= start]

    solved = _unique_solved(period_subs)
    cf_solved = solved[solved["source"] != "CSES"]
    cses_solved = solved[solved["source"] == "CSES"]

    lines = [f"📊 Stats de {handle} — {label}", ""]

    # ---- Ofensiva e dias ativos ----
    streak = rankings.streaks(subs, timezone, today)

    if handle in streak.index:
        current = int(streak.loc[handle, "current"])
        longest = int(streak.loc[handle, "longest"])
        active_today = bool(streak.loc[handle, "active_today"])
    else:
        current = longest = 0
        active_today = False

    icon = "🔥" if active_today else ("⏳" if current else "💤")
    streak_line = f"{icon} Ofensiva: {_dias(current)}"
    if longest > current:
        streak_line += f" (recorde {longest})"
    if current and not active_today:
        streak_line += " — resolva 1 hoje para manter!"
    lines.append(streak_line)

    active = int(rankings.count_active_days(period_subs, timezone).get(handle, 0))

    if n_days is None:
        lines.append(f"📅 Dias ativos: {active}")
    else:
        lines.append(f"📅 Dias ativos: {active}/{n_days}  {_bar(active, n_days)}")

    lines.append("")

    # ---- Resolvidos ----
    lines.append(
        f"🧩 Resolvidos: {len(solved)}  "
        f"(CF {len(cf_solved)} · CSES {len(cses_solved)})"
    )

    solved_today = len(_unique_solved(subs[subs["date"].dt.date == today]))

    if n_days is None:
        lines.append(f"   Hoje: {solved_today}")
    else:
        lines.append(
            f"   Hoje: {solved_today} · Total histórico: {len(_unique_solved(subs))}"
        )

    # ---- Taxa de acerto (só CF: do CSES só guardamos os accepts) ----
    cf_subs = period_subs[
        (period_subs["source"] != "CSES")
        & ~period_subs["verdict"].isin(["COMPILATION_ERROR", "TESTING"])
    ]

    if len(cf_subs):
        ac = int((cf_subs["verdict"] == "OK").sum())
        lines.append(
            f"🎯 Taxa de acerto (CF): {ac / len(cf_subs):.0%} "
            f"({ac} AC / {len(cf_subs)} envios)"
        )

    # ---- Dificuldade (CF, só problemas com rating real) ----
    rated = cf_solved[
        cf_solved["problem.rating"].notna()
        & (cf_solved["problem.rating"] < MAX_REAL_RATING)
    ]

    if len(rated):
        hardest = rated.loc[rated["problem.rating"].idxmax()]
        hardest_id = f"{hardest['problem.contestId']}{hardest['problem.index']}"

        name = hardest.get("problem.name")
        if not isinstance(name, str) or not name:
            name = codeforces.get_problem_names().get(
                (str(hardest["problem.contestId"]), str(hardest["problem.index"]))
            )

        hardest_label = f"{hardest_id} – {name}" if name else hardest_id

        lines.append(
            f"📈 Dificuldade média (CF): {rated['problem.rating'].mean():.0f} · "
            f"mais difícil: {int(hardest['problem.rating'])} ({hardest_label})"
        )

    # ---- Tópicos ----
    cf_tags = cf_solved["problem.tags"].explode().dropna()
    cses_cats = cses_solved["problem.tags"].explode().dropna()

    if len(cf_tags) or len(cses_cats):
        lines.append("")

    if len(cf_tags):
        lines.append(f"🏷️ Tópicos (CF): {_top(cf_tags.value_counts())}")

    if len(cses_cats):
        lines.append(f"📚 CSES: {_top(cses_cats.value_counts())}")

    # ---- Rating e contests ----
    lines.append("")

    info = users.iloc[0] if users is not None and not users.empty else pd.Series(dtype=object)
    cur_rating = info.get("rating")

    if pd.notna(cur_rating):
        lines.append(
            f"🧠 Rating: {int(cur_rating)} ({info.get('rank', 'unrated')}) · "
            f"máx {int(info.get('maxRating', cur_rating))}"
        )
    else:
        lines.append("🧠 Rating: unrated")

    if rating is not None and not rating.empty and "ratingUpdateTimeSeconds" in rating.columns:
        contests = rating.copy()
        contests["date"] = pd.to_datetime(
            contests["ratingUpdateTimeSeconds"], unit="s", utc=True
        ).dt.tz_convert(timezone)
        if start is not None:
            contests = contests[contests["date"] >= start]
    else:
        contests = pd.DataFrame()

    if len(contests) and start is not None:
        delta = int((contests["newRating"] - contests["oldRating"]).sum())
        lines.append(f"🏁 Contests: {len(contests)} ({delta:+d} de rating)")
    elif len(contests):
        # no histórico completo a soma é só o rating atual (o CF começa em 0)
        lines.append(f"🏁 Contests: {len(contests)}")
    else:
        lines.append("🏁 Contests: 0")

    # ---- Posição no grupo ----
    try:
        group = _group_submissions(member_handles)
        group = pd.concat(
            [group[group["handle"] != handle], subs], ignore_index=True
        )
        group["date"] = pd.to_datetime(group["date"], utc=True).dt.tz_convert(timezone)

        if start is not None:
            group = group[group["date"] >= start]

        solved_counts = _unique_solved(group).groupby("handle").size()
        day_counts = rankings.count_active_days(group, timezone)

        n_people = len(set(member_handles) | {handle})

        lines.append(
            f"🏆 No grupo: {_position(solved_counts, handle)}º em questões · "
            f"{_position(day_counts, handle)}º em dias (de {n_people})"
        )
    except Exception as e:
        print(f"[stats] Falha ao calcular posição no grupo: {e}")

    # ---- Aviso: CSES não vinculado ----
    member = members[members["codeforces"].astype(str).str.strip() == handle]

    if member.empty or member["cses_user"].isna().all():
        lines.append("")
        lines.append(
            "ℹ️ Seu usuário do CSES não está vinculado, então o CSES não "
            "entra nessas contas. Peça para cadastrarem no grupo."
        )

    return "\n".join(lines)
