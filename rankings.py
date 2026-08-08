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

    tmp = subs[subs["verdict"] == "OK"].copy()

    if tmp.empty:
        return pd.DataFrame(columns=["handle", "dias"])

    tmp["day"] = tmp["date"].dt.date

    # Dias distintos com pelo menos uma submissão OK
    dias = (
        tmp.groupby("handle")["day"]
        .nunique()
        .reset_index(name="dias")
    )

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