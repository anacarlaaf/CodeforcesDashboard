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


def top_frequency(subs: pd.DataFrame, unique_solved: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """
    Handles com mais dias distintos em que houve pelo menos uma
    submissão ACEITA (verdict == "OK"), seja no Codeforces ou no CSES,
    no período filtrado.

    Em caso de empate na quantidade de dias, desempata pela quantidade
    total de questões resolvidas no mesmo período (`unique_solved`,
    já deduplicado por handle+problema como usado em `top_total_solved`).
    """

    if subs.empty:
        return pd.DataFrame(columns=["handle", "dias"])

    tmp = subs[subs["verdict"] == "OK"].copy()

    if tmp.empty:
        return pd.DataFrame(columns=["handle", "dias"])

    tmp["day"] = tmp["date"].dt.date

    dias = (
        tmp
        .groupby("handle")["day"]
        .nunique()
        .rename("dias")
    )

    # total de questões resolvidas no período, por handle (critério de desempate)
    if unique_solved is None or unique_solved.empty:
        questoes = pd.Series(0, index=dias.index, name="questões")
    else:
        questoes = (
            unique_solved
            .groupby("handle")
            .size()
            .rename("questões")
        )

    result = (
        pd.concat([dias, questoes], axis=1)
        .fillna(0)
    )

    result["dias"] = result["dias"].astype(int)
    result["questões"] = result["questões"].astype(int)

    result = result.sort_values(
        ["dias", "questões"],
        ascending=[False, False],
    )

    return result.head(n).reset_index()