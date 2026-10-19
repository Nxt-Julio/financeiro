"""Relatórios: análises em abas — categorias do período, comparativo mensal,
visão do casal e projeção das parcelas futuras. Substitui as antigas telas
"Visão Geral", "Visão Casal" e "Projeção Futura".

Totais consideram só o que já foi realizado (data <= hoje ou já pago) —
parcelas futuras ainda não pagas são compromisso, não gasto (aba Futuro)."""
import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from database import fetch_parcelamentos, fetch_transacoes
from utils import periodo
from utils.finance import filtrar_realizadas
from utils.ui import PALETTE, PLOTLY_CONFIG, _fmt_brl, chip, kpi_row, lista, page_header, row_card, style_fig

page_header("Relatórios", "Gráficos e comparativos para entender para onde vai o dinheiro.", "📊")

transacoes = fetch_transacoes()
if not transacoes:
    st.info("Nenhuma transação cadastrada ainda. Registre um lançamento para começar.")
    st.stop()

hoje = datetime.date.today()
df = pd.DataFrame(transacoes)
df["categoria"] = df["categoria"].fillna("Sem categoria")
df_real = filtrar_realizadas(df)
df_real_p = periodo.filtrar_df(df_real)

aba_cat, aba_mes, aba_casal, aba_fut, aba_tab = st.tabs(["Categorias", "Mensal", "Casal", "Futuro", "Tabela"])

# ---------- Categorias (período) ----------
with aba_cat:
    chip(f"📅 {periodo.rotulo(longo=True)}")
    despesas = df_real_p[df_real_p["tipo"] == "despesa"]
    if despesas.empty:
        st.info("Nenhuma despesa realizada no período.")
    else:
        cat = despesas.groupby("categoria", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
        total = cat["valor"].sum()
        col1, col2 = st.columns([2, 3])
        with col1:
            top = cat.head(6)
            if len(cat) > 6:
                top = pd.concat([top, pd.DataFrame([{"categoria": "Outros", "valor": cat["valor"].iloc[6:].sum()}])])
            fig = go.Figure(go.Pie(labels=top["categoria"], values=top["valor"], hole=.6, sort=False,
                                   textinfo="percent", textposition="inside",
                                   hovertemplate="%{label}<br>R$ %{value:,.2f}<extra></extra>"))
            fig.add_annotation(text=f"<b>{_fmt_brl(total)}</b>", showarrow=False, font=dict(size=14))
            st.plotly_chart(style_fig(fig, altura=260, legenda=False), use_container_width=True, config=PLOTLY_CONFIG)
        with col2:
            lista([
                row_card(r["categoria"], f"{r['valor'] / total:.0%} das despesas", _fmt_brl(r["valor"]))
                for _, r in cat.head(10).iterrows()
            ])

# ---------- Comparativo mensal (últimos 12 meses) ----------
with aba_mes:
    df_real = df_real.assign(mes=df_real["data"].astype(str).str[:7])
    meses = sorted(df_real["mes"].unique())[-12:]
    mensal = (
        df_real[df_real["mes"].isin(meses)]
        .pivot_table(index="mes", columns="tipo", values="valor", aggfunc="sum", fill_value=0)
        .reindex(columns=["receita", "despesa"], fill_value=0)
        .reset_index()
    )
    mensal["saldo"] = mensal["receita"] - mensal["despesa"]
    mensal["rotulo"] = mensal["mes"].apply(periodo.rotulo)

    medias = mensal[["receita", "despesa"]].mean() if not mensal.empty else pd.Series({"receita": 0, "despesa": 0})
    kpi_row([
        {"label": "Receita média", "value": _fmt_brl(medias["receita"]), "color": PALETTE["receita"], "sub": "Por mês"},
        {"label": "Despesa média", "value": _fmt_brl(medias["despesa"]), "color": PALETTE["despesa"], "sub": "Por mês"},
    ])
    fig = go.Figure()
    fig.add_bar(x=mensal["rotulo"], y=mensal["receita"], name="Receita", marker_color=PALETTE["receita"])
    fig.add_bar(x=mensal["rotulo"], y=mensal["despesa"], name="Despesa", marker_color=PALETTE["despesa"])
    fig.add_scatter(x=mensal["rotulo"], y=mensal["saldo"], name="Saldo", mode="lines+markers",
                    line=dict(color=PALETTE["accent"], width=2))
    fig.update_layout(barmode="group")
    fig.update_traces(hovertemplate="R$ %{y:,.2f}<extra></extra>")
    st.plotly_chart(style_fig(fig, altura=300), use_container_width=True, config=PLOTLY_CONFIG)
    lista([
        row_card(periodo.rotulo(r["mes"], longo=True),
                 f"Receita {_fmt_brl(r['receita'])} · Despesa {_fmt_brl(r['despesa'])}",
                 _fmt_brl(r["saldo"]), cor_valor=PALETTE["receita"] if r["saldo"] >= 0 else PALETTE["despesa"])
        for _, r in mensal.iloc[::-1].iterrows()
    ])

# ---------- Casal (período) ----------
with aba_casal:
    chip(f"📅 {periodo.rotulo(longo=True)}")
    if df_real_p.empty:
        st.info("Nada realizado no período.")
    else:
        resumo = df_real_p.groupby(["responsavel", "tipo"])["valor"].sum().reset_index()
        pivot = (resumo.pivot_table(index="responsavel", columns="tipo", values="valor", aggfunc="sum", fill_value=0)
                 .reindex(columns=["receita", "despesa"], fill_value=0))
        pivot["saldo"] = pivot["receita"] - pivot["despesa"]
        kpi_row([
            {"label": resp, "value": _fmt_brl(linha["saldo"]),
             "color": PALETTE["receita"] if linha["saldo"] >= 0 else PALETTE["despesa"],
             "sub": f"Receita {_fmt_brl(linha['receita'])} · Despesa {_fmt_brl(linha['despesa'])}"}
            for resp, linha in pivot.iterrows()
        ])
        fig = px.bar(
            resumo, x="responsavel", y="valor", color="tipo", barmode="group",
            color_discrete_map={"receita": PALETTE["receita"], "despesa": PALETTE["despesa"]},
        )
        fig.update_traces(hovertemplate="R$ %{y:,.2f}<extra></extra>")
        st.plotly_chart(style_fig(fig, altura=280), use_container_width=True, config=PLOTLY_CONFIG)

# ---------- Futuro (parcelas a pagar) ----------
with aba_fut:
    parcelamentos = fetch_parcelamentos()
    if not parcelamentos:
        st.info("Nenhum parcelamento cadastrado ainda.")
    else:
        dfp = pd.DataFrame(parcelamentos)
        dfp["data_vencimento"] = pd.to_datetime(dfp["data_vencimento"])
        dfp["mes"] = dfp["data_vencimento"].dt.to_period("M").astype(str)
        dfp["pago"] = dfp["pago"].fillna(False).astype(bool)
        # Só o que AINDA falta pagar: parcelas marcadas como pagas saem, mesmo que
        # o vencimento já tenha passado (evita contar de novo algo já quitado).
        pendentes = dfp[~dfp["pago"]].copy()
        ts_hoje = pd.Timestamp(hoje)
        futuras = pendentes[pendentes["data_vencimento"] >= ts_hoje].sort_values("data_vencimento")
        atrasadas = pendentes[pendentes["data_vencimento"] < ts_hoje]

        kpi_row([
            {"label": "Comprometido", "value": _fmt_brl(futuras["valor_parcela"].sum()),
             "color": PALETTE["despesa"], "sub": "Parcelas futuras"},
            {"label": "Atrasadas", "value": _fmt_brl(atrasadas["valor_parcela"].sum()),
             "color": PALETTE["alerta"], "sub": f"{len(atrasadas)} vencida(s) não paga(s)"},
        ])
        resumo_mensal = pendentes.groupby("mes", as_index=False)["valor_parcela"].sum().sort_values("mes")
        if resumo_mensal.empty:
            st.info("Todas as parcelas já estão marcadas como pagas. 🎉")
        else:
            resumo_mensal["rotulo"] = resumo_mensal["mes"].apply(periodo.rotulo)
            fig = px.bar(resumo_mensal, x="rotulo", y="valor_parcela")
            fig.update_traces(marker_color=PALETTE["primary"], hovertemplate="R$ %{y:,.2f}<extra></extra>")
            st.plotly_chart(style_fig(fig, altura=240, legenda=False), use_container_width=True, config=PLOTLY_CONFIG)
        if not futuras.empty:
            st.markdown("**Próximas parcelas**")
            lista([
                row_card(r["descricao"], f"Parcela {r['parcela_atual']}/{r['total_parcelas']}",
                         _fmt_brl(r["valor_parcela"]), data=r["data_vencimento"].date())
                for _, r in futuras.head(15).iterrows()
            ])

# ---------- Tabela completa ----------
with aba_tab:
    df_view = periodo.filtrar_df(df).copy()
    df_view["data"] = pd.to_datetime(df_view["data"]).dt.strftime("%d/%m/%Y")
    st.dataframe(
        df_view,
        use_container_width=True,
        hide_index=True,
        column_order=["data", "descricao_original", "categoria", "valor", "tipo", "responsavel", "origem", "pago"],
        column_config={
            "data": st.column_config.TextColumn("Data"),
            "descricao_original": st.column_config.TextColumn("Descrição"),
            "categoria": st.column_config.TextColumn("Categoria"),
            "valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
            "tipo": st.column_config.TextColumn("Tipo"),
            "responsavel": st.column_config.TextColumn("Responsável"),
            "origem": st.column_config.TextColumn("Origem"),
            "pago": st.column_config.CheckboxColumn("Pago", disabled=True),
        },
    )
