"""Canvas de Alocação De/Para no estilo n8n (componente Streamlit v2).

Entradas (receitas) à esquerda com um handle na borda direita, Saídas
(despesas) à direita com um handle na borda esquerda. O usuário arrasta (ou
toca e toca) de um handle ao outro, informa o valor num popover e o vínculo vira
uma curva Bezier com badge de valor + botão de excluir.

Por que um componente próprio (SVG + pointer events) e não React Flow: o app é
Streamlit puro, sem pipeline npm/bundler no deploy (Coolify instala só o
requirements.txt). `st.components.v2` aceita HTML/CSS/JS inline, roda sem
iframe e fala com o Python por trigger values — então o canvas inteiro cabe em
alguns arquivos estáticos em `assets/fluxo/`, sem build. Pointer events (e não
o DnD do HTML5) porque o DnD nativo não funciona com toque no Chrome/Android.

Fonte dos arquivos JS (concatenados nesta ordem, num único módulo ES):
- `node.js`    — card do nó com os handles e o cálculo de saldos;
- `edges.js`   — arestas SVG e badge de valor/excluir;
- `popover.js` — popover de confirmação do valor;
- `canvas.js`  — o canvas, a mecânica de conexão e a ponte com o Python.
"""
from pathlib import Path

import streamlit as st

from utils.allocation import STATUS_DESPESA, STATUS_RECEITA, TOLERANCIA
from utils.ui import PALETTE

_ASSETS = Path(__file__).resolve().parent.parent / "assets" / "fluxo"
_JS_ORDEM = ("node.js", "edges.js", "popover.js", "canvas.js")


def _carregar():
    js = "\n\n".join((_ASSETS / nome).read_text(encoding="utf-8") for nome in _JS_ORDEM)
    tokens = ":host {" + "".join(f"--{k.replace('_', '-')}: {v};" for k, v in PALETTE.items()) + "}\n"
    css = tokens + (_ASSETS / "fluxo.css").read_text(encoding="utf-8")
    return st.components.v2.component("fluxo_alocacao", html="", css=css, js=js)


_componente = _carregar()


def fluxo_alocacao(nodes: list[dict], edges: list[dict], *, key: str, on_acao, revisao: int = 0):
    """Desenha o canvas.

    nodes: [{id, tipo ("receita"|"despesa"), titulo, meta, total, externo}] —
        `externo` é o quanto do nó já está alocado a contrapartes fora do canvas
        (outro período/filtro), para os saldos baterem com os do banco.
    edges: [{id, receita_id, despesa_id, valor}] com as duas pontas no canvas.
    on_acao: callback chamado (antes do rerun) quando o usuário confirma uma
        ação; ela fica em `st.session_state[key]["acao"]`:
        {"op": "salvar", "receita_id", "despesa_id", "valor"} ou {"op": "remover", "id"}.
    revisao: muda a cada ação processada para forçar o JS a descartar o estado
        otimista mesmo quando os dados voltam iguais (ex.: ação recusada).
    """
    rotulos = {
        "receita": {k: list(v) for k, v in STATUS_RECEITA.items()},
        "despesa": {k: list(v) for k, v in STATUS_DESPESA.items()},
    }
    return _componente(
        key=key,
        data={"nodes": nodes, "edges": edges, "rotulos": rotulos, "tol": TOLERANCIA, "revisao": revisao},
        on_acao_change=on_acao,
    )
