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


def top_frequency(subs: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """
    Handles com mais dias distintos em que houve pelo menos uma
    submissão (aceita ou não) no período filtrado.
    """

    if subs.empty:
        return pd.DataFrame(columns=["handle", "dias"])

    tmp = subs.copy()
    tmp["day"] = tmp["date"].dt.date

    counts = (
        tmp
        .groupby("handle")["day"]
        .nunique()
        .rename("dias")
        .sort_values(ascending=False)
    )

    return counts.head(n).reset_index()