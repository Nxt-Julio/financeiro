import pandas as pd
import plotly.express as px
import streamlit as st

from database import fetch_transacoes, init_db
from utils.finance import filtrar_realizadas
from utils.ui import PALETTE, _fmt_brl, kpi_row, page_header, setup_page, style_fig
from utils.auth import require_login

setup_page("Visão Geral", "📊")
require_login()
init_db()

page_header("Visão Geral", "Para onde vai o seu dinheiro — por categoria e ao longo do tempo.", "📊")

transacoes = fetch_transacoes()

if not transacoes:
    st.info("Nenhuma transação cadastrada ainda. Registre um lançamento ou parcelamento para começar.")
else:
    df = pd.DataFrame(transacoes)
    # KPIs e gráficos consideram só o que já foi realizado (data <= hoje ou já
    # pago) — parcelas futuras ainda não pagas são compromisso, não gasto (ver
    # Projeção Futura). A tabela completa mais abaixo continua mostrando tudo.
    df_realizado = filtrar_realizadas(df)
    receita = df_realizado.loc[df_realizado["tipo"] == "receita", "valor"].sum()
    despesa = df_realizado.loc[df_realizado["tipo"] == "despesa", "valor"].sum()

    kpi_row([
        {"label": "Receitas", "value": _fmt_brl(receita), "color": PALETTE["receita"], "sub": "Já recebidas"},
        {"label": "Despesas", "value": _fmt_brl(despesa), "color": PALETTE["despesa"], "sub": "Já incorridas ou pagas"},
        {"label": "Saldo", "value": _fmt_brl(receita - despesa),
         "color": PALETTE["receita"] if receita - despesa >= 0 else PALETTE["despesa"]},
        {"label": "Transações", "value": str(len(df)), "color": PALETTE["accent"], "sub": "Total lançado (todas)"},
    ])

    despesas = df_realizado[df_realizado["tipo"] == "despesa"]

    col_esq, col_dir = st.columns([3, 2])

    with col_esq:
        st.subheader("Despesas por categoria")
        if despesas.empty:
            st.info("Nenhuma despesa registrada ainda.")
        else:
            por_categoria = despesas.groupby("categoria", as_index=False)["valor"].sum()
            fig = px.pie(por_categoria, names="categoria", values="valor", hole=0.55)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(style_fig(fig), use_container_width=True)

    with col_dir:
        st.subheader("Maiores categorias")
        if not despesas.empty:
            ranking = (
                despesas.groupby("categoria", as_index=False)["valor"].sum()
                .sort_values("valor", ascending=False).head(8)
            )
            fig_bar = px.bar(ranking, x="valor", y="categoria", orientation="h")
            fig_bar.update_layout(yaxis=dict(autorange="reversed"), showlegend=False)
            fig_bar.update_traces(marker_color=PALETTE["primary"])
            st.plotly_chart(style_fig(fig_bar), use_container_width=True)

    st.subheader("Todas as transações")
    df_view = df.copy()
    df_view["data"] = pd.to_datetime(df_view["data"]).dt.strftime("%d/%m/%Y")
    st.dataframe(
        df_view,
        use_container_width=True,
        hide_index=True,
        column_order=["data", "descricao_original", "estabelecimento", "categoria", "valor", "tipo", "responsavel", "origem", "pago"],
        column_config={
            "id": None,
            "id_parcelamento": None,
            "data": st.column_config.TextColumn("Data"),
            "descricao_original": st.column_config.TextColumn("Descrição"),
            "estabelecimento": st.column_config.TextColumn("Estabelecimento"),
            "categoria": st.column_config.TextColumn("Categoria"),
            "valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
            "tipo": st.column_config.TextColumn("Tipo"),
            "responsavel": st.column_config.TextColumn("Responsável"),
            "origem": st.column_config.TextColumn("Origem"),
            "pago": st.column_config.CheckboxColumn("Pago", disabled=True),
        },
    )
