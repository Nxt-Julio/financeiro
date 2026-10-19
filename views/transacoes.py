"""Transações: entradas e saídas do período em cards, com o vínculo De/Para
(alocação de receita -> despesa).

Fluxo de vínculo: **modo de seleção** — no card de uma Entrada, "Vincular" abre
um diálogo (bottom sheet no celular) para escolher uma ou várias Saídas e o
valor de cada (com sugestão automática); no card de uma Saída, "Cobrir" faz o
caminho inverso. Drag-and-drop foi descartado porque o app é usado sobretudo no
celular (Chrome/Android), onde arrastar entre duas listas longas é impreciso, e
porque o Streamlit não oferece DnD nativo.
"""
import datetime

import plotly.graph_objects as go
import streamlit as st

from database import (
    AlocacaoInvalida,
    fetch_alocacoes,
    fetch_transacoes,
    remover_alocacao,
    salvar_alocacao,
)
from utils import periodo
from utils.allocation import TOLERANCIA, calcular_saldos, distribuir
from utils.ui import PALETTE, PLOTLY_CONFIG, _fmt_brl, chip, esc, kpi_row, md, page_header, style_fig

page_header(
    "Transações",
    "Entradas e saídas do período. Vincule cada receita às despesas que ela vai cobrir.",
    "💸",
)

st.html(
    f"""<style>
    [class*="st-key-rm_aloc_"] button {{
        background: transparent !important; color: {PALETTE['despesa']} !important;
        border: 1px solid rgba(244,63,94,.45) !important;
    }}
    </style>"""
)

flash = st.session_state.pop("aloc_flash", None)
if flash:
    st.toast(flash, icon="✅")

transacoes = fetch_transacoes()
alocacoes = fetch_alocacoes()

if not transacoes:
    st.info("Nenhum lançamento cadastrado ainda. Registre receitas e despesas para começar.")
    st.page_link("views/lancamento.py", label="Novo lançamento", icon="➕")
    st.stop()

saldos = calcular_saldos(transacoes, alocacoes)
por_id = {t["id"]: t for t in transacoes}

# Cores da barra de progresso por status (as tags usam as classes CSS de utils/ui.py).
COR_BARRA = {"total": PALETTE["receita"], "parcial": PALETTE["alerta"], "nenhum": PALETTE["border"], "excedido": PALETTE["despesa"]}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _nome(t):
    return t.get("descricao_original") or t.get("estabelecimento") or t.get("categoria") or f"Lançamento #{t['id']}"


def _data(t):
    return datetime.date.fromisoformat(str(t["data"])[:10])


def _data_br(t):
    try:
        return _data(t).strftime("%d/%m/%Y")
    except ValueError:
        return str(t["data"])


def _data_curta(t):
    try:
        d = _data(t)
        return f"{d.day:02d} {MESES[d.month - 1]}"
    except ValueError:
        return str(t["data"])


def _par(origem, outro_id):
    """(receita_id, despesa_id) a partir da transação de origem e do id do outro lado."""
    return (origem["id"], outro_id) if origem["tipo"] == "receita" else (outro_id, origem["id"])


# ---------- Filtros: segmented control + extras recolhidos ----------
chip(f"📅 {periodo.rotulo(longo=True)}")
TIPOS_VISAO = {"todas": "Todas", "receita": "Entradas", "despesa": "Saídas"}
visao = st.segmented_control(
    "Mostrar", list(TIPOS_VISAO), format_func=TIPOS_VISAO.get, default="todas",
    required=True, key="tx_visao", label_visibility="collapsed", width="stretch",
)

with st.expander("🔎 Filtros"):
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


# ---------- Bottom sheet de vínculo (modo de seleção) ----------
def abrir_dialogo(origem_id):
    # Sempre abre "limpo": descarta seleção/valores de uma abertura anterior.
    for chave in [k for k in st.session_state if str(k).startswith(f"dlg_{origem_id}_")]:
        del st.session_state[chave]
    dialogo_vincular(origem_id)


@st.dialog("🔗 Vincular De/Para", width="large")
def dialogo_vincular(origem_id):
    origem = por_id[origem_id]
    s_origem = saldos[origem_id]
    eh_receita = origem["tipo"] == "receita"
    tipo_destino = "despesa" if eh_receita else "receita"
    col_origem, col_destino = ("receita_id", "despesa_id") if eh_receita else ("despesa_id", "receita_id")

    st.markdown(md(
        f"**{'De' if eh_receita else 'Para'}:** {esc(_nome(origem))} · {_data_br(origem)}  \n"
        f"{'Saldo livre' if eh_receita else 'Falta cobrir'}: **{_fmt_brl(s_origem['disponivel'])}** "
        f"de {_fmt_brl(s_origem['total'])}"
    ))

    # Pares já vinculados ficam de fora (o valor deles é ajustado em "Vínculos").
    ja_vinculados = {a[col_destino] for a in alocacoes if a[col_origem] == origem_id}
    data_origem = _data(origem)
    candidatos = sorted(
        (t for t in transacoes
         if t["tipo"] == tipo_destino and t["id"] not in ja_vinculados and saldos[t["id"]]["disponivel"] > TOLERANCIA),
        # mais próximos da data da origem primeiro
        key=lambda t: abs((_data(t) - data_origem).days),
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
            md(f"{_nome(por_id[i])} — {rotulo_falta} {_fmt_brl(saldos[i]['disponivel'])}"),
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
            text=md(f"Total a vincular: {_fmt_brl(total)} de {_fmt_brl(s_origem['disponivel'])} "
                    f"{'livres' if eh_receita else 'em aberto'}"),
        )
    if excede:
        st.error(md(
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
            st.error(md("\n\n".join(erros)))
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
                    md(f"{'→' if eh_receita else '←'} {_nome(outro)} · {_data_br(outro)}"),
                    min_value=0.01,
                    max_value=round(a["valor"] + folga, 2),
                    value=float(a["valor"]),
                    step=50.0,
                    format="%.2f",
                    key=f"val_aloc_{sufixo}",
                )
                with st.container(key=f"row_aloc_{sufixo}"):
                    b1, b2 = st.columns(2)
                    salvar = b1.form_submit_button("💾 Salvar", use_container_width=True)
                    remover = b2.form_submit_button("✖ Desvincular", use_container_width=True, key=f"rm_aloc_{sufixo}")
            if salvar:
                try:
                    salvar_alocacao(a["receita_id"], a["despesa_id"], novo)
                    st.session_state["aloc_flash"] = "Valor do vínculo atualizado."
                    st.rerun()
                except AlocacaoInvalida as erro:
                    st.error(md(erro))
            if remover:
                remover_alocacao(a["id"])
                st.session_state["aloc_flash"] = "Vínculo removido (os lançamentos continuam intactos)."
                st.rerun()


def card(t):
    s = saldos[t["id"]]
    eh_receita = t["tipo"] == "receita"
    vinculos = [a for a in alocacoes if a["receita_id" if eh_receita else "despesa_id"] == t["id"]]

    meta = [_data_curta(t), t.get("categoria") or "Sem categoria", t["responsavel"]]
    if not eh_receita and t.get("pago"):
        meta.append("✔ paga")
    sinal, cor = ("+", PALETTE["receita"]) if eh_receita else ("−", PALETTE["despesa"])
    resto = f"{'Livre' if eh_receita else 'Falta'} {_fmt_brl(s['disponivel'])}" if s["status"] != "total" else (
        "Tudo alocado" if eh_receita else "Tudo coberto")

    linhas_vinculo = "".join(
        f'<div><span>{"→" if eh_receita else "←"} '
        f'{esc(_nome(por_id[a["despesa_id"] if eh_receita else a["receita_id"]]))}</span>'
        f'<span>{_fmt_brl(a["valor"])}</span></div>'
        for a in vinculos
    )
    bloco_vinculos = f'<div class="aloc-links">{linhas_vinculo}</div>' if vinculos else ""

    with st.container(border=True):
        st.markdown(
            f'<div class="tx-head"><div><div class="tx-title">{esc(_nome(t))}</div>'
            f'<div class="tx-meta">{esc(" · ".join(str(m) for m in meta))}</div></div>'
            f'<div class="tx-val" style="color:{cor}">{sinal} {_fmt_brl(s["total"])}</div></div>'
            f'<div class="aloc-bar"><div style="width:{s["percentual"] * 100:.1f}%;background:{COR_BARRA[s["status"]]}"></div></div>'
            f'<div class="tx-foot"><span class="tag {s["classe"]}">{s["rotulo"]}</span><small>{resto}</small></div>'
            f'{bloco_vinculos}',
            unsafe_allow_html=True,
        )
        acoes = (["vincular"] if s["disponivel"] > TOLERANCIA else []) + (["editar"] if vinculos else [])
        if acoes:
            # Uma ação ocupa a largura toda; duas ficam lado a lado (container "row_*").
            with st.container(key=f"row_card_{t['id']}"):
                for acao, col in zip(acoes, st.columns(len(acoes))):
                    with col:
                        if acao == "vincular":
                            rotulo = "🔗 Vincular a despesas" if eh_receita else "🔗 Cobrir com receitas"
                            if st.button(rotulo, key=f"vinc_{t['id']}", type="primary", use_container_width=True):
                                abrir_dialogo(t["id"])
                        else:
                            _editar_vinculos(t, vinculos)


lista_visao = {"todas": no_recorte, "receita": receitas, "despesa": despesas}[visao]
lista_visao = sorted(lista_visao, key=lambda t: (str(t["data"]), t["id"]), reverse=True)

st.caption(f"{len(lista_visao)} lançamento(s) · mais recentes primeiro")
if not lista_visao:
    st.info("Nada neste filtro. Troque o período no menu ou ajuste os filtros.")
limite = st.session_state.get(f"lim_{visao}", 25)
for t in lista_visao[:limite]:
    card(t)
if len(lista_visao) > limite:
    if st.button(f"Mostrar mais ({len(lista_visao) - limite} restantes)", key=f"mais_{visao}", use_container_width=True):
        st.session_state[f"lim_{visao}"] = limite + 25
        st.rerun()

# ---------- Mapa de fluxo ----------
ids_visiveis = {t["id"] for t in no_recorte}
fluxos = [a for a in alocacoes if a["receita_id"] in ids_visiveis or a["despesa_id"] in ids_visiveis]
if fluxos:
    with st.expander("🔀 Mapa de fluxo De → Para"):
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
        st.plotly_chart(style_fig(fig, legenda=False), use_container_width=True, config=PLOTLY_CONFIG)
