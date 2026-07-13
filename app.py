import datetime

import pandas as pd

from database import fetch_parcelamentos, fetch_transacoes, init_db
from utils.finance import filtrar_realizadas
from utils.ui import PALETTE, _fmt_brl, kpi_row, page_header, setup_page
from utils.auth import require_login

setup_page("Gestão Financeira Pessoal", "💰")
require_login()
init_db()

page_header(
    "Gestão Financeira Pessoal",
    "Seu painel de controle de receitas, despesas, parcelamentos e holerites — tudo local.",
    "💰",
)

transacoes = fetch_transacoes()
parcelamentos = fetch_parcelamentos()

# ---------- KPIs de visão geral ----------
# "Despesas"/"Saldo" contam só o que já foi REALIZADO (data <= hoje ou já pago) —
# parcelas futuras ainda não pagas são compromisso, não gasto, e ficam de fora
# daqui (aparecem em "Parcelas futuras" e na Projeção Futura).
hoje = datetime.date.today()

if transacoes:
    df = pd.DataFrame(transacoes)
    df_realizado = filtrar_realizadas(df, hoje)
    total_receita = df_realizado.loc[df_realizado["tipo"] == "receita", "valor"].sum()
    total_despesa = df_realizado.loc[df_realizado["tipo"] == "despesa", "valor"].sum()
    saldo = total_receita - total_despesa
else:
    total_receita = total_despesa = saldo = 0.0

comprometido_futuro = 0.0
if parcelamentos:
    dfp = pd.DataFrame(parcelamentos)
    dfp["venc"] = pd.to_datetime(dfp["data_vencimento"])
    dfp["pago"] = dfp["pago"].fillna(False).astype(bool)
    pendente = dfp[(dfp["venc"] >= pd.Timestamp(hoje)) & (~dfp["pago"])]
    comprometido_futuro = pendente["valor_parcela"].sum()

kpi_row([
    {"label": "Receitas", "value": _fmt_brl(total_receita), "color": PALETTE["receita"],
     "sub": "Já recebidas"},
    {"label": "Despesas", "value": _fmt_brl(total_despesa), "color": PALETTE["despesa"],
     "sub": "Já incorridas ou pagas"},
    {"label": "Saldo", "value": _fmt_brl(saldo),
     "color": PALETTE["receita"] if saldo >= 0 else PALETTE["despesa"],
     "sub": "Receitas − Despesas (já realizadas)"},
    {"label": "Parcelas futuras", "value": _fmt_brl(comprometido_futuro),
     "color": PALETTE["accent"], "sub": "Ainda não pagas, a partir de hoje"},
])

# ---------- Cards de navegação ----------
import streamlit as st

st.subheader("Módulos")

# (emoji, título, descrição, caminho do arquivo da página). Usamos st.page_link
# (navegação nativa) para preservar a sessão de login ao clicar — links comuns
# recarregam a página inteira e derrubariam o login.
SECOES = [
    ("🧾", "Parcelamentos", "Registre compras parceladas e gere as parcelas futuras automaticamente.", "pages/1_Parcelamentos.py"),
    ("📊", "Visão Geral", "Distribuição de despesas por categoria e lista de transações.", "pages/2_Visao_Geral.py"),
    ("🗂️", "Gerenciar Lançamentos", "Edite categorias e campos, ou exclua lançamentos.", "pages/8_Gerenciar_Lancamentos.py"),
    ("✍️", "Lançamento Manual", "Registre receitas e despesas avulsas em dinheiro.", "pages/3_Lancamento_Manual.py"),
    ("📄", "Leitura de Holerite", "Importe o holerite em PDF e lance o salário líquido.", "pages/4_Leitura_Holerite.py"),
    ("📑", "Leitura de Extrato", "Importe a fatura/extrato em PDF com categorização automática.", "pages/5_Leitura_Extrato.py"),
    ("👫", "Visão Casal", "Compare receita e despesa de cada responsável.", "pages/6_Visao_Casal.py"),
    ("📈", "Projeção Futura", "Veja os gastos já comprometidos nos próximos meses.", "pages/7_Projecao_Futura.py"),
    ("⚙️", "Configurações", "Personalize os nomes dos responsáveis.", "pages/0_Configuracoes.py"),
]

cols = st.columns(4)
for i, (emoji, titulo, desc, page_path) in enumerate(SECOES):
    with cols[i % 4]:
        with st.container(border=True):
            st.page_link(page_path, label=f"**{emoji} {titulo}**")
            st.caption(desc)

st.caption("Ou use o menu à esquerda para navegar entre os módulos.")
