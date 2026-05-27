import streamlit as st
import pandas as pd
import requests
import time
import hashlib

api_key = st.secrets["CODEFORCES_API_KEY"]
api_secret = st.secrets["CODEFORCES_API_SECRET"]

BASE = "https://codeforces.com/api/"

@st.cache_data(ttl=3600)
def get_contest_size(contest_id):
    url = "https://codeforces.com/api/contest.standings"
    
    params = {
        "contestId": contest_id,
        "from": 1,
        "count": 1
    }

    r = requests.get(url, params=params).json()
    print(r)
    print(r)
    
    problems = r["result"]["problems"]
    return len(problems)

@st.cache_data(ttl=3600)
def cf_request(method, params=None):
    if params is None:
        params = {}

    rand = "123456"
    now = int(time.time())

    # adicionar autenticação
    params["apiKey"] = api_key
    params["time"] = now

    # ordenar parâmetros alfabeticamente
    sorted_params = "&".join(
        f"{k}={params[k]}" for k in sorted(params)
    )

    # string para hash
    to_hash = f"{rand}/{method}?{sorted_params}#{api_secret}"

    sha = hashlib.sha512(to_hash.encode()).hexdigest()

    params["apiSig"] = rand + sha

    r = requests.get(BASE + method, params=params)
    data = r.json()

    if data["status"] != "OK":
        st.error(data["comment"])
        return []

    return data["result"]

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


def progress_bar_scaled(done, total, size=7):
    if total == 0:
        return ""
    ratio = min(done / total, 1)
    filled = int(ratio * size)
    return "🟩" * filled + "🟥" * (size - filled)

def progress_bar(done, total):
    done = min(done, total)
    return "🟩" * done + "🟥" * (total - done)
