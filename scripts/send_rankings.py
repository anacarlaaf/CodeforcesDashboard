import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

import argparse
import datetime
import os
import subprocess

import pandas as pd
import requests

import codeforces
import cses
import rankings


def sync_data_local():
    """
    Executa a atualização do CSES localmente, faz commit e push.
    """
    
    print("[Sync] Executando atualização local do CSES...")
    
    # 1. Executa o script de atualização do CSES
    script_path = project_root / "scripts" / "run_cses_update.py"
    
    if not script_path.exists():
        print(f"[Sync] ⚠️ Script não encontrado: {script_path}")
        print("[Sync] Continuando com dados existentes...")
        return
    
    try:
        # Executa o script com as variáveis de ambiente
        env = os.environ.copy()
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=project_root,
            capture_output=True,
            text=True,
            env=env
        )
        
        print(f"[Sync] Script executado com sucesso!")
        if result.stdout:
            print(f"[Sync] Output: {result.stdout}")
        if result.stderr:
            print(f"[Sync] Stderr: {result.stderr}")
            
    except subprocess.CalledProcessError as e:
        print(f"[Sync] ❌ Erro ao executar script: {e}")
        print(f"[Sync] Output: {e.stdout}")
        print(f"[Sync] Stderr: {e.stderr}")
        print("[Sync] Continuando com dados existentes...")
        return
    
    # 2. Verifica se o parquet foi modificado
    parquet_path = project_root / "data" / "cses_all.parquet"
    
    if not parquet_path.exists():
        print("[Sync] ⚠️ Parquet não encontrado após atualização.")
        return
    
    # 3. Verifica se há mudanças no git
    print("[Sync] Verificando mudanças no git...")
    result = subprocess.run(
        ["git", "status", "--porcelain", "data/cses_all.parquet"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    
    if not result.stdout.strip():
        print("[Sync] Nenhuma mudança no parquet. Nada para commitar.")
        return
    
    # 4. Faz git pull antes de commitar
    print("[Sync] Fazendo git pull para pegar mudanças remotas...")
    result = subprocess.run(
        ["git", "pull", "--rebase", "origin", "main"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        print(f"[Sync] ⚠️ git pull falhou: {result.stderr.strip()}")
        print("[Sync] Tentando reset para o estado remoto...")
        
        # Se falhar, tenta fazer reset --hard
        result = subprocess.run(
            ["git", "reset", "--hard", "origin/main"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            print("[Sync] ⚠️ Não foi possível sincronizar com o remoto.")
            print("[Sync] Continuando com commit local...")
        else:
            print("[Sync] Reset para o remoto realizado com sucesso.")
    else:
        print(f"[Sync] ✅ {result.stdout.strip()}")
    
    # 5. Adiciona o arquivo modificado
    print("[Sync] Adicionando arquivo ao git...")
    subprocess.run(
        ["git", "add", "data/cses_all.parquet"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
    
    # 6. Faz commit
    print("[Sync] Fazendo commit...")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_msg = f"chore: update cses_all.parquet ({timestamp})"
    
    result = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        print(f"[Sync] ⚠️ Commit falhou: {result.stderr.strip()}")
        return
    
    print(f"[Sync] ✅ Commit realizado: {commit_msg}")
    
    # 7. Faz push
    print("[Sync] Fazendo push para o repositório remoto...")
    result = subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        print(f"[Sync] ❌ Push falhou: {result.stderr.strip()}")
        print("[Sync] ⚠️ O commit foi feito localmente, mas não foi enviado.")
        return
    
    print(f"[Sync] ✅ Push realizado com sucesso!")


def sync_data_simple():
    """
    Versão simples: apenas faz git pull para pegar mudanças remotas.
    Mantido para compatibilidade.
    """
    print("[Sync] Atualizando dados (git pull)...")
    
    result = subprocess.run(
        ["git", "pull", "origin", "main"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        print(f"[Sync] git pull falhou (seguindo com dados locais atuais): {result.stderr.strip()}")
    else:
        print(f"[Sync] {result.stdout.strip()}")


def build_dataset(start: datetime.datetime, end: datetime.datetime):
    """
    Reproduz a mesma lógica de carregamento/filtro do dashboard.py,
    mas lendo direto dos parquets (sem Streamlit/UI).
    """

    users = pd.read_csv("data/users.csv")

    handles = (
        users["codeforces"]
        .dropna()
        .astype(str)
        .str.strip()
    )
    handles = handles[handles != ""].tolist()

    subs, rating, cf_users = codeforces.load_data(handles=handles)

    subs["date"] = pd.to_datetime(
        subs["creationTimeSeconds"],
        unit="s",
        utc=True,
    )

    cses_subs = cses.load_submissions()
    cses_subs = cses_subs[cses_subs["handle"].isin(handles)]
    cses_subs["problem.rating"] = -1

    subs = pd.concat(
        [subs, cses_subs],
        ignore_index=True,
        sort=False,
    )

    subs = subs[
        (subs["date"] >= start)
        & (subs["date"] <= end)
    ]

    solved = subs[subs["verdict"] == "OK"]

    unique_solved = solved.drop_duplicates(
        ["handle", "problem.contestId", "problem.index"]
    ).copy()

    return subs, unique_solved


def format_top(title: str, df: pd.DataFrame, value_col: str, n: int = 5) -> str:
    lines = [f"*{title}*"]

    if df.empty:
        lines.append("_sem dados no período_")
        return "\n".join(lines)

    top = df.reset_index(drop=True).head(n)
    
    # Encontra o maior handle para definir a largura
    max_handle_len = max(len(str(row["handle"])) for _, row in top.iterrows())
    # Define largura mínima e adiciona padding
    handle_width = max(max_handle_len + 2, 10)  # +2 para espaçamento
    
    # Encontra o maior valor para alinhar à direita
    max_value_len = max(len(str(row[value_col])) for _, row in top.iterrows())
    
    code_lines = []
    
    for i, row in top.iterrows():
        pos = f"{i+1}."
        handle = str(row["handle"])
        value = str(row[value_col])
        
        # Alinhamento: posição à esquerda, handle à esquerda, valor à direita
        line = f"{pos:<3}{handle:<{handle_width}}{value:>{max_value_len}}"
        code_lines.append(line)
    
    lines.append("```text")
    lines.extend(code_lines)
    lines.append("```")

    return "\n".join(lines)

def build_message(period_label: str, start: datetime.datetime, end: datetime.datetime) -> str:

    subs, unique_solved = build_dataset(start, end)

    blocks = [
        "🎈Olá, GPC! Vamos ver como vão os treinos? 🦾🧠",
        "",
        f"🏆 *RANKING {period_label.upper()}* 🏆\n",
        format_top(
            "Mais questões no total",
            rankings.top_total_solved(unique_solved, n=5),
            "questões",
        ),
        "",
        format_top(
            "Mais questões no Codeforces",
            rankings.top_codeforces_solved(unique_solved, n=5),
            "questões",
        ),
        "",
        format_top(
            "Mais questões no CSES",
            rankings.top_cses_solved(unique_solved, n=5),
            "questões",
        ),
        "",
        format_top(
            "Dias de estudo",
            rankings.top_frequency(subs, unique_solved, n=5),
            "dias",
        ),
    ]

    return "\n".join(blocks)


def send_telegram_message(text: str):

    token = os.environ.get("TELEGRAM_BOT_ID")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN e/ou TELEGRAM_CHAT_ID não encontrados no ambiente."
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    r = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",  # Mantém Markdown para negrito/itálico
        },
        timeout=20,
    )

    if r.status_code != 200:
        raise RuntimeError(
            f"Erro ao enviar mensagem no Telegram: {r.status_code} {r.text}"
        )

    print("[Telegram] Mensagem enviada com sucesso.")


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--period",
        choices=["semanal", "mensal"],
        required=True,
    )
    parser.add_argument(
        "--skip-update",
        action="store_true",
        help="Pula a atualização do CSES (usa dados locais)"
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Faz a atualização mas não faz push (apenas commit local)"
    )
    args = parser.parse_args()

    # Se não for para pular, executa a atualização local
    if not args.skip_update:
        sync_data_local()
    else:
        print("[Sync] Pulando atualização do CSES, usando dados locais...")
        # Ainda faz git pull para pegar mudanças remotas
        sync_data_simple()

    today = datetime.datetime.now(datetime.timezone.utc)
    end = today.replace(hour=23, minute=59, second=59, microsecond=999999)

    if args.period == "semanal":
        start = (today - datetime.timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "Semanal"
    else:
        start = (today - datetime.timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "Mensal"

    message = build_message(period_label, start, end)

    print(message)

    send_telegram_message(message)


if __name__ == "__main__":
    main()