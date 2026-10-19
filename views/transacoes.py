"""Transações: entradas e saídas do período num canvas de nós (estilo n8n),
com o vínculo De/Para (alocação de receita -> despesa) feito por fios.

Entradas ficam à esquerda (handle na borda direita), Saídas à direita (handle
na borda esquerda). Arrastar de um handle ao outro — ou tocar num e depois no
outro, mais preciso no celular — abre um popover para o valor; ao confirmar, o
vínculo vira uma linha com badge de valor e botão de excluir. O canvas é o
componente de `utils/fluxo.py`; aqui ficam os filtros, os KPIs e a gravação.
"""
import datetime

import streamlit as st

from database import (
    AlocacaoInvalida,
    fetch_alocacoes,
    fetch_transacoes,
    remover_alocacao,
    salvar_alocacao,
)
from utils import periodo
from utils.allocation import TOLERANCIA, calcular_saldos
from utils.fluxo import fluxo_alocacao
from utils.ui import PALETTE, _fmt_brl, chip, kpi_row, page_header

page_header(
    "Transações",
    "Entradas e saídas do período. Vincule cada receita às despesas que ela vai cobrir.",
    "💸",
)

FLUXO_KEY = "fluxo_aloc"


def _processar_acao():
    """Callback do canvas: grava a ação confirmada antes do rerun, para que a
    execução seguinte já leia os vínculos atualizados do banco."""
    acao = (st.session_state.get(FLUXO_KEY) or {}).get("acao")
    if not isinstance(acao, dict):
        return
    st.session_state["fluxo_rev"] = st.session_state.get("fluxo_rev", 0) + 1
    try:
        if acao.get("op") == "salvar":
            salvar_alocacao(int(acao["receita_id"]), int(acao["despesa_id"]), float(acao["valor"]))
            st.session_state["aloc_flash"] = f"Vínculo salvo: {_fmt_brl(float(acao['valor']))}."
        elif acao.get("op") == "remover":
            remover_alocacao(int(acao["id"]))
            st.session_state["aloc_flash"] = "Vínculo removido (os lançamentos continuam intactos)."
    except AlocacaoInvalida as erro:
        st.session_state["aloc_erro"] = str(erro)
    except (KeyError, TypeError, ValueError):
        st.session_state["aloc_erro"] = "Não foi possível entender a ação do canvas. Tente de novo."


flash = st.session_state.pop("aloc_flash", None)
if flash:
    st.toast(flash, icon=":material/check_circle:")
erro_aloc = st.session_state.pop("aloc_erro", None)
if erro_aloc:
    st.toast(erro_aloc, icon=":material/error:")

transacoes = fetch_transacoes()
alocacoes = fetch_alocacoes()

if not transacoes:
    st.info("Nenhum lançamento cadastrado ainda. Registre receitas e despesas para começar.")
    st.page_link("views/lancamento.py", label="Novo lançamento", icon="➕")
    st.stop()

saldos = calcular_saldos(transacoes, alocacoes)

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _nome(t):
    return t.get("descricao_original") or t.get("estabelecimento") or t.get("categoria") or f"Lançamento #{t['id']}"


def _data(t):
    return datetime.date.fromisoformat(str(t["data"])[:10])


def _data_curta(t):
    try:
        d = _data(t)
        return f"{d.day:02d} {MESES[d.month - 1]}"
    except ValueError:
        return str(t["data"])


# ---------- Filtros (recolhidos) ----------
chip(f"📅 {periodo.rotulo(longo=True)}")

with st.expander("Filtros", icon=":material/filter_list:"):
    filtro_resp = st.multiselect("Responsável", sorted({t["responsavel"] for t in transacoes}))
    busca = st.text_input("Buscar", placeholder="Descrição ou categoria").strip().lower()
    ocultar_quitados = st.toggle("Ocultar quitados", help="Esconde receitas totalmente alocadas e despesas totalmente cobertas.")


def _visivel(t):
    if not periodo.no_periodo(t):
        return False
    if filtro_resp and t["responsavel"] not in filtro_resp:
        return False
    if busca and busca not in f"{_nome(t)} {t.get('categoria') or ''}".lower():
        return False
    if ocultar_quitados and saldos[t["id"]]["status"] == "total":
        return False
    return True


no_recorte = [t for t in transacoes if _visivel(t)]
receitas = [t for t in no_recorte if t["tipo"] == "receita"]
despesas = [t for t in no_recorte if t["tipo"] == "despesa"]

# ---------- KPIs do recorte ----------
total_rec = sum(saldos[t["id"]]["total"] for t in receitas)
livre_rec = sum(saldos[t["id"]]["disponivel"] for t in receitas)
total_desp = sum(saldos[t["id"]]["total"] for t in despesas)
falta_desp = sum(saldos[t["id"]]["disponivel"] for t in despesas)
kpi_row([
    {"label": "Entradas", "value": _fmt_brl(total_rec), "color": PALETTE["receita"],
     "sub": f"{_fmt_brl(total_rec - livre_rec)} alocado"},
    {"label": "Saídas", "value": _fmt_brl(total_desp), "color": PALETTE["despesa"],
     "sub": f"{_fmt_brl(total_desp - falta_desp)} coberto"},
    {"label": "Saldo livre", "value": _fmt_brl(livre_rec), "color": PALETTE["accent"],
     "sub": "Receita sem destino"},
    {"label": "Falta cobrir", "value": _fmt_brl(falta_desp),
     "color": PALETTE["receita"] if falta_desp <= TOLERANCIA else PALETTE["alerta"],
     "sub": "Despesa sem receita"},
])


# ---------- Canvas De/Para ----------
def _ordem(t):
    return (str(t["data"]), t["id"])


ids_canvas = {t["id"] for t in no_recorte}
alocado_canvas = {}
for a in alocacoes:
    if a["receita_id"] in ids_canvas and a["despesa_id"] in ids_canvas:
        for lado in ("receita_id", "despesa_id"):
            alocado_canvas[a[lado]] = alocado_canvas.get(a[lado], 0.0) + a["valor"]


def _no(t):
    meta = [_data_curta(t), t.get("categoria") or "Sem categoria", t["responsavel"]]
    if t["tipo"] == "despesa" and t.get("pago"):
        meta.append("paga")
    return {
        "id": t["id"],
        "tipo": t["tipo"],
        "titulo": _nome(t),
        "meta": " · ".join(str(m) for m in meta),
        "total": saldos[t["id"]]["total"],
        # vínculos com contrapartes fora do canvas (outro período/filtro)
        "externo": round(saldos[t["id"]]["alocado"] - alocado_canvas.get(t["id"], 0.0), 2),
    }


nos = [_no(t) for t in sorted(receitas, key=_ordem, reverse=True)] +       [_no(t) for t in sorted(despesas, key=_ordem, reverse=True)]
arestas = [
    {"id": a["id"], "receita_id": a["receita_id"], "despesa_id": a["despesa_id"], "valor": a["valor"]}
    for a in alocacoes
    if a["receita_id"] in ids_canvas and a["despesa_id"] in ids_canvas
]

st.caption(f"{len(receitas)} entrada(s) · {len(despesas)} saída(s) · {len(arestas)} vínculo(s) no filtro")
if not no_recorte:
    st.info("Nada neste filtro. Troque o período no menu ou ajuste os filtros.")
else:
    fluxo_alocacao(nos, arestas, key=FLUXO_KEY, on_acao=_processar_acao,
                   revisao=st.session_state.get("fluxo_rev", 0))
