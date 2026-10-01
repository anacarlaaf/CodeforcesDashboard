import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
import codeforces
import cses
import db
import rankings

st.set_page_config(
    layout="wide",
    page_title="ICOMP | CP Dashboard",
    page_icon="📊"
)

tag_colors= [
    "#1f77b4", "#8ecae6", "#ff2d2d", "#ff9896",
    "#2a9d8f", "#6ede8a", "#f77f00", "#f4a261",
    "#6a4c93", "#adb5bd",
    "#339af0", "#1d3557", "#f08080", "#2d6a4f",
    "#74c69d", "#52b788", "#e76f51", "#457b9d",
    "#a8dadc", "#ffb703"
]

colors_problems = {
    "CSES": "#f4a261",
    "Gym/Unrated": "#E0E0E0",
    "<800": "#AAAAAA",
    "800–1200": "#77FF77",
    "1200–1600": "#77DDBB",
    "1600–2000": "#7777FF",
    "2000–2400": "#AA77FF",
    "2400+": "#FF7777",
}

def progress_bar_active_days(done, total, size=7):
    """
    Barra de progresso para 'dias com submissão', com emojis
    """

    if total == 0:
        return ""

    ratio = min(done / total, 1)

    filled = int(ratio * size)

    return (
        "🟢" * filled
        + "⚪" * (size - filled)
    )

@st.cache_data
def load_cses_problems(path="utils/cses_problems.csv"):
    """Mapa {task_id: {name, category, url}} dos problemas do CSES."""

    try:
        df = pd.read_csv(path, dtype={"task_id": str})
    except FileNotFoundError:
        return {}

    return df.set_index("task_id")[["name", "category", "url"]].to_dict("index")

# =============================
# SIDEBAR
# =============================

st.title("🎈 Grupo de Programação Competitiva da UFAM")

df = db.load_members_df()

handles = (
    df["codeforces"]
    .dropna()
    .astype(str)
    .str.strip()
)

handles = handles[handles != ""].tolist()

handles_input = st.sidebar.text_input(
    "Handles",
    ",".join(handles)
)

handles = [h.strip() for h in handles if h.strip()]

mode = st.sidebar.radio("Modo", ["Todos", "Individual", "Time"])

team_default = ["luanzito", "rebecamadi", "lip33"] if len(handles) >= 3 else handles + ["", "", ""]

# =============================
# INTERVALO DE DATAS
# =============================

st.sidebar.subheader("📅 Intervalo")

# Os dados ficam em UTC no banco; o fuso escolhido aqui vale para
# exibição, para os limites do período e para a contagem de dias.
TIMEZONES = [
    "America/Manaus",
    "America/Sao_Paulo",
    "America/Rio_Branco",
    "America/Noronha",
    "UTC",
]

tz = st.sidebar.selectbox("Fuso horário", TIMEZONES)

preset = st.sidebar.radio(
    "Período rápido",
    [
        "Última semana",
        "Último mês",
        "Últimos 3 meses",
        "Personalizado",
    ]
)

today = pd.Timestamp.now(tz=tz)

if preset == "Última semana":
    start = (today - datetime.timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = today.replace(hour=23, minute=59, second=59, microsecond=999999)

elif preset == "Último mês":
    start = (today - datetime.timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = today.replace(hour=23, minute=59, second=59, microsecond=999999)

elif preset == "Últimos 3 meses":
    start = (today - datetime.timedelta(days=89)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = today.replace(hour=23, minute=59, second=59, microsecond=999999)

else:
    date_range = st.sidebar.date_input(
    "Escolha o intervalo",
    [(today - datetime.timedelta(days=7)).date(), today.date()]
    )

    if isinstance(date_range, tuple) or isinstance(date_range, list):

        if len(date_range) == 2:
            start_date, end_date = date_range

        elif len(date_range) == 1:
            start_date = end_date = date_range[0]

        else:
            start_date = end_date = today.date()

    else:
        start_date = end_date = date_range

    start = pd.Timestamp(start_date).tz_localize(tz)

    end = pd.Timestamp(end_date).tz_localize(tz)
    end = end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

if st.sidebar.button("🔄 Atualizar dados"):
    st.cache_data.clear()
    st.cache_resource.clear()

    # Codeforces: limpar o cache acima já força a próxima consulta a
    # resincronizar o que for novo (ver codeforces.sync_cf_submissions).
    #
    # CSES: chamado direto aqui (não mais via GitHub Actions) — o
    # workflow update_cses.yml continua existindo só pelo cron de
    # madrugada, como sincronização automática de fundo. Um clique
    # aqui roda cses.update() na hora, na mesma sessão do Streamlit,
    # e já grava no Supabase (tabela `submissions`, source='CSES').
    
    with st.spinner("Sincronizando CSES..."):
        try:
            cses.update(problems_csv="utils/cses_problems.csv")

            st.sidebar.success(
                "Cache limpo e CSES sincronizado. "
                "Codeforces será resincronizado na próxima consulta."
            )

        except Exception as e:
            st.sidebar.warning(
                "Cache limpo — Codeforces será resincronizado na próxima "
                "consulta.\n\n"
                f"Falha ao sincronizar CSES: {e}"
            )

# =============================
# CARREGAR DADOS
# =============================

# subs já vem UNIFICADO (Codeforces + CSES juntos, lido da tabela
# `submissions` no Supabase) — não precisa mais de concat manual.
subs, rating, users = codeforces.load_data(handles=handles)

# A API do Codeforces omite rank/rating/maxRating para usuários sem
# contest rated. Se TODOS os handles forem assim, essas colunas nem
# existem no DataFrame. Garante as colunas e trata NaN em usuários unrated.
users = users.copy()
for col in ("handle", "rank", "rating", "maxRating"):
    if col not in users.columns:
        users[col] = float("nan")

users["rank"] = users["rank"].fillna("unrated")

# Colunas mínimas que o dashboard usa. Garantidas mesmo quando a API
# devolve DataFrames vazios (ex: handle sem contest rated / sem submissões),
# pois um DataFrame vazio criado a partir de lista vazia não tem colunas.
SUBS_COLUMNS = [
    "handle", "verdict", "problem.contestId", "problem.index",
    "problem.rating", "problem.tags", "source", "date",
]
RATING_COLUMNS = [
    "handle", "contestId", "ratingUpdateTimeSeconds", "newRating", "date",
]

if subs is None or subs.empty or "date" not in subs.columns:
    subs = pd.DataFrame(columns=SUBS_COLUMNS)
else:
    subs = subs.copy()

    for col in SUBS_COLUMNS:
        if col not in subs.columns:
            subs[col] = pd.NA

    subs["date"] = pd.to_datetime(subs["date"], utc=True).dt.tz_convert(tz)

if rating is None or rating.empty or "ratingUpdateTimeSeconds" not in rating.columns:
    st.info("Nenhum dado de rating disponível para os handles selecionados.")
    rating = pd.DataFrame({
        "handle": pd.Series(dtype="object"),
        "contestId": pd.Series(dtype="float64"),
        "ratingUpdateTimeSeconds": pd.Series(dtype="float64"),
        "newRating": pd.Series(dtype="float64"),
        "date": pd.Series(dtype=f"datetime64[ns, {tz}]"),
    })
else:
    rating = rating.copy()
    rating["date"] = pd.to_datetime(
        rating["ratingUpdateTimeSeconds"], unit="s", utc=True
    ).dt.tz_convert(tz)

# =============================
# FILTROS
# =============================

# Histórico completo, sem o filtro de período — usado pra contar os
# WAs antes de um accept mesmo quando eles caem antes do intervalo.
all_subs = subs

subs = subs[
    (subs["date"] >= start)
    & (subs["date"] <= end)
]

rating = rating[
    (rating["date"] >= start)
    & (rating["date"] <= end)
]

solved = subs[
    subs["verdict"] == "OK"
]

unique_solved = solved.drop_duplicates(
    [
        "handle",
        "problem.contestId",
        "problem.index",
    ]
).copy()

# =============================
# MODO TODOS
# =============================

if mode == "Todos":

    st.header("👥 Visão de Todos")

    # KPI
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("👥 Usuários", users.shape[0])
    col2.metric("📩 Submissões", subs.shape[0])
    col3.metric("🧩 Problemas resolvidos", unique_solved.shape[0])
    col4.metric("🏁 Contests", rating["contestId"].nunique())  # corrigido

    # =============================
    # DESTAQUES DO PERÍODO (top 3)
    # =============================

    st.subheader("🥇 Destaques do período")

    medals = ["🥇", "🥈", "🥉"]

    def render_ranking_table(col, title, df, value_col):
        with col:
            st.markdown(f"**{title}**")

            if df.empty:
                st.caption("Sem dados no período.")
                return

            df = df.reset_index(drop=True)

            df.insert(
                0,
                "#",
                [
                    medals[i] if i < len(medals) else str(i + 1)
                    for i in range(len(df))
                ],
            )

            df = df.rename(
                columns={"handle": "Handle", value_col: value_col.capitalize()}
            )

            st.dataframe(
                df,
                hide_index=True,
                width="stretch",
                height=140,  # mostra ~3 linhas, resto acessível via scroll
            )

    rk_col1, rk_col2, rk_col3, rk_col4 = st.columns(4)

    render_ranking_table(
        rk_col1,
        "Mais questões no total",
        rankings.top_total_solved(unique_solved, n=len(handles)),
        "questões",
    )

    render_ranking_table(
        rk_col2,
        "Mais questões no Codeforces",
        rankings.top_codeforces_solved(unique_solved, n=len(handles)),
        "questões",
    )

    render_ranking_table(
        rk_col3,
        "Mais questões no CSES",
        rankings.top_cses_solved(unique_solved, n=len(handles)),
        "questões",
    )

    render_ranking_table(
        rk_col4,
        "Maior frequência",
        rankings.top_frequency(subs, unique_solved, n=len(handles)),
        "dias",
    )

    # Ranking
    st.subheader("🏆 Ranking por quantidade de questões")

    # Problemas resolvidos por usuário
    solved_count = (
        unique_solved.groupby("handle")
        .size()
        .rename("problems_solved")
    )

    # Contests oficiais por usuário
    contest_count = (
        rating.groupby("handle")
        .size()
        .rename("official_contests")
    )

    # Merge com users
    ranking = users.merge(
        solved_count, on="handle", how="left"
    ).merge(
        contest_count, on="handle", how="left"
    )

    # Preencher NaN com 0
    ranking["problems_solved"] = ranking["problems_solved"].fillna(0).astype(int)
    ranking["official_contests"] = ranking["official_contests"].fillna(0).astype(int)

    total_days = (end - start).days
    total_months = total_days // 30
    target_contests = max(2, int(total_months * 2))

    # Dias distintos com pelo menos uma submissão (CF + CSES) no período
    active_days_count = (
        subs.assign(day=subs["date"].dt.date)
        .groupby("handle")["day"]
        .nunique()
    )

    ranking["active_days"] = (
        ranking["handle"]
        .map(active_days_count)
        .fillna(0)
        .astype(int)
    )

    max_digits_problems = len(str(ranking["problems_solved"].max()))
    max_digits_contests = len(str(target_contests))
    max_digits_active_days = len(str(ranking["active_days"].max()))

    ranking["problems"] = ranking["problems_solved"].apply(
        lambda x: f"{str(x).rjust(max_digits_problems, "\u2007")}/{total_days}  {codeforces.progress_bar_scaled(x, total_days)}"
    )

    ranking["contests"] = ranking["official_contests"].apply(
        lambda x: f"{str(x).rjust(max_digits_contests, "\u2007")}/{target_contests}  {codeforces.progress_bar_scaled(x, target_contests, 2)}"
    )

    ranking["days_active"] = ranking["active_days"].apply(
        lambda x: f"{str(x).rjust(max_digits_active_days, "\u2007")}/{total_days}  {progress_bar_active_days(x, total_days)}"
    )

    # Ordenar por problemas resolvidos
    ranking = ranking.sort_values(
        ["problems_solved", "active_days"],
        ascending=[False, False]
    )[
        [
            "handle",
            "rank",
            "problems",
            "days_active",
            "contests",
        ]
    ]

    # Renomear para exibição
    ranking = ranking.rename(columns={
        "handle": "Handle",
        "rank": "Rank",
        "problems": "Problems",
        "days_active": "Dias Ativos",
        "contests": "Contests"
    })

    styled = ranking.style.map(
        codeforces.cf_rank_color,
        subset=["Rank"]
    )

    st.dataframe(styled, width="stretch")

    # ======================================================
    # PROBLEMAS RESOLVIDOS POR USUÁRIO (POR DIFICULDADE)
    # ======================================================

    st.subheader("🧩 Problemas resolvidos por usuário (por dificuldade)")

    # --- Identificar problemas Gym ---
    # Antes disso dependia de um valor sentinela (-1) escrito nas
    # submissões do CSES pra "enganar" essa checagem. Agora que a
    # tabela unificada tem uma coluna `source` explícita, usamos ela
    # direto: linhas do CSES nunca contam como gym, independente do
    # rating (que é sempre NULL pra elas).
    unique_solved["is_gym"] = (
        (unique_solved["source"] != "CSES")
        & (
            unique_solved["problem.rating"].isna()
            | (unique_solved["problem.rating"] >= 100000)
        )
    )

    # --- Separar dados ---
    diff_df = unique_solved[~unique_solved["is_gym"]].copy()

    # Apenas gym
    gym_df = unique_solved[unique_solved["is_gym"]].copy()

    if diff_df.empty and gym_df.empty:
        st.info("Sem dados no período.")
    else:

        # =============================
        # FAIXAS DE DIFICULDADE
        # =============================

        labels = [
            "CSES",
            "<800",
            "800–1200",
            "1200–1600",
            "1600–2000",
            "2000–2400",
            "2400+",
        ]

        diff_df["difficulty"] = "CSES"

        mask_cf = diff_df["problem.rating"] >= 0

        diff_df.loc[mask_cf, "difficulty"] = pd.cut(
            diff_df.loc[mask_cf, "problem.rating"],
            bins=[0, 800, 1200, 1600, 2000, 2400, 5000],
            labels=labels[1:],
            right=False,      # 0–799
        )

        # Pivot: problemas por usuário por dificuldade
        pivot = (
            diff_df
            .groupby(["handle", "difficulty"], observed=False)
            .size()
            .unstack(fill_value=0)
        )

        pivot = pivot.reindex(
            columns=labels,
            fill_value=0
        )

        # Garantir todos os handles
        for h in handles:
            if h not in pivot.index:
                pivot.loc[h] = 0

        pivot = pivot.sort_index()

        pivot = pivot.reindex(
            columns=labels,
            fill_value=0
        )

        # =============================
        # CONTAGEM DE GYM
        # =============================

        gym_counts = gym_df.groupby("handle").size()
        gym_counts = gym_counts.reindex(handles, fill_value=0)
        gym_counts = gym_counts.sort_index()

        # =============================
        # GRÁFICO
        # =============================

        fig = go.Figure()

        # Barras por dificuldade
        for d in labels:
            fig.add_bar(
                x=pivot.index,
                y=pivot[d],
                name=d,
                marker_color=colors_problems.get(d)
            )

        # Barra Gym (branca + textura cinza)
        fig.add_bar(
            x=gym_counts.index,
            y=gym_counts.values,
            name="gym/unrated",
            marker=dict(
                color="white",
                pattern=dict(
                    shape="/",
                    fgcolor="gray"
                )
            )
        )

        fig.update_layout(
            barmode="stack",
            xaxis_title="Usuário",
            yaxis_title="Problemas resolvidos",
            height=500
        )

        st.plotly_chart(fig, width='stretch')

# =============================
# MODO INDIVIDUAL
# =============================

elif mode == "Individual":

    st.header("👤 Visão Individual")

    user = st.selectbox("Usuário", handles)

    u_subs = subs[subs["handle"] == user]
    u_solved = unique_solved[unique_solved["handle"] == user]
    u_rating = rating[rating["handle"] == user]

    info = users[users["handle"] == user].iloc[0]

    # =============================
    # LINK PARA O PERFIL
    # =============================

    profile_url = f"https://codeforces.com/profile/{user}"
    rank = info["rank"]

    color_map = {
        "newbie": "#808080",
        "pupil": "#008000",
        "specialist": "#03A89E",
        "expert": "#0000FF",
        "candidate master": "#AA00AA",
        "master": "#FF8C00",
        "international master": "#FF8C00",
        "grandmaster": "#FF0000",
        "international grandmaster": "#CC0000",
        "legendary grandmaster": "#AA0000",
    }


    if isinstance(rank, str):
        color = color_map.get(rank.lower(), "black")
    else:
        color = "black"
        rank = "unrated"

    st.markdown(
        f'### 🔗 Perfil no Codeforces: <a href="{profile_url}" target="_blank" style="color:{color}; font-weight:700;">{user}</a> <span style="color:gray;">({rank})</span>',
        unsafe_allow_html=True
    )

    # =============================
    # KPIs
    # =============================

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "🧠 Rating atual",
        "-" if pd.isna(info.get("rating")) else int(info["rating"])
    )

    col2.metric(
        "🏆 Rating máximo",
        "-" if pd.isna(info.get("maxRating")) else int(info["maxRating"])
    )
    col3.metric("🧩 Problemas resolvidos", u_solved.shape[0])
    col4.metric("🏁 Contests", u_rating.shape[0])

    # Dificuldade
    st.subheader("🧠 Distribuição por dificuldade")

    labels = [
        "CSES",
        "Gym/Unrated",
        "<800",
        "800–1200",
        "1200–1600",
        "1600–2000",
        "2000–2400",
        "2400+",
    ]

    diff = u_solved.copy()

    # padrão = Gym
    diff["difficulty"] = "Gym/Unrated"

    # CSES — antes checava problem.rating == -1 (sentinela); agora
    # usa a coluna `source`, que é explícita e não depende de nenhum
    # valor mágico.
    diff.loc[
        diff["source"] == "CSES",
        "difficulty"
    ] = "CSES"

    # Problemas normais CF
    mask_cf = (
        (diff["source"] != "CSES")
        & diff["problem.rating"].notna()
        & (diff["problem.rating"] >= 0)
    )

    diff.loc[mask_cf, "difficulty"] = pd.cut(
        diff.loc[mask_cf, "problem.rating"],
        bins=[0, 800, 1200, 1600, 2000, 2400, 5000],
        labels=labels[2:],   # começa em <800
        right=False,
    )

    if not diff.empty:

        pie = (
            diff["difficulty"]
            .value_counts()
            .reindex(labels, fill_value=0)
        )

        pie = pie[pie > 0]

        pie_colors = [
            colors_problems.get(label, "#DDDDDD")
            for label in pie.index
        ]

        fig = go.Figure(
            data=[
                go.Pie(
                    labels=pie.index,
                    values=pie.values,
                    marker=dict(colors=pie_colors)
                )
            ]
        )

        st.plotly_chart(fig, width="stretch")

        # =============================
        # TIPOS DE PROBLEMAS RESOLVIDOS
        # =============================

        st.subheader("🏷️ Tipos de problemas resolvidos")

        tag_rows = []

        for _, row in u_solved.iterrows():

            # -------------------------
            # CSES — identificado pela coluna `source`, não mais por
            # um rating sentinela (-1).
            # -------------------------
            if row.get("source") == "CSES":
                tag_rows.append({"tag": "CSES"})
                continue

            prob_rating = row.get("problem.rating")

            # -------------------------
            # Gym / Unrated
            # -------------------------
            if pd.isna(prob_rating) or prob_rating >= 100000:
                tag_rows.append({"tag": "Gym/Unrated"})
                continue

            # -------------------------
            # Problemas normais CF
            # -------------------------
            tags = row.get("problem.tags")

            if isinstance(tags, list) and len(tags) > 0:
                for tag in tags:
                    tag_rows.append({"tag": tag})
            else:
                tag_rows.append({"tag": "Sem tags"})

        tags_df = pd.DataFrame(tag_rows)

        if tags_df.empty:
            st.info("Sem dados de tags no período.")
        else:

            tag_counts = tag_df = (
                tags_df["tag"]
                .value_counts()
                .sort_values(ascending=False)
            )

            colors = [
                "#f4a261" if tag == "CSES"
                else "#E0E0E0" if tag == "Gym/Unrated"
                else tag_colors[i % len(tag_colors)]
                for i, tag in enumerate(tag_counts.index)
            ]

            fig_tags = go.Figure(
                data=[
                    go.Bar(
                        x=tag_counts.index,
                        y=tag_counts.values,
                        text=tag_counts.values,
                        textposition="outside",
                        marker=dict(color=colors)
                    )
                ]
            )

            fig_tags.update_layout(
                xaxis_title="Tag",
                yaxis_title="Quantidade de problemas",
                height=500
            )

            st.plotly_chart(fig_tags, width="stretch")

            st.dataframe(
                pd.DataFrame({
                    "Tag": tag_counts.index,
                    "Questões": tag_counts.values
                }).reset_index(drop=True),
                width="stretch",
            )

    # =============================
    # SUBMISSÕES DO USUÁRIO
    # =============================

    st.subheader("📜 Submissões")

    f_col1, f_col2 = st.columns(2)

    platform_filter = f_col1.multiselect(
        "Plataforma",
        ["Codeforces", "CSES"],
        default=["Codeforces", "CSES"],
    )

    show_rejected = f_col2.toggle(
        "Mostrar submissões não aceitas (WA, TLE...)",
        value=False,
    )

    # -----------------------------
    # WAs ATÉ O ACCEPT
    # -----------------------------
    # Para cada accept, conta as submissões rejeitadas no mesmo
    # problema desde o accept anterior (ou desde o início). Usa o
    # histórico completo, então WAs anteriores ao período também
    # contam. Compilation error não conta (mesma regra de penalidade
    # do Codeforces). CSES só guarda accepts, então fica vazio.

    hist = all_subs[
        (all_subs["handle"] == user)
        & (all_subs["source"] == "CF")
    ].sort_values("date")

    problem_key = [
        hist["problem.contestId"].astype(str),
        hist["problem.index"].astype(str),
    ]

    is_ac = hist["verdict"] == "OK"
    is_fail = ~hist["verdict"].isin(["OK", "COMPILATION_ERROR", "TESTING"])

    # segmento = nº de accepts anteriores no problema; o próprio
    # accept fica no mesmo segmento das falhas que o precederam
    segment = is_ac.groupby(problem_key).cumsum() - is_ac

    wa_before = (
        is_fail
        .groupby(problem_key + [segment])
        .transform("sum")
        [is_ac]
    )

    table = u_subs.copy()

    if not show_rejected:
        table = table[table["verdict"] == "OK"]

    table["platform"] = table["source"].map(
        {"CF": "Codeforces", "CSES": "CSES"}
    )

    table = table[table["platform"].isin(platform_filter)]

    if table.empty:
        st.info("Sem submissões no período.")
    else:

        cf_names = codeforces.get_problem_names()
        cses_problems = load_cses_problems()

        def problem_details(row):
            cid = str(row["problem.contestId"])
            idx = str(row["problem.index"])

            # CSES — nome, categoria e link vêm do CSV de problemas
            if row["source"] == "CSES":
                p = cses_problems.get(idx, {})
                return pd.Series({
                    "problem_id": f"CSES {idx}",
                    "name": p.get("name", "-"),
                    "problem_url": p.get(
                        "url", f"https://cses.fi/problemset/task/{idx}"
                    ),
                })

            # Codeforces — nome salvo no banco (vem do user.status,
            # cobre gym/mashup); problemset como fallback para linhas
            # ainda sem backfill. contestId >= 100000 é gym.
            name = row.get("problem.name")

            if not isinstance(name, str) or not name:
                name = cf_names.get((cid, idx), "-")

            is_gym = cid.isdigit() and int(cid) >= 100000
            kind = "gym" if is_gym else "contest"

            return pd.Series({
                "problem_id": f"{cid}{idx}",
                "name": name,
                "problem_url": f"https://codeforces.com/{kind}/{cid}/problem/{idx}",
            })

        table = pd.concat(
            [table, table.apply(problem_details, axis=1)],
            axis=1,
        )

        table["wa_before"] = table.index.map(wa_before).astype("Int64")

        def difficulty_label(row):
            if row["source"] == "CSES":
                return "CSES"

            r = row["problem.rating"]

            if pd.isna(r) or r >= 100000:
                return "Gym/Unrated"

            return str(int(r))

        table["difficulty"] = table.apply(difficulty_label, axis=1)

        table["topics"] = table["problem.tags"].apply(
            lambda t: ", ".join(t) if isinstance(t, list) and t else "-"
        )

        verdict_labels = {
            "OK": "✅ Aceito",
            "WRONG_ANSWER": "❌ Wrong Answer",
            "TIME_LIMIT_EXCEEDED": "⏱️ Time Limit",
            "MEMORY_LIMIT_EXCEEDED": "💾 Memory Limit",
            "RUNTIME_ERROR": "💥 Runtime Error",
            "COMPILATION_ERROR": "🛠️ Compilation Error",
            "IDLENESS_LIMIT_EXCEEDED": "⏱️ Idleness Limit",
            "CHALLENGED": "🎯 Hackeado",
            "SKIPPED": "⏭️ Skipped",
            "PARTIAL": "◐ Parcial",
            "TESTING": "⏳ Em teste",
        }

        table["verdict_label"] = table["verdict"].map(
            lambda v: verdict_labels.get(v, v)
        )

        table = table.sort_values("date", ascending=False)

        st.caption(
            f"{len(table)} submissões · "
            f"{table.loc[table['verdict'] == 'OK', 'problem_id'].nunique()} problemas distintos aceitos"
        )

        st.dataframe(
            table[[
                "date",
                "platform",
                "problem_id",
                "name",
                "difficulty",
                "topics",
                "verdict_label",
                "wa_before",
                "problem_url",
            ]],
            hide_index=True,
            width="stretch",
            column_config={
                "date": st.column_config.DatetimeColumn(
                    "Data", format="DD/MM/YYYY HH:mm"
                ),
                "platform": "Plataforma",
                "problem_id": "ID",
                "name": "Problema",
                "difficulty": "Dificuldade",
                "topics": "Tópicos",
                "verdict_label": "Veredito",
                "wa_before": st.column_config.NumberColumn(
                    "WAs até AC",
                    help="Submissões rejeitadas no problema antes deste accept "
                         "(sem contar compilation error)",
                ),
                "problem_url": st.column_config.LinkColumn(
                    "Enunciado", display_text="abrir"
                ),
            },
        )
# =============================
# MODO TIME
# =============================

else:
    st.header("👥 Visão de Time")

    st.subheader("👤 Seleção do Time")

    col1, col2, col3 = st.columns(3)

    inputs = []
    cols = [col1, col2, col3]

    for i in range(3):
        with cols[i]:
            h = st.text_input(
                f"Handle {i+1}",
                value=team_default[i],
                key=f"team_{i}"
            )
            inputs.append(h)

    team_handles = [h.strip() for h in inputs if h.strip()]

    # evitar vazio
    if not team_handles:
        st.warning("Adicione pelo menos um handle no time.")
        st.stop()

    # =============================
    # FILTRO DO TIME
    # =============================

    team_users = users[users["handle"].isin(team_handles)]
    team_rating = rating[rating["handle"].isin(team_handles)]
    team_solved = unique_solved[unique_solved["handle"].isin(team_handles)]

    # =============================
    # TABELA
    # =============================

    st.subheader("🏆 Ranking do Time")

    # Problemas resolvidos por usuário
    solved_count = (
        team_solved.groupby("handle")
        .size()
        .rename("problems_solved")
    )

    # Contests oficiais por usuário
    contest_count = (
        team_rating.groupby("handle")
        .size()
        .rename("official_contests")
    )

    ranking = team_users.merge(
        solved_count, on="handle", how="left"
    ).merge(
        contest_count, on="handle", how="left"
    )

    ranking["rating"] = ranking["rating"].fillna(0).astype(int)
    ranking["maxRating"] = ranking["maxRating"].fillna(0).astype(int)

    # Garantir que todos os handles apareçam
    ranking = ranking.set_index("handle").reindex(team_handles).reset_index()

    ranking["problems_solved"] = ranking["problems_solved"].fillna(0).astype(int)
    ranking["official_contests"] = ranking["official_contests"].fillna(0).astype(int)

    total_days = (end - start).days
    total_months = total_days // 30
    target_contests = max(2, int(total_months * 2))

    max_digits_problems = len(str(ranking["problems_solved"].max()))
    max_digits_contests = len(str(target_contests))

    ranking["problems"] = ranking["problems_solved"].apply(
        lambda x: f"{str(x).rjust(max_digits_problems, '\u2007')}/{total_days}  {codeforces.progress_bar_scaled(x, total_days)}"
    )

    ranking["contests"] = ranking["official_contests"].apply(
        lambda x: f"{str(x).rjust(max_digits_contests, '\u2007')}/{target_contests}  {codeforces.progress_bar_scaled(x, target_contests, 2)}"
    )

    ranking = ranking.sort_values("rating", ascending=False)[
        [
            "handle",
            "rating",
            "maxRating",
            "rank",
            "problems",
            "contests",
        ]
    ]

    ranking = ranking.rename(columns={
        "handle": "Handle",
        "rating": "Rating",
        "maxRating": "Max Rating",
        "rank": "Rank",
        "problems": "Problems",
        "contests": "Contests"
    })

    styled = ranking.style.map(
        codeforces.cf_rank_color,
        subset=["Rank"]
    )

    st.dataframe(styled, width="stretch")

    # =============================
    # TAGS (AGREGADO DO TIME)
    # =============================

    st.subheader("🏷️ Tipos de problemas resolvidos")

    tag_rows = []

    for _, row in team_solved.iterrows():

        # CSES — identificado pela coluna `source`, não mais por um
        # rating sentinela (-1).
        if row.get("source") == "CSES":
            tag_rows.append({"tag": "CSES"})
            continue

        tags = row.get("problem.tags")

        # Tags normais do CF
        if isinstance(tags, list) and len(tags) > 0:
            for tag in tags:
                tag_rows.append({"tag": tag})

        # Gym/unrated ou problemas sem tags
        else:
            tag_rows.append({"tag": "Sem tags"})

    tags_df = pd.DataFrame(tag_rows)

    if tags_df.empty:
        st.info("Sem dados no período.")
    else:

        tag_counts = tags_df["tag"].value_counts()

        colors = [
            tag_colors[i % len(tag_colors)]
            for i in range(len(tag_counts))
        ]

        fig = go.Figure(
            data=[
                go.Bar(
                    x=tag_counts.index,
                    y=tag_counts.values,
                    text=tag_counts.values,
                    textposition="outside",
                    marker=dict(color=colors)
                )
            ]
        )

        fig.update_layout(
            xaxis_title="Tag",
            yaxis_title="Quantidade de problemas",
            height=500
        )

        st.plotly_chart(fig, width="stretch")