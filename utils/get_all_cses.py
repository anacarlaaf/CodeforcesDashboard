import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

BASE_URL = "https://cses.fi"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


def get_all_cses_problems():
    """
    Faz scraping de TODOS os problemas do CSES.

    Retorna lista:
    [
        {
            "task_id": 1068,
            "name": "Weird Algorithm",
            "category": "Introductory Problems",
            "url": "https://cses.fi/problemset/task/1068/"
        },
        ...
    ]
    """

    url = f"{BASE_URL}/problemset/"

    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    problems = []

    current_category = None

    # Navega pelos elementos principais
    content = soup.find("div", class_="content")

    for elem in content.find_all(["h2", "a"]):

        # Categoria
        if elem.name == "h2":
            current_category = elem.get_text(strip=True)

        # Problema
        elif elem.name == "a":

            href = elem.get("href", "")

            if "/problemset/task/" not in href:
                continue

            try:
                task_id = int(href.strip("/").split("/")[-1])
            except:
                continue

            name = elem.get_text(strip=True)

            problems.append({
                "task_id": task_id,
                "name": name,
                "category": current_category,
                "url": BASE_URL + href,
            })

    # remover duplicados
    unique = {}

    for p in problems:
        unique[p["task_id"]] = p

    problems = list(unique.values())

    # ordenar
    problems.sort(key=lambda x: x["task_id"])

    return problems


if __name__ == "__main__":

    problems = get_all_cses_problems()

    print(f"Total de problemas encontrados: {len(problems)}")

    df = pd.DataFrame(problems)

    print(df.head())

    # salvar
    df.to_csv("cses_problems.csv", index=False)

    print("Arquivo salvo: cses_problems.csv")