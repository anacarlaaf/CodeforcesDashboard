import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import datetime

st.set_page_config(layout="wide")

# =============================
# 🔧 API
# =============================

BASE = "https://codeforces.com/api/"

@st.cache_data(ttl=3600)
def cf_request(method, params):
    r = requests.get(BASE + method, params=params)
    return r.json()["result"]

@st.cache_data(ttl=3600)
def load_data(handles):
    all_subs = []
    all_rating = []
    users = []

    for h in handles:
        info = cf_request("user.info", {"handles": h})[0]
        users.append(info)

        subs = cf_request("user.status", {"handle": h, "count": 1000})
        for s in subs:
            s["handle"] = h
        all_subs.extend(subs)

        rating = cf_request("user.rating", {"handle": h})
        for r in rating:
            r["handle"] = h
        all_rating.extend(rating)

    subs_df = pd.json_normalize(all_subs)
    rating_df = pd.DataFrame(all_rating)
    users_df = pd.DataFrame(users)

    return subs_df, rating_df, users_df

def cf_rank_color(rank):
    colors = {
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
        return f"color: {colors.get(rank.lower(), 'black')}; font-weight: bold;"
    return ""


# =============================
# 🔥 FUNÇÃO HEATMAP GITHUB
# =============================
def github_heatmap(df, title="Atividade"):

    if df.empty:
        st.info("Sem dados no período.")
        return

    daily = (
        df.groupby(df["date"].dt.date)
        .size()
        .rename("count")
        .to_frame()
    )

    full_range = pd.date_range(
        daily.index.min(), daily.index.max(), freq="D"
    )

    daily = daily.reindex(full_range, fill_value=0)

    heatmap_df = pd.DataFrame({
        "date": daily.index,
        "count": daily["count"].values
    })

    heatmap_df["weekday"] = heatmap_df["date"].dt.weekday
    heatmap_df["week"] = heatmap_df["date"].dt.isocalendar().week

    fig = go.Figure(data=go.Heatmap(
        x=heatmap_df["week"],
        y=heatmap_df["weekday"],
        z=heatmap_df["count"],
        colorscale="Greens",
        showscale=False
    ))

    fig.update_yaxes(
        scaleanchor="x",
        scaleratio=1
    )

    fig.update_layout(
        title=title,
        height=300,
        margin=dict(l=0, r=0, t=40, b=0),
        xaxis=dict(showgrid=False),
        yaxis=dict(
            showgrid=False,
            tickmode="array",
            tickvals=[0,1,2,3,4,5,6],
            ticktext=["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        )
    )

    st.plotly_chart(fig, use_container_width=True)


# =============================
# 🎛️ SIDEBAR
# =============================

st.title("📊 Codeforces")

handles_input = st.sidebar.text_input(
    "Handles (separados por vírgula)",
    "anacarlaaf,luanzito,rebecamadi,lip33"
)

handles = [h.strip() for h in handles_input.split(",") if h.strip()]

mode = st.sidebar.radio("Modo", ["Todos", "Individual"])

# =============================
# 📅 INTERVALO DE DATAS
# =============================

st.sidebar.subheader("📅 Intervalo")

preset = st.sidebar.radio(
    "Período rápido",
    [
        "Última semana",
        "Último mês",
        "Últimos 3 meses",
        "Personalizado",
    ]
)

today = datetime.datetime.now()

if preset == "Última semana":
    start = today - datetime.timedelta(days=7)
    end = today

elif preset == "Último mês":
    start = today - datetime.timedelta(days=30)
    end = today

elif preset == "Últimos 3 meses":
    start = today - datetime.timedelta(days=90)
    end = today

else:
    date_range = st.sidebar.date_input(
        "Escolha o intervalo",
        [today - datetime.timedelta(days=7), today]
    )

    start = pd.to_datetime(date_range[0])
    end = pd.to_datetime(date_range[1])

start = pd.to_datetime(start)
end = pd.to_datetime(end)

if st.sidebar.button("🔄 Atualizar dados"):
    st.cache_data.clear()

# =============================
# 📥 CARREGAR DADOS
# =============================

subs, rating, users = load_data(handles)

subs["date"] = pd.to_datetime(subs["creationTimeSeconds"], unit="s")
rating["date"] = pd.to_datetime(rating["ratingUpdateTimeSeconds"], unit="s")

# 🔎 Filtrar submissões
subs = subs[(subs["date"] >= start) & (subs["date"] <= end)]

# 🔎 Filtrar contests oficiais pelo mesmo período
rating = rating[(rating["date"] >= start) & (rating["date"] <= end)]

solved = subs[subs["verdict"] == "OK"]

unique_solved = solved.drop_duplicates(
    ["handle", "problem.contestId", "problem.index"]
)

# =============================
# 👥 MODO TODOS
# =============================

if mode == "Todos":

    st.header("👥 Visão de Todos")

    # ✅ KPI da equipe
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("👥 Usuários", users.shape[0])
    col2.metric("📩 Submissões", subs.shape[0])
    col3.metric("🧩 Problemas resolvidos", unique_solved.shape[0])
    col4.metric("🏁 Contests", rating["contestId"].nunique())  # corrigido

    # Ranking
    st.subheader("🏆 Ranking por Rating")

    # 🧩 Problemas resolvidos por usuário
    solved_count = (
        unique_solved.groupby("handle")
        .size()
        .rename("problems_solved")
    )

    # 🏁 Contests oficiais por usuário (já filtrados pelo período)
    contest_count = (
        rating.groupby("handle")
        .size()
        .rename("official_contests")
    )

    # 🔗 Merge com users
    ranking = users.merge(
        solved_count, on="handle", how="left"
    ).merge(
        contest_count, on="handle", how="left"
    )

    # Preencher NaN com 0
    ranking["problems_solved"] = ranking["problems_solved"].fillna(0).astype(int)
    ranking["official_contests"] = ranking["official_contests"].fillna(0).astype(int)

    # Ordenar por rating
    ranking = ranking.sort_values("rating", ascending=False)[
        [
            "handle",
            "rating",
            "maxRating",
            "rank",
            "problems_solved",
            "official_contests",
        ]
    ]

    # 🔥 Estilo das cores do rank
    styled = ranking.style.map(
        cf_rank_color,
        subset=["rank"]
    )

    st.dataframe(styled, use_container_width=True)

    # =============================
    # 🧩 PROBLEMAS RESOLVIDOS POR USUÁRIO (POR DIFICULDADE)
    # =============================

    st.subheader("🧩 Problemas resolvidos por usuário (por dificuldade)")

    diff_df = unique_solved.dropna(subset=["problem.rating"]).copy()

    if diff_df.empty:
        st.info("Sem dados de dificuldade no período.")
    else:
        bins = [0, 800, 1200, 1600, 2000, 2400, 5000]
        labels = ["<800", "800–1200", "1200–1600",
                  "1600–2000", "2000–2400", "2400+"]

        diff_df["difficulty"] = pd.cut(
            diff_df["problem.rating"],
            bins=bins,
            labels=labels
        )

        pivot = (
            diff_df
            .groupby(["handle", "difficulty"])
            .size()
            .unstack(fill_value=0)
        )

        colors = {
            "<800": "#AAAAAA",
            "800–1200": "#77FF77",
            "1200–1600": "#77DDBB",
            "1600–2000": "#7777FF",
            "2000–2400": "#AA77FF",
            "2400+": "#FF7777",
        }

        fig = go.Figure()

        for diff in labels:
            if diff in pivot.columns:
                fig.add_bar(
                    x=pivot.index,
                    y=pivot[diff],
                    name=diff,
                    marker_color=colors.get(diff, None)
                )

        fig.update_layout(
            barmode="stack",
            xaxis_title="Usuário",
            yaxis_title="Problemas resolvidos",
            height=500
        )

        st.plotly_chart(fig, use_container_width=True)

# =============================
# 👤 MODO INDIVIDUAL
# =============================

else:

    st.header("👤 Visão Individual")

    user = st.selectbox("Usuário", handles)

    u_subs = subs[subs["handle"] == user]
    u_solved = unique_solved[unique_solved["handle"] == user]
    u_rating = rating[rating["handle"] == user]

    info = users[users["handle"] == user].iloc[0]

    # =============================
    # 🔗 LINK PARA O PERFIL
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

    color = color_map.get(rank.lower(), "black")

    st.markdown(
        f'### 🔗 Perfil no Codeforces: <a href="{profile_url}" target="_blank" style="color:{color}; font-weight:700;">{user}</a> <span style="color:gray;">({rank})</span>',
        unsafe_allow_html=True
    )

    # =============================
    # 📊 KPIs
    # =============================

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("🧠 Rating atual", info["rating"])
    col2.metric("🏆 Rating máximo", info["maxRating"])
    col3.metric("🧩 Problemas resolvidos", u_solved.shape[0])
    col4.metric("🏁 Contests", u_rating.shape[0])

    # Dificuldade
    st.subheader("🧠 Distribuição por dificuldade")

    bins = [0, 800, 1200, 1600, 2000, 2400, 5000]
    labels = ["<800", "800–1200", "1200–1600",
              "1600–2000", "2000–2400", "2400+"]

    diff = u_solved.dropna(subset=["problem.rating"])

    if not diff.empty:
        diff["difficulty"] = pd.cut(
            diff["problem.rating"], bins=bins, labels=labels
        )

        pie = diff["difficulty"].value_counts()

        fig = go.Figure(
            data=[go.Pie(labels=pie.index, values=pie.values)]
        )


        st.plotly_chart(fig, use_container_width=True)