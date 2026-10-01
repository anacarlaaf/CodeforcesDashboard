import pandas as pd


def top_total_solved(unique_solved: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """
    Handles com mais questões resolvidas no total (Codeforces + CSES),
    considerando apenas o período/handles já filtrados em `unique_solved`.
    """

    if unique_solved.empty:
        return pd.DataFrame(columns=["handle", "questões"])

    counts = (
        unique_solved
        .groupby("handle")
        .size()
        .rename("questões")
        .sort_values(ascending=False)
    )

    return counts.head(n).reset_index()


def top_codeforces_solved(unique_solved: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """
    Handles com mais questões resolvidas apenas no Codeforces.
    """

    if unique_solved.empty:
        return pd.DataFrame(columns=["handle", "questões"])

    cf = unique_solved[unique_solved["source"] != "CSES"]

    counts = (
        cf
        .groupby("handle")
        .size()
        .rename("questões")
        .sort_values(ascending=False)
    )

    return counts.head(n).reset_index()


def top_cses_solved(unique_solved: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """
    Handles com mais questões resolvidas apenas no CSES.
    """

    if unique_solved.empty:
        return pd.DataFrame(columns=["handle", "questões"])

    cses_df = unique_solved[unique_solved["source"] == "CSES"]

    counts = (
        cses_df
        .groupby("handle")
        .size()
        .rename("questões")
        .sort_values(ascending=False)
    )

    return counts.head(n).reset_index()


def top_frequency(
    subs: pd.DataFrame,
    unique_solved: pd.DataFrame,
    n: int = 3
) -> pd.DataFrame:
    """
    Handles com mais dias distintos em que houve pelo menos uma
    submissão ACEITA (verdict == "OK"), seja no Codeforces ou no CSES,
    no período filtrado.

    Em caso de empate na quantidade de dias, desempata pela quantidade
    total de questões resolvidas no mesmo período.
    """

    n = int(n)

    if subs.empty:
        return pd.DataFrame(columns=["handle", "dias"])

    # Dias distintos com pelo menos uma submissão OK, no mesmo fuso em
    # que as datas de `subs` já estão
    dias = (
        count_active_days(subs, str(subs["date"].dt.tz))
        .reset_index(name="dias")
    )

    if dias.empty:
        return pd.DataFrame(columns=["handle", "dias"])

    # Questões resolvidas no período, para desempate
    if unique_solved is None or unique_solved.empty:
        questoes = pd.DataFrame({
            "handle": dias["handle"],
            "questões": 0
        })
    else:
        questoes = (
            unique_solved.groupby("handle")
            .size()
            .reset_index(name="questões")
        )

    # Merge explícito pelo handle
    result = dias.merge(
        questoes,
        on="handle",
        how="left"
    )

    result["dias"] = result["dias"].fillna(0).astype(int)
    result["questões"] = result["questões"].fillna(0).astype(int)

    # Primeiro: mais dias
    # Segundo: mais questões resolvidas
    result = result.sort_values(
        ["dias", "questões"],
        ascending=[False, False]
    )

    return result.head(n)[
        ["handle", "dias"]
    ].reset_index(drop=True)

# -----------------------------------
# DIAS ATIVOS / OFENSIVA
# -----------------------------------
#
# Regra única para dashboard, bot e ranking: um dia é "ativo" quando
# tem pelo menos uma submissão ACEITA (verdict == "OK"), no Codeforces
# ou no CSES, contando o dia de calendário no fuso informado. A
# ofensiva funciona como a do Duolingo: dias ativos consecutivos até
# hoje. Se hoje ainda não teve accept, a ofensiva de ontem continua
# valendo (ainda dá tempo de mantê-la); ela só zera quando um dia
# inteiro passa sem accept.


def active_days(subs: pd.DataFrame, tz: str) -> pd.DataFrame:
    """Pares (handle, day) distintos com pelo menos um accept, com
    `day` sendo a data local no fuso `tz`."""

    if subs.empty:
        return pd.DataFrame(columns=["handle", "day"])

    ok = subs[subs["verdict"] == "OK"]

    return (
        pd.DataFrame({
            "handle": ok["handle"],
            "day": pd.to_datetime(ok["date"], utc=True).dt.tz_convert(tz).dt.date,
        })
        .drop_duplicates()
        .reset_index(drop=True)
    )


def count_active_days(subs: pd.DataFrame, tz: str) -> pd.Series:
    """Quantidade de dias ativos por handle (no período de `subs`)."""

    return active_days(subs, tz).groupby("handle")["day"].nunique()


def streaks(subs: pd.DataFrame, tz: str, today=None) -> pd.DataFrame:
    """
    Ofensiva por handle, a partir do histórico COMPLETO de submissões
    (não filtrar por período, senão a ofensiva é cortada no início do
    intervalo).

    Colunas:
      - current: ofensiva atual (dias consecutivos até hoje ou ontem)
      - longest: maior ofensiva já registrada
      - active_today: se já teve accept hoje
    """

    if today is None:
        today = pd.Timestamp.now(tz=tz).date()

    days = active_days(subs, tz)
    days = days[days["day"] <= today]

    rows = []

    for handle, group in days.groupby("handle"):

        ordinals = sorted(d.toordinal() for d in group["day"])

        longest = run = 1

        for prev, cur in zip(ordinals, ordinals[1:]):
            run = run + 1 if cur == prev + 1 else 1
            longest = max(longest, run)

        # `run` agora é a sequência que termina no último dia ativo
        last = ordinals[-1]
        gap = today.toordinal() - last

        rows.append({
            "handle": handle,
            "current": run if gap <= 1 else 0,
            "longest": longest,
            "active_today": gap == 0,
        })

    return pd.DataFrame(
        rows, columns=["handle", "current", "longest", "active_today"]
    ).set_index("handle")
