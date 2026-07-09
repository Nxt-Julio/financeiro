import pandas as pd
import plotly.express as px
import streamlit as st

from database import fetch_transacoes, init_db
from utils.ui import PALETTE, _fmt_brl, kpi_row, page_header, setup_page, style_fig

setup_page("Visão Casal", "👫")
init_db()

page_header("Visão Casal", "Receita e despesa de cada responsável, lado a lado.", "👫")

transacoes = fetch_transacoes()

if not transacoes:
    st.info("Nenhuma transação cadastrada ainda. Registre um lançamento para começar.")
else:
    df = pd.DataFrame(transacoes)

    resumo = df.groupby(["responsavel", "tipo"])["valor"].sum().reset_index()

    pivot = resumo.pivot_table(
        index="responsavel", columns="tipo", values="valor", aggfunc="sum", fill_value=0
    )
    for coluna in ("receita", "despesa"):
        if coluna not in pivot.columns:
            pivot[coluna] = 0.0
    pivot["saldo"] = pivot["receita"] - pivot["despesa"]

    # KPIs: saldo por responsável
    cards = []
    for responsavel, linha in pivot.iterrows():
        cards.append({
            "label": responsavel,
            "value": _fmt_brl(linha["saldo"]),
            "color": PALETTE["receita"] if linha["saldo"] >= 0 else PALETTE["despesa"],
            "sub": f"Receita {_fmt_brl(linha['receita'])} · Despesa {_fmt_brl(linha['despesa'])}",
        })
    kpi_row(cards)

    st.subheader("Receita vs. Despesa por responsável")
    fig = px.bar(
        resumo, x="responsavel", y="valor", color="tipo", barmode="group",
        color_discrete_map={"receita": PALETTE["receita"], "despesa": PALETTE["despesa"]},
        labels={"responsavel": "Responsável", "valor": "Valor (R$)", "tipo": "Tipo"},
    )
    st.plotly_chart(style_fig(fig), use_container_width=True)

    st.subheader("Resumo por responsável")
    tabela = pivot.reset_index().rename(
        columns={
            "responsavel": "Responsável",
            "receita": "Total Receita",
            "despesa": "Total Despesa",
            "saldo": "Saldo",
        }
    )
    st.dataframe(
        tabela[["Responsável", "Total Receita", "Total Despesa", "Saldo"]],
        use_container_width=True,
    )
