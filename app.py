import datetime

import pandas as pd

from database import fetch_parcelamentos, fetch_transacoes, init_db
from utils.ui import PALETTE, _fmt_brl, kpi_row, page_header, setup_page

setup_page("Gestão Financeira Pessoal", "💰")
init_db()

page_header(
    "Gestão Financeira Pessoal",
    "Seu painel de controle de receitas, despesas, parcelamentos e holerites — tudo local.",
    "💰",
)

transacoes = fetch_transacoes()
parcelamentos = fetch_parcelamentos()

# ---------- KPIs de visão geral ----------
if transacoes:
    df = pd.DataFrame(transacoes)
    total_receita = df.loc[df["tipo"] == "receita", "valor"].sum()
    total_despesa = df.loc[df["tipo"] == "despesa", "valor"].sum()
    saldo = total_receita - total_despesa
else:
    total_receita = total_despesa = saldo = 0.0

hoje = datetime.date.today()
comprometido_futuro = 0.0
if parcelamentos:
    dfp = pd.DataFrame(parcelamentos)
    dfp["venc"] = pd.to_datetime(dfp["data_vencimento"])
    comprometido_futuro = dfp.loc[dfp["venc"] >= pd.Timestamp(hoje), "valor_parcela"].sum()

kpi_row([
    {"label": "Receitas", "value": _fmt_brl(total_receita), "color": PALETTE["receita"],
     "sub": "Total lançado"},
    {"label": "Despesas", "value": _fmt_brl(total_despesa), "color": PALETTE["despesa"],
     "sub": "Total lançado"},
    {"label": "Saldo", "value": _fmt_brl(saldo),
     "color": PALETTE["receita"] if saldo >= 0 else PALETTE["despesa"],
     "sub": "Receitas − Despesas"},
    {"label": "Parcelas futuras", "value": _fmt_brl(comprometido_futuro),
     "color": PALETTE["accent"], "sub": "Comprometido a partir de hoje"},
])

# ---------- Cards de navegação ----------
import streamlit as st

st.subheader("Módulos")

# (emoji, título, descrição, slug da página — a rota é o nome do arquivo em
# pages/ sem o prefixo numérico, ex: 1_Parcelamentos.py -> /Parcelamentos)
SECOES = [
    ("🧾", "Parcelamentos", "Registre compras parceladas e gere as parcelas futuras automaticamente.", "Parcelamentos"),
    ("📊", "Visão Geral", "Distribuição de despesas por categoria e lista de transações.", "Visao_Geral"),
    ("🗂️", "Gerenciar Lançamentos", "Edite categorias e campos, ou exclua lançamentos.", "Gerenciar_Lancamentos"),
    ("✍️", "Lançamento Manual", "Registre receitas e despesas avulsas em dinheiro.", "Lancamento_Manual"),
    ("📄", "Leitura de Holerite", "Importe o holerite em PDF e lance o salário líquido.", "Leitura_Holerite"),
    ("📑", "Leitura de Extrato", "Importe a fatura/extrato em PDF com categorização automática.", "Leitura_Extrato"),
    ("👫", "Visão Casal", "Compare receita e despesa de cada responsável.", "Visao_Casal"),
    ("📈", "Projeção Futura", "Veja os gastos já comprometidos nos próximos meses.", "Projecao_Futura"),
    ("⚙️", "Configurações", "Personalize os nomes dos responsáveis.", "Configuracoes"),
]

cols = st.columns(4)
for i, (emoji, titulo, desc, slug) in enumerate(SECOES):
    with cols[i % 4]:
        st.markdown(
            f'<a class="nav-card" href="/{slug}" target="_self">'
            f'<span class="nav-emoji">{emoji}</span>'
            f'<span class="nav-title">{titulo}</span>'
            f'<span class="nav-desc">{desc}</span></a>',
            unsafe_allow_html=True,
        )

st.caption("Use o menu à esquerda para navegar entre os módulos.")
