"""Visão Geral (dashboard): resumo do período, gráficos compactos e as próximas
contas a vencer. Pensado para caber numa tela de celular sem rolar muito."""
import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from database import fetch_cartoes, fetch_transacoes
from utils import periodo
from utils.cards import resumo_cartao
from utils.finance import marcar_realizadas
from utils.ui import (
    PALETTE, PLOTLY_CONFIG, _fmt_brl, chip, kpi_row, lista, page_header, row_card, style_fig,
)

page_header("Visão Geral", "Resumo do período: o que entrou, o que saiu e o que vem por aí.", "🏠")

hoje = datetime.date.today()
transacoes = fetch_transacoes()
cartoes = fetch_cartoes()

chip(f"📅 {periodo.rotulo(longo=True)}")

if not transacoes:
    st.info("Nenhum lançamento ainda. Comece por **Novo lançamento** ou **Importar PDF** no menu.")
    st.page_link("views/lancamento.py", label="Novo lançamento", icon="➕")
    st.stop()

df = pd.DataFrame(transacoes)
df["data_dt"] = pd.to_datetime(df["data"]).dt.date
df["realizada"] = marcar_realizadas(df, hoje)
df_p = periodo.filtrar_df(df)

receitas = df_p.loc[df_p["tipo"] == "receita", "valor"].sum()
desp_real = df_p.loc[(df_p["tipo"] == "despesa") & df_p["realizada"], "valor"].sum()
a_vencer = df_p.loc[(df_p["tipo"] == "despesa") & ~df_p["realizada"], "valor"].sum()
saldo = receitas - desp_real

# ---------- KPIs (grid 2x2 no celular) ----------
kpi_row([
    {"label": "Receitas", "value": _fmt_brl(receitas), "color": PALETTE["receita"], "sub": "No período"},
    {"label": "Despesas", "value": _fmt_brl(desp_real), "color": PALETTE["despesa"], "sub": "Já realizadas"},
    {"label": "Saldo livre", "value": _fmt_brl(saldo),
     "color": PALETTE["receita"] if saldo >= 0 else PALETTE["despesa"], "sub": "Receitas − despesas"},
    {"label": "A vencer", "value": _fmt_brl(a_vencer), "color": PALETTE["alerta"], "sub": "Compromissos do período"},
])

# ---------- Próximas contas a vencer ----------
st.subheader("Próximas contas")
proximas = []  # (data, titulo, meta, valor)
pend = df[(df["tipo"] == "despesa") & ~df["pago"].fillna(False).astype(bool)
          & (df["data_dt"] >= hoje) & df["cartao_id"].isna()]
for _, t in pend.sort_values("data_dt").head(8).iterrows():
    proximas.append((t["data_dt"], t["descricao_original"] or t["estabelecimento"] or "Despesa",
                     f'{t["categoria"] or "Sem categoria"} · {t["responsavel"]}', float(t["valor"])))
for c in cartoes:
    r = resumo_cartao(c, transacoes, hoje)
    fech = r["ciclos"]["fechada"]
    if fech["vencimento"] >= hoje and r["total_fechada"] > 0:
        proximas.append((fech["vencimento"], f"Fatura {c['nome']}", "Fatura fechada", r["total_fechada"]))
    if r["total_aberta"] > 0:
        proximas.append((r["ciclos"]["aberta"]["vencimento"], f"Fatura {c['nome']}",
                         f"Aberta · fecha dia {c['dia_fechamento']}", r["total_aberta"]))
proximas.sort(key=lambda p: p[0])

# Horizonte de 45 dias; se nada cair nele, mostra as 3 próximas mesmo assim.
proximas = [p for p in proximas if (p[0] - hoje).days <= 45] or proximas[:3]
if not proximas:
    st.caption("Nada a vencer. 🎉")
else:
    linhas = []
    for data, titulo, meta, valor in proximas[:6]:
        dias = (data - hoje).days
        if dias == 0:
            tag = '<span class="tag tag-pendente">Hoje</span>'
        elif dias <= 5:
            tag = f'<span class="tag tag-parcial">Em {dias} dia{"s" if dias > 1 else ""}</span>'
        else:
            tag = f'<span class="tag tag-livre">Em {dias} dias</span>'
        linhas.append(row_card(titulo, meta, _fmt_brl(valor), data=data, tag=tag))
    lista(linhas)

# ---------- Gráficos compactos ----------
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Para onde foi")
    despesas = df_p[(df_p["tipo"] == "despesa") & df_p["realizada"]].copy()
    if despesas.empty:
        st.caption("Sem despesas realizadas no período.")
    else:
        despesas["categoria"] = despesas["categoria"].fillna("Sem categoria")
        cat = despesas.groupby("categoria", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
        # Top 4 + "Outros": rosca legível no celular, sem legenda longa.
        if len(cat) > 5:
            cat = pd.concat([cat.head(4), pd.DataFrame([{"categoria": "Outros", "valor": cat["valor"].iloc[4:].sum()}])])
        fig = go.Figure(go.Pie(
            labels=cat["categoria"], values=cat["valor"], hole=.62, sort=False,
            textinfo="percent", textposition="inside", insidetextorientation="horizontal",
            hovertemplate="%{label}<br>R$ %{value:,.2f}<extra></extra>",
        ))
        fig.add_annotation(text=f"<b>{_fmt_brl(cat['valor'].sum())}</b>", showarrow=False, font=dict(size=14))
        st.plotly_chart(style_fig(fig, altura=230, legenda=False), use_container_width=True, config=PLOTLY_CONFIG)
        lista([
            row_card(r["categoria"], f"{r['valor'] / cat['valor'].sum():.0%} das despesas", _fmt_brl(r["valor"]))
            for _, r in cat.head(4).iterrows()
        ])

with col_b:
    st.subheader("Últimos 6 meses")
    df["mes"] = df["data"].astype(str).str[:7]
    meses = sorted({m for m in df["mes"] if m <= hoje.strftime("%Y-%m")})[-6:]
    hist = (
        df[df["mes"].isin(meses) & df["realizada"]]
        .groupby(["mes", "tipo"], as_index=False)["valor"].sum()
    )
    if hist.empty:
        st.caption("Sem histórico ainda.")
    else:
        hist["mes_lbl"] = hist["mes"].apply(periodo.rotulo)
        fig_b = px.bar(
            hist, x="mes_lbl", y="valor", color="tipo", barmode="group",
            color_discrete_map={"receita": PALETTE["receita"], "despesa": PALETTE["despesa"]},
            category_orders={"mes_lbl": [periodo.rotulo(m) for m in meses]},
        )
        fig_b.update_traces(hovertemplate="R$ %{y:,.2f}<extra></extra>")
        fig_b.update_yaxes(showticklabels=False, showgrid=False)
        st.plotly_chart(style_fig(fig_b, altura=260), use_container_width=True, config=PLOTLY_CONFIG)

st.page_link("views/relatorios.py", label="Ver relatórios completos", icon="📊")
