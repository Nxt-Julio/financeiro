import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from database import fetch_parcelamentos, init_db
from utils.ui import PALETTE, _fmt_brl, kpi_row, page_header, setup_page, style_fig
from utils.auth import require_login

setup_page("Projeção Futura", "📈")
require_login()
init_db()

page_header(
    "Projeção Futura",
    "Quanto dos próximos meses já está comprometido com compras parceladas.",
    "📈",
)

parcelamentos = fetch_parcelamentos()

if not parcelamentos:
    st.info("Nenhum parcelamento cadastrado ainda. Registre um parcelamento para começar.")
else:
    df = pd.DataFrame(parcelamentos)
    df["data_vencimento"] = pd.to_datetime(df["data_vencimento"])
    df["mes"] = df["data_vencimento"].dt.to_period("M").astype(str)
    df["pago"] = df["pago"].fillna(False).astype(bool)

    # Esta página é sobre o que AINDA falta pagar — parcelas já marcadas como
    # pagas (ex: quitadas via Gerenciar Lançamentos ou vinculadas a um holerite)
    # saem do gráfico e das tabelas, mesmo que a data de vencimento já tenha
    # passado (evita contar de novo algo já quitado).
    pendentes = df[~df["pago"]].copy()

    hoje = pd.Timestamp(datetime.date.today())
    futuras = pendentes[pendentes["data_vencimento"] >= hoje].sort_values("data_vencimento").copy()
    atrasadas = pendentes[pendentes["data_vencimento"] < hoje]

    total_futuro = futuras["valor_parcela"].sum()
    meses_futuros = futuras["mes"].nunique()
    proximo_mes = futuras["mes"].min() if not futuras.empty else "—"

    kpi_row([
        {"label": "Comprometido (futuro)", "value": _fmt_brl(total_futuro), "color": PALETTE["despesa"],
         "sub": "Ainda não pago"},
        {"label": "Meses com parcelas", "value": str(meses_futuros), "color": PALETTE["accent"]},
        {"label": "Próximo mês", "value": str(proximo_mes), "color": PALETTE["primary"]},
        {"label": "Atrasadas", "value": _fmt_brl(atrasadas["valor_parcela"].sum()),
         "color": PALETTE["despesa"], "sub": f"{len(atrasadas)} parcela(s) vencida(s) e não paga(s)"},
    ])

    resumo_mensal = (
        pendentes.groupby("mes", as_index=False)["valor_parcela"].sum().sort_values("mes")
    )

    st.subheader("Total comprometido por mês")
    if resumo_mensal.empty:
        st.info("Todas as parcelas já estão marcadas como pagas. 🎉")
    else:
        fig = px.line(
            resumo_mensal, x="mes", y="valor_parcela", markers=True,
            labels={"mes": "Mês", "valor_parcela": "Valor comprometido (R$)"},
        )
        fig.update_traces(line_color=PALETTE["primary"], line_width=3,
                          marker=dict(size=9, color=PALETTE["accent"]))
        fig.update_xaxes(type="category")
        fig.update_traces(fill="tozeroy", fillcolor="rgba(99,102,241,0.12)")
        st.plotly_chart(style_fig(fig), use_container_width=True)

    st.subheader("Parcelas futuras")
    if futuras.empty:
        st.info("Nenhuma parcela futura pendente a partir de hoje.")
    else:
        futuras["Parcela"] = (
            futuras["parcela_atual"].astype(str) + "/" + futuras["total_parcelas"].astype(str)
        )
        tabela = futuras.rename(
            columns={
                "descricao": "Descrição",
                "data_vencimento": "Vencimento",
                "valor_parcela": "Valor",
            }
        )[["Descrição", "Parcela", "Vencimento", "Valor"]]
        tabela["Vencimento"] = tabela["Vencimento"].dt.strftime("%d/%m/%Y")
        st.dataframe(tabela, use_container_width=True)
