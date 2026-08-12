# CP Dashboard — GPC UFAM

Dashboard em Streamlit para acompanhar o treino de programação competitiva do Grupo de Programação Competitiva da UFAM, agregando dados do **Codeforces** e do **CSES**, com rankings, gráficos e um bot no Telegram para lembretes e estatísticas.

## Funcionalidades

- **Dashboard (`dashboard.py`)**: visão geral do grupo, ranking por rating, destaques do período (mais questões, maior frequência), distribuição de dificuldade e tags dos problemas resolvidos. Suporta visão individual, de time ou de todos, com filtro de período customizável.
- **Atualização de dados sob demanda**: botão "🔄 Atualizar dados" dispara os workflows do GitHub Actions via API, que buscam dados novos e commitam os `.parquet` de volta no repositório.
- **Bot do Telegram — Tucanito (`tucanito.py`)**: permite cadastrar handle do Codeforces, configurar lembretes de treino por dia/horário, consultar estatísticas (`/stats`) e receber notificações automáticas.
- **Ranking automático (`send_rankings.py`)**: gera e envia (via Telegram) um resumo semanal/mensal dos destaques do grupo.

## Estrutura do projeto

| Arquivo | Responsabilidade |
|---|---|
| `dashboard.py` | App Streamlit principal (UI, filtros, gráficos) |
| `codeforces.py` | Integração com a API do Codeforces, leitura/escrita dos parquets de submissões, rating e usuários |
| `cses.py` | Login e scraping autenticado do CSES, leitura/escrita do parquet de submissões |
| `rankings.py` | Cálculo dos rankings (total, Codeforces, CSES, frequência) |
| `reminders.py` | Gerenciamento de lembretes e estatísticas por usuário (usado pelo Tucanito) |
| `bot_config.py` | Configuração do bot (token, timezone, mapeamento de dias) |
| `tucanito.py` | Bot do Telegram (comandos, lembretes automáticos) |
| `send_rankings.py` | Script standalone que monta e envia o ranking periódico no Telegram |
| `scripts/run_cf_update.py` / `run_cses_update.py` | Entrypoints usados pelos workflows para atualizar os dados |
| `.github/workflows/update_cf.yml` / `update_cses.yml` | Automação diária (cron) + disparo manual (`workflow_dispatch`) da atualização de dados |

## Dados

Os dados são persistidos como arquivos `.parquet`/`.csv` no próprio repositório:

- `data/users.csv` — cadastro dos membros (handles de Codeforces e CSES)
- `data/cf_submissions.parquet`, `data/cf_rating.parquet`, `data/cf_users.parquet` — dados do Codeforces
- `data/cses_all.parquet` — submissões do CSES
- `data/telegram_users.json` — lembretes e configurações do bot

## Secrets necessários

| Secret | Onde configurar | Usado por |
|---|---|---|
| `GITHUB_TOKEN` | Secrets do Streamlit | `dashboard.py` (disparar workflows) |
| `CODEFORCES_USERS` | Secrets do GitHub Actions | `codeforces.py` (API key/secret por handle, formato JSON) |
| `CSES_ACCOUNTS` | Secrets do GitHub Actions | `cses.py` (usuário/senha por conta, formato JSON) |
| `TELEGRAM_BOT_ID` | Ambiente / `.env` / Secrets do Streamlit | `bot_config.py`, `send_rankings.py` |
| `TELEGRAM_CHAT_ID` | Ambiente | `send_rankings.py` |

## Atualização de dados

Os workflows rodam automaticamente todo dia (cron `0 6 * * *`, ~03h em Manaus) e também podem ser disparados manualmente pelo botão do dashboard ou pela aba Actions do GitHub. Os dois workflows compartilham um `concurrency group` para evitar conflito de push simultâneo no `main`.

---

## Pendências

### Prioridades

- [x] Criar bot para avisos no Telegram
- [ ] Criar bot para zerar o CSES para não precisar acessar as submissões com credenciais dos usuários
- [ ] Criar formulário de inscrição para vincular contas de email, cses e codeforces automaticamente
- [ ] Salvar em BD ao invés de .parquet e .csv

### Visual

- [x] Mostrar outros rankings (quantidade de questões, plataformas, etc)
- [ ] Mostrar alguma métrica que incentive o upsolving
- [ ] Adicionar logos da UFAM, ICOMP, Algox e CPC
- [ ] Adicionar botão de atalho para o Tucanito Bot.