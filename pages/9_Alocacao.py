"""Alocação Financeira (vínculo De/Para): destina partes de receitas para cobrir
despesas específicas, em relação N:N, com saldo livre/falta cobrir em cada card.

Fluxo escolhido: **modo de seleção** — no card de uma Entrada, "Vincular a
despesas" abre um diálogo para escolher uma ou várias Saídas e o valor de cada
(com sugestão automática); no card de uma Saída, "Cobrir com receitas" faz o
caminho inverso. Drag-and-drop foi descartado porque o app é usado sobretudo no
celular (Chrome/Android), onde arrastar entre duas listas longas é impreciso, e
porque o Streamlit não oferece DnD nativo.
"""
import datetime
import html

import plotly.graph_objects as go
import streamlit as st

from database import (
    AlocacaoInvalida,
    fetch_alocacoes,
    fetch_transacoes,
    init_db,
    remover_alocacao,
    salvar_alocacao,
)
from utils.allocation import TOLERANCIA, calcular_saldos, distribuir
from utils.ui import PALETTE, _fmt_brl, kpi_row, page_header, setup_page, style_fig
from utils.auth import require_login

setup_page("Alocação De/Para", "🔗")
require_login()
init_db()

page_header(
    "Alocação De/Para",
    "Defina para onde vai cada receita: vincule entradas às despesas que elas vão cobrir "
    "e acompanhe o que ainda está livre e o que falta quitar.",
    "🔗",
)

st.markdown(
    f"""<style>
    [class*="st-key-rm_aloc_"] button {{
        background: transparent !important; color: {PALETTE['despesa']} !important;
        border: 1px solid rgba(244,63,94,.45) !important;
    }}
    </style>""",
    unsafe_allow_html=True,
)

flash = st.session_state.pop("aloc_flash", None)
if flash:
    st.toast(flash, icon="✅")

transacoes = fetch_transacoes()
alocacoes = fetch_alocacoes()

if not transacoes:
    st.info("Nenhum lançamento cadastrado ainda. Registre receitas e despesas para começar a alocar.")
    st.stop()

saldos = calcular_saldos(transacoes, alocacoes)
por_id = {t["id"]: t for t in transacoes}

# Cores da barra de progresso por status (as tags usam as classes CSS de utils/ui.py).
COR_BARRA = {"total": PALETTE["receita"], "parcial": "#F59E0B", "nenhum": PALETTE["border"], "excedido": PALETTE["despesa"]}
ORDEM_STATUS = {"excedido": 0, "nenhum": 1, "parcial": 2, "total": 3}


def _md(texto):
    """Escapa o "$" de "R$": o Markdown do Streamlit trata "$...$" como LaTeX."""
    return str(texto).replace("$", "\\$")


def _nome(t):
    return t.get("descricao_original") or t.get("estabelecimento") or t.get("categoria") or f"Lançamento #{t['id']}"


def _data_br(t):
    try:
        return datetime.date.fromisoformat(str(t["data"])[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(t["data"])


def _fmt_mes(mes):
    if mes == "Todos":
        return "Todos os meses"
    ano, m = mes.split("-")
    return f"{m}/{ano}"


def _par(origem, outro_id):
    """(receita_id, despesa_id) a partir da transação de origem e do id do outro lado."""
    return (origem["id"], outro_id) if origem["tipo"] == "receita" else (outro_id, origem["id"])


# ---------- Filtros ----------
hoje = datetime.date.today()
meses = sorted({str(t["data"])[:7] for t in transacoes}, reverse=True)
mes_padrao = hoje.strftime("%Y-%m") if hoje.strftime("%Y-%m") in meses else meses[0]
opcoes_mes = ["Todos"] + meses

f1, f2, f3, f4 = st.columns([1, 1.3, 1.5, 1])
with f1:
    mes = st.selectbox("Mês", opcoes_mes, index=opcoes_mes.index(mes_padrao), format_func=_fmt_mes)
with f2:
    filtro_resp = st.multiselect("Responsável", sorted({t["responsavel"] for t in transacoes}))
with f3:
    busca = st.text_input("Buscar", placeholder="Descrição ou categoria").strip().lower()
with f4:
    st.write("")
    ocultar_quitados = st.toggle("Ocultar quitados", help="Esconde receitas totalmente alocadas e despesas totalmente cobertas.")


def _visivel(t):
    if mes != "Todos" and not str(t["data"]).startswith(mes):
        return False
    if filtro_resp and t["responsavel"] not in filtro_resp:
        return False
    if busca and busca not in f"{_nome(t)} {t.get('categoria') or ''}".lower():
        return False
    if ocultar_quitados and saldos[t["id"]]["status"] == "total":
        return False
    return True


def _ordenar(lista):
    return sorted(lista, key=lambda t: (ORDEM_STATUS[saldos[t["id"]]["status"]], str(t["data"])), reverse=False)


receitas = _ordenar([t for t in transacoes if t["tipo"] == "receita" and _visivel(t)])
despesas = _ordenar([t for t in transacoes if t["tipo"] == "despesa" and _visivel(t)])

# ---------- KPIs do recorte ----------
total_rec = sum(saldos[t["id"]]["total"] for t in receitas)
livre_rec = sum(saldos[t["id"]]["disponivel"] for t in receitas)
total_desp = sum(saldos[t["id"]]["total"] for t in despesas)
falta_desp = sum(saldos[t["id"]]["disponivel"] for t in despesas)
kpi_row([
    {"label": "Entradas", "value": _fmt_brl(total_rec), "color": PALETTE["receita"],
     "sub": f"{_fmt_brl(total_rec - livre_rec)} já alocado"},
    {"label": "Saldo livre", "value": _fmt_brl(livre_rec), "color": PALETTE["accent"],
     "sub": "Ainda sem destino definido"},
    {"label": "Saídas", "value": _fmt_brl(total_desp), "color": PALETTE["despesa"],
     "sub": f"{_fmt_brl(total_desp - falta_desp)} já coberto"},
    {"label": "Falta cobrir", "value": _fmt_brl(falta_desp),
     "color": PALETTE["receita"] if falta_desp <= TOLERANCIA else "#F59E0B",
     "sub": "Despesas sem receita destinada"},
])


# ---------- Diálogo de vínculo (modo de seleção) ----------
def abrir_dialogo(origem_id):
    # Sempre abre "limpo": descarta seleção/valores de uma abertura anterior.
    for chave in [k for k in st.session_state if str(k).startswith(f"dlg_{origem_id}_")]:
        del st.session_state[chave]
    dialogo_vincular(origem_id)


@st.dialog("🔗 Novo vínculo De/Para", width="large")
def dialogo_vincular(origem_id):
    origem = por_id[origem_id]
    s_origem = saldos[origem_id]
    eh_receita = origem["tipo"] == "receita"
    tipo_destino = "despesa" if eh_receita else "receita"
    col_origem, col_destino = ("receita_id", "despesa_id") if eh_receita else ("despesa_id", "receita_id")

    st.markdown(_md(
        f"**{'De' if eh_receita else 'Para'}:** {html.escape(_nome(origem))} · {_data_br(origem)}  \n"
        f"{'Saldo livre' if eh_receita else 'Falta cobrir'}: **{_fmt_brl(s_origem['disponivel'])}** "
        f"de {_fmt_brl(s_origem['total'])}"
    ))

    # Pares já vinculados ficam de fora (o valor deles é ajustado em "Editar vínculos").
    ja_vinculados = {a[col_destino] for a in alocacoes if a[col_origem] == origem_id}
    data_origem = datetime.date.fromisoformat(str(origem["data"])[:10])
    candidatos = sorted(
        (t for t in transacoes
         if t["tipo"] == tipo_destino and t["id"] not in ja_vinculados and saldos[t["id"]]["disponivel"] > TOLERANCIA),
        # mais próximos da data da origem primeiro
        key=lambda t: abs((datetime.date.fromisoformat(str(t["data"])[:10]) - data_origem).days),
    )
    if not candidatos:
        st.info(f"Não há {tipo_destino}s em aberto para vincular.")
        return

    rotulo_falta = "falta" if tipo_destino == "despesa" else "livre"
    escolhidos = st.multiselect(
        "Despesas que esta receita vai cobrir" if eh_receita else "Receitas que vão cobrir esta despesa",
        [t["id"] for t in candidatos],
        format_func=lambda i: f"{_nome(por_id[i])} · {_data_br(por_id[i])} · {rotulo_falta} {_fmt_brl(saldos[i]['disponivel'])}",
        placeholder="Busque e selecione uma ou mais…",
        key=f"dlg_{origem_id}_sel",
    )

    prefixo = f"dlg_{origem_id}_v"
    for chave in [k for k in st.session_state if str(k).startswith(prefixo)]:
        if int(chave[len(prefixo):]) not in escolhidos:
            del st.session_state[chave]

    # Sugestão automática: cobre cada item por inteiro, na ordem escolhida, até o
    # saldo da origem acabar. Só é aplicada ao item recém-adicionado — valores já
    # digitados pelo usuário são preservados.
    valores = {}
    for i in escolhidos:
        chave = f"{prefixo}{i}"
        if chave not in st.session_state:
            capacidade = s_origem["disponivel"] - sum(valores.values())
            st.session_state[chave] = distribuir(capacidade, [saldos[i]["disponivel"]])[0]
        valores[i] = st.number_input(
            _md(f"{_nome(por_id[i])} — {rotulo_falta} {_fmt_brl(saldos[i]['disponivel'])}"),
            min_value=0.0,
            max_value=float(saldos[i]["disponivel"]),
            step=50.0,
            format="%.2f",
            key=chave,
        )

    total = round(sum(valores.values()), 2)
    excede = total > s_origem["disponivel"] + TOLERANCIA
    if escolhidos:
        st.progress(
            min(total / s_origem["disponivel"], 1.0) if s_origem["disponivel"] > 0 else 1.0,
            text=_md(f"Total a vincular: {_fmt_brl(total)} de {_fmt_brl(s_origem['disponivel'])} "
                     f"{'livres' if eh_receita else 'em aberto'}"),
        )
    if excede:
        st.error(_md(
            f"O total ultrapassa {'o saldo livre da receita' if eh_receita else 'o que falta cobrir da despesa'} "
            f"em {_fmt_brl(total - s_origem['disponivel'])}. Reduza algum valor."
        ))

    if st.button("Confirmar vínculos", type="primary", use_container_width=True,
                 disabled=excede or total <= TOLERANCIA):
        erros, criados = [], 0
        for i, valor in valores.items():
            if valor <= TOLERANCIA:
                continue
            try:
                salvar_alocacao(*_par(origem, i), valor)
                criados += 1
            except AlocacaoInvalida as erro:
                erros.append(str(erro))
        if erros:
            st.error(_md("\n\n".join(erros)))
        else:
            st.session_state["aloc_flash"] = f"{criados} vínculo(s) criado(s)."
            st.rerun()


# ---------- Cards ----------
def _editar_vinculos(t, vinculos):
    eh_receita = t["tipo"] == "receita"
    with st.popover(f"✏️ Vínculos ({len(vinculos)})", use_container_width=True):
        for a in vinculos:
            outro = por_id[a["despesa_id"] if eh_receita else a["receita_id"]]
            # Pode subir até o que ainda sobra nos dois lados do par.
            folga = min(saldos[a["receita_id"]]["disponivel"], saldos[a["despesa_id"]]["disponivel"])
            sufixo = f"{a['id']}_{t['id']}"
            with st.form(f"form_aloc_{sufixo}", border=False):
                novo = st.number_input(
                    _md(f"{'→' if eh_receita else '←'} {_nome(outro)} · {_data_br(outro)}"),
                    min_value=0.01,
                    max_value=round(a["valor"] + folga, 2),
                    value=float(a["valor"]),
                    step=50.0,
                    format="%.2f",
                    key=f"val_aloc_{sufixo}",
                )
                b1, b2 = st.columns(2)
                salvar = b1.form_submit_button("💾 Salvar", use_container_width=True)
                remover = b2.form_submit_button("✖ Desvincular", use_container_width=True, key=f"rm_aloc_{sufixo}")
            if salvar:
                try:
                    salvar_alocacao(a["receita_id"], a["despesa_id"], novo)
                    st.session_state["aloc_flash"] = "Valor do vínculo atualizado."
                    st.rerun()
                except AlocacaoInvalida as erro:
                    st.error(_md(erro))
            if remover:
                remover_alocacao(a["id"])
                st.session_state["aloc_flash"] = "Vínculo removido (os lançamentos continuam intactos)."
                st.rerun()


def card(t):
    s = saldos[t["id"]]
    eh_receita = t["tipo"] == "receita"
    lbl_alocado, lbl_resto = ("Alocado", "Livre") if eh_receita else ("Coberto", "Falta")
    vinculos = [a for a in alocacoes if a["receita_id" if eh_receita else "despesa_id"] == t["id"]]

    meta = [_data_br(t), t["responsavel"], t["origem"]]
    if t.get("categoria"):
        meta.append(t["categoria"])
    if not eh_receita and t.get("pago"):
        meta.append("✔ paga")

    linhas_vinculo = "".join(
        f'<div><span>{"→" if eh_receita else "←"} '
        f'{html.escape(_nome(por_id[a["despesa_id"] if eh_receita else a["receita_id"]]))}</span>'
        f'<span>{_fmt_brl(a["valor"])}</span></div>'
        for a in vinculos
    )
    bloco_vinculos = f'<div class="aloc-links">{linhas_vinculo}</div>' if vinculos else ""

    with st.container(border=True):
        st.markdown(
            f'<div class="aloc-head"><span class="aloc-title">{html.escape(_nome(t))}</span>'
            f'<span class="tag {s["classe"]}">{s["rotulo"]}</span></div>'
            f'<div class="aloc-meta">{html.escape(" · ".join(str(m) for m in meta))}</div>'
            f'<div class="aloc-bar"><div style="width:{s["percentual"] * 100:.1f}%;background:{COR_BARRA[s["status"]]}"></div></div>'
            f'<div class="aloc-nums">'
            f'<div><span>Total</span><b>{_fmt_brl(s["total"])}</b></div>'
            f'<div><span>{lbl_alocado}</span><b>{_fmt_brl(s["alocado"])}</b></div>'
            f'<div><span>{lbl_resto}</span><b style="color:{PALETTE["receita"] if eh_receita else PALETTE["despesa"]}">'
            f'{_fmt_brl(s["disponivel"])}</b></div>'
            f'</div>{bloco_vinculos}',
            unsafe_allow_html=True,
        )
        with st.container(horizontal=True):
            if s["disponivel"] > TOLERANCIA:
                rotulo = "🔗 Vincular a despesas" if eh_receita else "🔗 Cobrir com receitas"
                if st.button(rotulo, key=f"vinc_{t['id']}", type="primary", use_container_width=True):
                    abrir_dialogo(t["id"])
            if vinculos:
                _editar_vinculos(t, vinculos)


def coluna(titulo, lista, chave, vazio):
    st.subheader(f"{titulo} ({len(lista)})")
    if not lista:
        st.caption(vazio)
        return
    limite = st.session_state.get(chave, 30)
    for t in lista[:limite]:
        card(t)
    if len(lista) > limite:
        if st.button(f"Mostrar mais ({len(lista) - limite} restantes)", key=f"mais_{chave}", use_container_width=True):
            st.session_state[chave] = limite + 30
            st.rerun()


col_ent, col_sai = st.columns(2)
with col_ent:
    coluna("💚 Entradas", receitas, "lim_receitas",
           "Nenhuma receita neste filtro. Tente outro mês — também é possível vincular a partir das saídas.")
with col_sai:
    coluna("💸 Saídas", despesas, "lim_despesas", "Nenhuma despesa neste filtro.")

# ---------- Mapa de fluxo ----------
ids_visiveis = {t["id"] for t in receitas} | {t["id"] for t in despesas}
fluxos = [a for a in alocacoes if a["receita_id"] in ids_visiveis or a["despesa_id"] in ids_visiveis]
if fluxos:
    with st.expander("🔀 Mapa de fluxo De → Para", expanded=False):
        nos = list(dict.fromkeys([a["receita_id"] for a in fluxos] + [a["despesa_id"] for a in fluxos]))
        indice = {i: n for n, i in enumerate(nos)}
        fig = go.Figure(go.Sankey(
            valueformat=",.2f",
            valuesuffix=" (R$)",
            node=dict(
                label=[_nome(por_id[i]) for i in nos],
                color=[PALETTE["receita"] if por_id[i]["tipo"] == "receita" else PALETTE["despesa"] for i in nos],
                pad=18, thickness=16,
            ),
            link=dict(
                source=[indice[a["receita_id"]] for a in fluxos],
                target=[indice[a["despesa_id"]] for a in fluxos],
                value=[a["valor"] for a in fluxos],
                color="rgba(99,102,241,0.35)",
            ),
        ))
        st.plotly_chart(style_fig(fig), use_container_width=True)
