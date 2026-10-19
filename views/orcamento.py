"""Orçamento & Metas: teto mensal de gasto por categoria e quanto já foi usado
no mês. Conta todas as despesas com data no mês (inclusive parcelas ainda não
pagas — já estão comprometidas)."""
import pandas as pd
import streamlit as st

from database import excluir_orcamento, fetch_categorias, fetch_orcamentos, fetch_transacoes, salvar_orcamento
from utils import periodo
from utils.ui import PALETTE, _fmt_brl, chip, esc, kpi_row, page_header

page_header(
    "Orçamento & Metas",
    "Defina um teto mensal por categoria e acompanhe quanto ainda pode gastar.",
    "🎯",
)

flash = st.session_state.pop("orc_flash", None)
if flash:
    st.toast(flash, icon="✅")

mes = periodo.mes_ou_corrente()
chip(f"📅 {periodo.rotulo(mes, longo=True)}")
if periodo.atual() == periodo.TODOS:
    st.caption("O orçamento é mensal — mostrando o mês corrente. Escolha outro mês no menu.")

orcamentos = fetch_orcamentos()
df = pd.DataFrame(fetch_transacoes())
gasto_cat: dict[str, float] = {}
if not df.empty:
    desp = periodo.filtrar_df(df, mes)
    desp = desp[desp["tipo"] == "despesa"].copy()
    desp["categoria"] = desp["categoria"].fillna("Sem categoria")
    gasto_cat = desp.groupby("categoria")["valor"].sum().to_dict()


@st.dialog("🎯 Teto de categoria")
def dialogo_teto(categoria: str | None = None, teto: float | None = None):
    with st.form("form_teto", border=False):
        if categoria:
            st.markdown(f"**{esc(categoria)}**")
            cat = categoria
        else:
            existentes = {o["categoria"] for o in orcamentos}
            cat = st.selectbox("Categoria", [c for c in fetch_categorias() if c not in existentes], index=None,
                               accept_new_options=True, placeholder="Escolha ou digite")
        valor = st.number_input("Teto mensal (R$)", min_value=0.0, step=50.0, format="%.2f",
                                value=float(teto) if teto else None, placeholder="0,00")
        ok = st.form_submit_button("Salvar teto", use_container_width=True)
    if ok:
        if not (cat or "").strip() or not valor:
            st.error("Informe a categoria e um teto maior que zero.")
        else:
            salvar_orcamento(cat, valor)
            st.session_state["orc_flash"] = f"Teto de {cat.strip()} definido."
            st.rerun()


if not orcamentos:
    st.info("Nenhum teto definido ainda. Comece pelas categorias em que mais gasta.")
    if gasto_cat:
        st.markdown("**Maiores gastos do mês:**")
        for cat, valor in sorted(gasto_cat.items(), key=lambda x: -x[1])[:5]:
            if st.button(f"🎯 {cat} — {_fmt_brl(valor)}", key=f"sug_{cat}", use_container_width=True):
                dialogo_teto(cat, round(valor, -1) or None)
    with st.container(key="acao_rodape"):
        if st.button("➕ Definir teto", type="primary", use_container_width=True):
            dialogo_teto()
    st.stop()

# ---------- Resumo ----------
total_teto = sum(o["teto"] for o in orcamentos)
total_gasto = sum(gasto_cat.get(o["categoria"], 0.0) for o in orcamentos)
restante = total_teto - total_gasto
estourados = sum(1 for o in orcamentos if gasto_cat.get(o["categoria"], 0.0) > o["teto"])
kpi_row([
    {"label": "Orçado", "value": _fmt_brl(total_teto), "color": PALETTE["primary_soft"]},
    {"label": "Gasto", "value": _fmt_brl(total_gasto), "color": PALETTE["despesa"],
     "sub": f"{total_gasto / total_teto:.0%} do orçado" if total_teto else None},
    {"label": "Restante", "value": _fmt_brl(restante),
     "color": PALETTE["receita"] if restante >= 0 else PALETTE["despesa"]},
    {"label": "Estourados", "value": str(estourados),
     "color": PALETTE["despesa"] if estourados else PALETTE["receita"], "sub": "Categorias acima do teto"},
])

# ---------- Uma barra por categoria (mais apertadas primeiro) ----------
st.subheader("Categorias")


def _uso(o):
    return gasto_cat.get(o["categoria"], 0.0) / o["teto"] if o["teto"] else 0.0


for o in sorted(orcamentos, key=_uso, reverse=True):
    gasto = gasto_cat.get(o["categoria"], 0.0)
    uso = _uso(o)
    if uso > 1:
        tag, cor = '<span class="tag tag-pendente">Estourado</span>', PALETTE["despesa"]
    elif uso >= .8:
        tag, cor = '<span class="tag tag-parcial">Atenção</span>', PALETTE["alerta"]
    else:
        tag, cor = '<span class="tag tag-ok">No limite</span>', PALETTE["receita"]
    falta = o["teto"] - gasto
    with st.container(border=True):
        st.markdown(
            f'<div class="bud-head"><span class="bud-cat">{esc(o["categoria"])}</span>{tag}</div>'
            f'<div class="aloc-bar"><div style="width:{min(uso, 1) * 100:.0f}%;background:{cor}"></div></div>'
            f'<div class="bud-nums"><span>{_fmt_brl(gasto)} de {_fmt_brl(o["teto"])}</span>'
            f'<span>{"Sobram " + _fmt_brl(falta) if falta >= 0 else "Passou " + _fmt_brl(-falta)}</span></div>',
            unsafe_allow_html=True,
        )
        with st.container(key=f"row_orc_{o['id']}"):
            c1, c2 = st.columns(2)
            if c1.button("✏️ Ajustar", key=f"orc_ed_{o['id']}", use_container_width=True):
                dialogo_teto(o["categoria"], o["teto"])
            if c2.button("🗑️ Remover", key=f"orc_rm_{o['id']}", use_container_width=True):
                excluir_orcamento(o["id"])
                st.session_state["orc_flash"] = f"Teto de {o['categoria']} removido."
                st.rerun()

sem_teto = {c: v for c, v in gasto_cat.items() if c not in {o["categoria"] for o in orcamentos}}
if sem_teto:
    with st.expander(f"Gastos sem teto ({len(sem_teto)}) · {_fmt_brl(sum(sem_teto.values()))}"):
        for cat, valor in sorted(sem_teto.items(), key=lambda x: -x[1]):
            if st.button(f"🎯 {cat} — {_fmt_brl(valor)}", key=f"sem_{cat}", use_container_width=True):
                dialogo_teto(cat, round(valor, -1) or None)

with st.container(key="acao_rodape"):
    if st.button("➕ Definir teto", type="primary", use_container_width=True):
        dialogo_teto()
