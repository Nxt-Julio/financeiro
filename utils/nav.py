"""Navegação do app: lista ordenada de rotas e o menu lateral (Drawer).

Usamos `st.navigation(..., position="hidden")` e desenhamos o menu nós mesmos
com `st.page_link`, para controlar a hierarquia:

1. Cabeçalho — quem está usando, saldo consolidado e seletor de período;
2. Operacional — o dia a dia;
3. Planejamento & Gestão — análise e metas;
4. Rodapé — Configurações, recolher (desktop) e Sair.

No celular o Streamlit já exibe a sidebar como gaveta sobreposta (o toque fora
fecha); o CSS em utils/ui.py adiciona o backdrop e o JS o gesto de swipe. No
desktop, "Recolher menu" deixa só os ícones (estado em `nav_compacto`).
"""
from dataclasses import dataclass
from typing import Literal

import pandas as pd
import streamlit as st
from streamlit.navigation.page import StreamlitPage

from database import get_responsaveis
from utils import periodo
from utils.auth import modo_sandbox, sair
from utils.finance import filtrar_realizadas
from utils.ui import PALETTE, _fmt_brl, esc

Secao = Literal["operacional", "planejamento", "rodape"]


@dataclass(frozen=True)
class NavItem:
    slug: str       # url_path da página (vazio = página inicial)
    titulo: str
    icone: str
    arquivo: str    # script em views/
    secao: Secao
    padrao: bool = False


# Ordem = ordem no menu. Dentro de cada seção, do uso mais frequente ao menos.
NAV: tuple[NavItem, ...] = (
    NavItem("", "Visão Geral", ":material/space_dashboard:", "views/dashboard.py", "operacional", padrao=True),
    NavItem("transacoes", "Transações", ":material/swap_vert:", "views/transacoes.py", "operacional"),
    NavItem("cartoes", "Contas & Cartões", ":material/credit_card:", "views/cartoes.py", "operacional"),
    NavItem("novo", "Novo lançamento", ":material/add_circle:", "views/lancamento.py", "operacional"),
    NavItem("importar", "Importar PDF", ":material/upload_file:", "views/importar_pdf.py", "operacional"),
    NavItem("orcamento", "Orçamento & Metas", ":material/savings:", "views/orcamento.py", "planejamento"),
    NavItem("relatorios", "Relatórios", ":material/bar_chart:", "views/relatorios.py", "planejamento"),
    NavItem("editar", "Editar lançamentos", ":material/edit_note:", "views/gerenciar.py", "planejamento"),
    NavItem("configuracoes", "Configurações", ":material/settings:", "views/configuracoes.py", "rodape"),
)

TITULOS_SECAO: dict[Secao, str] = {
    "operacional": "Operacional",
    "planejamento": "Planejamento & Gestão",
    "rodape": "Conta",
}


def build_pages() -> dict[str, StreamlitPage]:
    """slug -> st.Page, na ordem do menu."""
    return {
        item.slug: st.Page(
            item.arquivo, title=item.titulo, icon=item.icone,
            url_path=item.slug or None, default=item.padrao,
        )
        for item in NAV
    }


def item_atual(pages: dict[str, StreamlitPage], atual: StreamlitPage) -> NavItem:
    for item in NAV:
        if pages[item.slug] is atual or pages[item.slug].title == atual.title:
            return item
    return NAV[0]


def _cabecalho(transacoes: list[dict]):
    nome1, nome2 = get_responsaveis()
    iniciais = (nome1[:1] + nome2[:1]).upper()

    saldo = 0.0
    if transacoes:
        df = filtrar_realizadas(pd.DataFrame(transacoes))
        saldo = df.loc[df["tipo"] == "receita", "valor"].sum() - df.loc[df["tipo"] == "despesa", "valor"].sum()
    cor = PALETTE["receita"] if saldo >= 0 else PALETTE["despesa"]

    st.markdown(
        f'<div class="nav-head"><div class="nav-avatar">{esc(iniciais)}</div>'
        f'<div class="nav-who"><div class="nav-name">{esc(nome1)} &amp; {esc(nome2)}</div>'
        f'<div class="nav-saldo-lbl">Saldo consolidado</div>'
        f'<div class="nav-saldo" style="color:{cor}">{_fmt_brl(saldo)}</div></div></div>',
        unsafe_allow_html=True,
    )

    opcoes = periodo.opcoes(transacoes)
    if st.session_state.get("periodo") not in opcoes:
        st.session_state["periodo"] = periodo.mes_corrente()
    st.selectbox("Período", opcoes, key="periodo", format_func=lambda p: periodo.rotulo(p, longo=True))


def _link(item: NavItem, pages: dict[str, StreamlitPage], ativo: NavItem, compacto: bool):
    # O item ativo usa a chave fixa "nav_active" — o CSS (utils/ui.py) estiliza
    # `.st-key-nav_active` como selecionado, com o badge de tela atual.
    chave = "nav_active" if item == ativo else f"nav_{item.slug or 'inicio'}"
    with st.container(key=chave):
        st.page_link(pages[item.slug], label=item.titulo, icon=item.icone,
                     help=item.titulo if compacto else None)


def render_sidebar(pages: dict[str, StreamlitPage], ativo: NavItem, transacoes: list[dict]):
    compacto = st.session_state.get("nav_compacto", False)
    with st.sidebar:
        _cabecalho(transacoes)

        for secao in ("operacional", "planejamento", "rodape"):
            st.markdown(f'<div class="nav-section">{TITULOS_SECAO[secao]}</div>', unsafe_allow_html=True)
            for item in NAV:
                if item.secao == secao:
                    _link(item, pages, ativo, compacto)

        st.markdown('<div class="nav-section"></div>', unsafe_allow_html=True)
        if st.button("Expandir menu" if compacto else "Recolher menu", key="nav_recolher",
                     icon=":material/left_panel_open:" if compacto else ":material/left_panel_close:",
                     use_container_width=True):
            st.session_state["nav_compacto"] = not compacto
            st.rerun()
        if not modo_sandbox():
            if st.button("Sair", key="nav_sair", icon=":material/logout:", use_container_width=True):
                sair()
                st.rerun()
        else:
            st.markdown('<div class="nav-sandbox">🧪 Modo sandbox — dados de teste, login desligado.</div>',
                        unsafe_allow_html=True)

    st.html(f"<style>{_CSS_ATIVO}{_CSS_COMPACTO if compacto else ''}</style>")


# Item selecionado: realce, barra à esquerda e badge (ponto) à direita.
_CSS_ATIVO = """
.st-key-nav_active [data-testid="stPageLink-NavLink"] {
    background: linear-gradient(135deg, rgba(99,102,241,.28), rgba(34,211,238,.08)) !important;
    border-color: rgba(99,102,241,.40) !important;
    position: relative;
}
.st-key-nav_active [data-testid="stPageLink-NavLink"] p { font-weight: 700; }
.st-key-nav_active [data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"] { color: var(--primary-soft) !important; }
.st-key-nav_active [data-testid="stPageLink-NavLink"]::after {
    /* badge de "tela atual" */
    content: ""; position: absolute; right: 14px; top: 50%;
    width: 7px; height: 7px; margin-top: -3.5px; border-radius: 50%;
    background: var(--accent); box-shadow: 0 0 0 4px rgba(34,211,238,.16);
}
/* "Recolher" só existe no desktop — no celular o menu já é uma gaveta. */
@media (max-width: 767px) { .st-key-nav_recolher { display: none; } }
"""

# Modo recolhido (desktop): trilho de 76px só com ícones.
_CSS_COMPACTO = """
@media (min-width: 768px) {
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div {
        width: 76px !important; min-width: 76px !important; max-width: 76px !important;
    }
    [data-testid="stSidebarCollapseButton"] { display: none; }
    [data-testid="stSidebarUserContent"] { padding: 8px 10px 16px; }
    [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"],
    [data-testid="stSidebar"] .stButton button,
    [data-testid="stSidebar"] .stButton button > div { justify-content: center; padding: 0; }
    [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] .stButton button [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] .stSelectbox, .nav-who, .nav-sandbox,
    .st-key-nav_active [data-testid="stPageLink-NavLink"]::after { display: none !important; }
    .nav-section { font-size: 0; padding: 6px 0 4px; }
    .nav-head { padding: 0; justify-content: center; background: none; border: none; }
}
"""
