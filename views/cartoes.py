"""Contas & Cartões: cartões em carrossel (estilo carteira digital) com limite
disponível, fatura atual e melhor dia de compra; abaixo, os lançamentos da
fatura do cartão selecionado. Regras de ciclo/limite em utils/cards.py."""
import datetime

import pandas as pd
import streamlit as st

from database import (
    atribuir_cartao_sem_vinculo,
    excluir_cartao,
    fetch_cartoes,
    fetch_transacoes,
    salvar_cartao,
)
from utils import periodo
from utils.cards import resumo_cartao
from utils.ui import PALETTE, _fmt_brl, esc, kpi_row, lista, page_header, row_card

page_header(
    "Contas & Cartões",
    "Limite, fatura e melhor dia de compra de cada cartão, e o que já entrou na fatura aberta.",
    "💳",
)

hoje = datetime.date.today()
transacoes = fetch_transacoes()
cartoes = fetch_cartoes()

flash = st.session_state.pop("cc_flash", None)
if flash:
    st.toast(flash, icon="✅")

CORES = {"Roxo": "#7C3AED", "Índigo": "#4F46E5", "Azul": "#2563EB", "Verde": "#059669",
         "Laranja": "#EA580C", "Rosa": "#DB2777", "Grafite": "#374151"}


def _dia_mes(d: datetime.date) -> str:
    return d.strftime("%d/%m")


def form_cartao(cartao: dict | None = None):
    """Formulário de criação/edição (dentro de um diálogo)."""
    c = cartao or {}
    cores = list(CORES)
    cor_atual = next((n for n, h in CORES.items() if h == c.get("cor")), cores[0])
    with st.form(f"form_cartao_{c.get('id', 'novo')}", border=False):
        nome = st.text_input("Nome do cartão", value=c.get("nome", ""), placeholder="Ex: Nubank Julio")
        limite = st.number_input("Limite total (R$)", min_value=0.0, step=100.0, format="%.2f",
                                 value=float(c.get("limite", 0.0)))
        with st.container(key=f"row_dias_{c.get('id', 'novo')}"):
            col1, col2 = st.columns(2)
            fech = col1.number_input("Dia do fechamento", min_value=1, max_value=31, step=1,
                                     value=int(c.get("dia_fechamento", 1)))
            venc = col2.number_input("Dia do vencimento", min_value=1, max_value=31, step=1,
                                     value=int(c.get("dia_vencimento", 10)))
        cor = st.selectbox("Cor", cores, index=cores.index(cor_atual))
        enviar = st.form_submit_button("Salvar cartão", use_container_width=True)
    if enviar:
        if not nome.strip():
            st.error("Informe o nome do cartão.")
            return
        if any(o["nome"].lower() == nome.strip().lower() and o["id"] != c.get("id") for o in cartoes):
            st.error("Já existe um cartão com esse nome.")
            return
        salvar_cartao(nome, limite, fech, venc, CORES[cor], id_cartao=c.get("id"))
        st.session_state["cc_flash"] = "Cartão salvo."
        st.rerun()


@st.dialog("💳 Novo cartão")
def dialogo_novo():
    form_cartao()


@st.dialog("✏️ Editar cartão")
def dialogo_editar(cartao):
    form_cartao(cartao)
    st.divider()
    if st.button("🗑️ Excluir cartão", use_container_width=True, key="cc_excluir"):
        excluir_cartao(cartao["id"])
        st.session_state.pop("cc_sel", None)
        st.session_state["cc_flash"] = "Cartão excluído (os lançamentos continuam, sem vínculo)."
        st.rerun()


if not cartoes:
    st.info("Nenhum cartão cadastrado. Cadastre seus cartões para acompanhar limite, faturas e vencimentos.")
    with st.container(key="acao_rodape"):
        if st.button("➕ Cadastrar cartão", type="primary", use_container_width=True):
            dialogo_novo()
    st.stop()

resumos = {c["id"]: resumo_cartao(c, transacoes, hoje) for c in cartoes}

# ---------- Totais ----------
total_limite = sum(r["limite"] for r in resumos.values())
total_disp = sum(r["disponivel"] for r in resumos.values())
total_aberta = sum(r["total_aberta"] for r in resumos.values())
prox_venc = min(r["ciclos"]["aberta"]["vencimento"] for r in resumos.values())
kpi_row([
    {"label": "Limite disponível", "value": _fmt_brl(total_disp), "color": PALETTE["receita"],
     "sub": f"de {_fmt_brl(total_limite)}"},
    {"label": "Faturas abertas", "value": _fmt_brl(total_aberta), "color": PALETTE["despesa"],
     "sub": f"Próx. venc. {_dia_mes(prox_venc)}"},
])

# ---------- Carteira (carrossel) ----------
ids = [c["id"] for c in cartoes]
if st.session_state.get("cc_sel") not in ids:
    st.session_state["cc_sel"] = ids[0]
sel_id = st.session_state["cc_sel"]

blocos = []
for c in cartoes:
    r = resumos[c["id"]]
    blocos.append(
        f'<div class="cc{" sel" if c["id"] == sel_id else ""}" style="--cc:{esc(c["cor"])}">'
        f'<div class="cc-top"><span>{esc(c["nome"])}</span><span class="cc-chip"></span></div>'
        f'<div><div class="cc-lbl">Limite disponível</div><div class="cc-big">{_fmt_brl(r["disponivel"])}</div>'
        f'<div class="cc-bar"><div style="width:{r["percentual_usado"] * 100:.0f}%"></div></div>'
        f'<div class="cc-lbl">{_fmt_brl(r["usado"])} usado de {_fmt_brl(r["limite"])}</div></div>'
        f'<div class="cc-row">'
        f'<div><span class="cc-lbl">Fatura atual</span><b>{_fmt_brl(r["total_aberta"])}</b></div>'
        f'<div><span class="cc-lbl">Vence</span><b>{_dia_mes(r["ciclos"]["aberta"]["vencimento"])}</b></div>'
        f'<div><span class="cc-lbl">Melhor dia</span><b>Dia {r["melhor_dia"]}</b></div>'
        f'</div></div>'
    )
st.markdown(f'<div class="carousel">{"".join(blocos)}</div>', unsafe_allow_html=True)

nomes = {c["id"]: c["nome"] for c in cartoes}
st.pills("Cartão", ids, format_func=nomes.get, key="cc_sel", required=True, label_visibility="collapsed")
sel = next(c for c in cartoes if c["id"] == st.session_state["cc_sel"])
r = resumos[sel["id"]]

with st.container(key="row_cc_acoes"):
    a1, a2 = st.columns(2)
    if a1.button("✏️ Editar", use_container_width=True, key="cc_editar"):
        dialogo_editar(sel)
    if a2.button("➕ Novo cartão", use_container_width=True, key="cc_novo"):
        dialogo_novo()

# Lançamentos de cartão antigos (antes desta tela) não têm cartão definido.
sem_cartao = [t for t in transacoes if t["origem"] == "Cartão" and t["tipo"] == "despesa" and not t.get("cartao_id")]
if sem_cartao:
    with st.expander(f"⚠️ {len(sem_cartao)} lançamento(s) de cartão sem cartão definido"):
        st.caption("Compras com origem \"Cartão\" registradas antes do cadastro de cartões não entram em "
                   "nenhuma fatura. Você pode vinculá-las todas a este cartão, ou uma a uma em **Editar lançamentos**.")
        if st.button(f"Vincular todas a {sel['nome']}", use_container_width=True, key="cc_atribuir"):
            n = atribuir_cartao_sem_vinculo(sel["id"])
            st.session_state["cc_flash"] = f"{n} lançamento(s) vinculado(s) a {sel['nome']}."
            st.rerun()

# ---------- Fatura do cartão selecionado ----------
st.subheader(f"Fatura · {sel['nome']}")
FATURAS = {"aberta": "Aberta", "fechada": "Anterior"}
qual = st.segmented_control("Fatura", list(FATURAS), format_func=FATURAS.get, default="aberta",
                            required=True, key="cc_fatura", label_visibility="collapsed", width="stretch")
ciclo = r["ciclos"][qual]
itens = r[qual]
total = r["total_aberta"] if qual == "aberta" else r["total_fechada"]
situacao = "fecha" if qual == "aberta" else "fechou"
st.markdown(
    f'<div class="row-card"><div class="row-main"><div class="row-title">Total {_fmt_brl(total)}</div>'
    f'<div class="row-meta">{_dia_mes(ciclo["inicio"])} a {_dia_mes(ciclo["fim"] - datetime.timedelta(days=1))} · '
    f'{situacao} {_dia_mes(ciclo["fim"])} · vence {ciclo["vencimento"].strftime("%d/%m/%Y")}</div></div></div>',
    unsafe_allow_html=True,
)
if not itens:
    st.caption("Nenhum lançamento nesta fatura.")
else:
    lista([
        row_card(
            t["descricao_original"] or t["estabelecimento"] or "Compra",
            f'{t["categoria"] or "Sem categoria"} · {t["responsavel"]}',
            _fmt_brl(float(t["valor"])),
            data=datetime.date.fromisoformat(str(t["data"])[:10]),
            cor_valor=PALETTE["despesa"],
        )
        for t in itens
    ])

# ---------- Outras origens (conta e dinheiro) ----------
st.subheader("Conta & dinheiro")
df = periodo.filtrar_df(pd.DataFrame(transacoes))
outras = df[df["origem"] != "Cartão"] if not df.empty else df
if outras.empty:
    st.caption(f"Sem movimentação fora do cartão em {periodo.rotulo(longo=True).lower()}.")
else:
    linhas = []
    for origem, grupo in outras.groupby("origem"):
        ent = grupo.loc[grupo["tipo"] == "receita", "valor"].sum()
        sai = grupo.loc[grupo["tipo"] == "despesa", "valor"].sum()
        linhas.append(row_card(
            origem, f"Entradas {_fmt_brl(ent)} · Saídas {_fmt_brl(sai)}", _fmt_brl(ent - sai),
            cor_valor=PALETTE["receita"] if ent - sai >= 0 else PALETTE["despesa"],
        ))
    lista(linhas)
    st.caption(periodo.rotulo(longo=True))
