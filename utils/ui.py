"""Sistema de design compartilhado do app (tema, CSS mobile-first e componentes).

O `app.py` (roteador) chama `setup_app()` uma única vez por execução — ele
configura a página e injeta o CSS/JS do shell. As telas em `views/` só usam os
componentes (`page_header`, `kpi_row`, `card_carousel`, ...).

Estratégia mobile-first: o CSS base é o do celular (Chrome/Android, ~360-420px);
`@media (min-width: 768px)` e `(min-width: 1100px)` acrescentam o layout de
tablet/desktop. Áreas seguras (notch/barra de gestos) via `env(safe-area-inset-*)`
— o JS do shell adiciona `viewport-fit=cover` ao meta viewport para ativá-las.
"""
import html as _html

import streamlit as st

# Paleta central — referenciada tanto no CSS quanto nos gráficos Plotly.
PALETTE = {
    "bg": "#0E1016",
    "surface": "#171A23",
    "surface_2": "#1F2330",
    "border": "#2A2F3D",
    "text": "#E6E8EE",
    "muted": "#9AA1B2",
    "primary": "#6366F1",
    "primary_soft": "#818CF8",
    "receita": "#22C55E",
    "despesa": "#F43F5E",
    "accent": "#22D3EE",
    "alerta": "#F59E0B",
}

# Sequência de cores para gráficos categóricos (pizza, barras por categoria).
CHART_SEQUENCE = [
    "#6366F1", "#22D3EE", "#22C55E", "#F59E0B", "#F43F5E",
    "#A855F7", "#14B8A6", "#EAB308", "#EC4899", "#38BDF8",
]

# Config padrão do st.plotly_chart: sem barra de ferramentas (polui no celular).
PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}

_TOKENS = ":root {" + "".join(f"--{k.replace('_', '-')}: {v};" for k, v in PALETTE.items()) + "}"

_CSS = """
:root {
    --tap: 44px;                       /* alvo de toque mínimo */
    --radius: 16px;
    --gutter: 16px;
    --topbar: 56px;
    --safe-top: env(safe-area-inset-top, 0px);
    --safe-bottom: env(safe-area-inset-bottom, 0px);
    --safe-left: env(safe-area-inset-left, 0px);
    --safe-right: env(safe-area-inset-right, 0px);
}

/* ================= Base ================= */
.stApp {
    background:
        radial-gradient(900px 500px at 10% -10%, rgba(99,102,241,0.14), transparent 60%),
        radial-gradient(800px 400px at 100% 0%, rgba(34,211,238,0.07), transparent 55%),
        var(--bg);
}
.block-container {
    max-width: 100%;
    padding: calc(var(--topbar) + var(--safe-top) + 12px)
             calc(var(--gutter) + var(--safe-right))
             calc(32px + var(--safe-bottom))
             calc(var(--gutter) + var(--safe-left));
}
[data-testid="stVerticalBlock"] { gap: .85rem; }
[data-testid="stHorizontalBlock"] { gap: .75rem; }
/* `.stApp [data-testid]` ganha da especificidade do CSS do próprio Streamlit. */
.stApp [data-testid="stHeading"] :is(h1, h2, h3), .stApp [data-testid="stMarkdownContainer"] :is(h1, h2, h3) {
    letter-spacing: -0.02em; font-weight: 700;
}
.stApp [data-testid="stHeading"] h1, .stApp [data-testid="stMarkdownContainer"] h1 { font-size: 1.5rem; }
.stApp [data-testid="stHeading"] h2, .stApp [data-testid="stMarkdownContainer"] h2 { font-size: 1.25rem; }
.stApp [data-testid="stHeading"] h3, .stApp [data-testid="stMarkdownContainer"] h3 { font-size: 1.1rem; padding: .4rem 0 0; }
hr { border-color: var(--border); }

/* Colunas do Streamlit empilham no celular (exceto containers "row_*",
   usados para pares de botões que devem ficar lado a lado). */
@media (max-width: 767px) {
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        min-width: 100% !important; flex: 1 1 100% !important;
    }
    [class*="st-key-row_"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; }
    [class*="st-key-row_"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        min-width: 0 !important; flex: 1 1 0 !important;
    }
}

/* ================= Barra superior (header mobile) ================= */
[data-testid="stHeader"] {
    height: calc(var(--topbar) + var(--safe-top));
    padding-top: var(--safe-top);
    background: rgba(14,16,22,.82);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border-bottom: 1px solid var(--border);
}
[data-testid="stHeader"]::after {
    /* Título da tela atual — definido por tela em set_titulo_topo(). */
    content: var(--page-title, "");
    position: absolute;
    left: 64px; right: 64px;
    bottom: 0; height: var(--topbar);
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 1.02rem; color: var(--text);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    pointer-events: none;
}
[data-testid="stToolbar"] { height: var(--topbar); }
/* Botão hambúrguer: troca o ícone ">>" do Streamlit pelo ícone "menu". */
[data-testid="stExpandSidebarButton"] {
    width: var(--tap); height: var(--tap);
    border-radius: 12px;
    background: var(--surface-2) !important;
    border: 1px solid var(--border) !important;
}
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] { font-size: 0 !important; }
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"]::before {
    content: "menu"; font-size: 24px; color: var(--text);
}

/* ================= Sidebar / Drawer ================= */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, var(--surface), var(--bg));
    border-right: 1px solid var(--border);
}
[data-testid="stSidebarHeader"] {
    padding: calc(4px + var(--safe-top)) 8px 0; height: auto; min-height: 0; margin-bottom: 0;
}
[data-testid="stSidebarHeader"] [data-testid="stLogoSpacer"] { display: none; }
[data-testid="stSidebarCollapseButton"] { margin-left: auto; }
[data-testid="stSidebarCollapseButton"] button { width: var(--tap); height: var(--tap); }
[data-testid="stSidebarUserContent"] {
    padding: 0 12px calc(16px + var(--safe-bottom)) calc(12px + var(--safe-left));
}
/* A coluna da sidebar tem altura fixa e rolagem: sem isto o flex encolhe os
   contêineres dos itens (36px) e os links de 48px se sobrepõem. */
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] { gap: 2px; }
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] > * { flex-shrink: 0; }
/* O Markdown do Streamlit tem margem inferior negativa — anula no menu. */
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"]:has(.nav-head, .nav-section, .nav-sandbox) { margin-bottom: 0; }

/* Mobile: gaveta sobreposta com backdrop escuro (o toque fora já fecha). */
@media (max-width: 767px) {
    /* Só quando aberta: recolhida, o Streamlit a desloca exatamente pela largura padrão. */
    [data-testid="stSidebar"][aria-expanded="true"] {
        width: min(86vw, 320px) !important; min-width: min(86vw, 320px) !important;
        box-shadow: 0 0 0 100vmax rgba(5,6,10,.62), 12px 0 40px rgba(0,0,0,.5);
        transition: box-shadow .25s ease, transform .3s cubic-bezier(.2,.8,.2,1);
    }
}

/* Cabeçalho do menu: identidade e saldo */
.nav-head {
    display: flex; align-items: center; gap: 12px;
    padding: 12px; margin-bottom: 10px;
    border-radius: var(--radius);
    background: linear-gradient(135deg, rgba(99,102,241,.22), rgba(34,211,238,.08));
    border: 1px solid var(--border);
}
.nav-avatar {
    flex: 0 0 44px; height: 44px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: .9rem; color: white;
    background: linear-gradient(135deg, var(--primary), var(--accent));
}
.nav-who { min-width: 0; }
.nav-name { font-weight: 700; font-size: .95rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nav-saldo-lbl { color: var(--muted); font-size: .68rem; text-transform: uppercase; letter-spacing: .05em; margin-top: 2px; }
.nav-saldo { font-weight: 800; font-size: 1.12rem; }
/* Seletor de período logo abaixo do cabeçalho */
[data-testid="stSidebar"] .stSelectbox { margin-bottom: 4px; }
[data-testid="stSidebar"] .stSelectbox [data-testid="stWidgetLabel"] p {
    color: var(--muted); font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .08em;
}
.nav-section {
    color: var(--muted); font-size: .68rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: .08em;
    padding: 16px 12px 6px;
    border-top: 1px solid var(--border);
    margin-top: 6px;
}
.nav-sandbox { font-size: .75rem; color: #FBBF24; padding: 8px 10px; margin-top: 8px; border-radius: 10px;
    background: rgba(245,158,11,.1); border: 1px solid rgba(245,158,11,.3); }

/* Itens de navegação (st.page_link) — 44px, ícone Material + rótulo */
[data-testid="stSidebar"] [data-testid="stPageLink"] { width: 100%; }
/* O Streamlit aplica margin -6px aos page links da sidebar (pensado para links
   de 32px); com 44px eles se sobreporiam. */
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(> [data-testid="stPageLink"]) { margin: 0 !important; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {
    min-height: 44px; width: 100%;
    display: flex; align-items: center; gap: 12px;
    padding: 0 12px; margin: 0;
    border-radius: 10px; border: 1px solid transparent;
    transition: background .12s ease, border-color .12s ease;
}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { background: rgba(99,102,241,.12); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p { font-size: .93rem; font-weight: 550; color: var(--text); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"] { font-size: 1.3rem; color: var(--muted); }

/* Botões do rodapé do menu (Recolher / Sair) com cara de item de menu */
[data-testid="stSidebar"] .stButton button {
    width: 100%; min-height: 44px; padding: 0 12px; gap: 12px;
    justify-content: flex-start;
    background: transparent; border: 1px solid transparent; font-weight: 550;
}
[data-testid="stSidebar"] .stButton button > div { justify-content: flex-start; gap: 12px; }
[data-testid="stSidebar"] .stButton button [data-testid="stIconMaterial"] { font-size: 1.3rem; color: var(--muted); }
[data-testid="stSidebar"] .stButton button:hover { background: rgba(99,102,241,.12); transform: none; box-shadow: none; filter: none; }
.st-key-nav_sair button p, .st-key-nav_sair button [data-testid="stIconMaterial"] { color: #FB7185 !important; }

/* ================= Desktop / tablet ================= */
@media (min-width: 768px) {
    .block-container {
        padding: 2.2rem clamp(1.5rem, 3.5vw, 4rem) 3rem;
    }
    [data-testid="stHeader"] { background: transparent; border-bottom: none; backdrop-filter: none; -webkit-backdrop-filter: none; }
    [data-testid="stHeader"]::after { display: none; }
    [data-testid="stVerticalBlock"] { gap: 1rem; }
    [data-testid="stHorizontalBlock"] { gap: 1.2rem; }
    .stApp [data-testid="stHeading"] h2, .stApp [data-testid="stMarkdownContainer"] h2 { font-size: 1.45rem; }
    .stApp [data-testid="stHeading"] h3, .stApp [data-testid="stMarkdownContainer"] h3 { font-size: 1.25rem; }
}

/* ================= Cabeçalho da tela ================= */
.app-hero {
    border-radius: 20px;
    margin-bottom: .2rem;
}
.app-hero h1 { display: none; }
.app-hero p { margin: 0; color: var(--muted); font-size: .88rem; line-height: 1.4; }
@media (min-width: 768px) {
    .app-hero {
        background: linear-gradient(135deg, rgba(99,102,241,0.20), rgba(34,211,238,0.10));
        border: 1px solid var(--border);
        padding: 1.4rem 1.6rem;
        box-shadow: 0 10px 40px -18px rgba(99,102,241,0.55);
    }
    .stApp .app-hero h1 { display: block; margin: 0; padding: 0; font-size: 1.8rem; line-height: 1.15; }
    .app-hero p { margin-top: .4rem; font-size: .96rem; }
    .app-hero .hero-icon { font-size: 1.9rem; margin-right: .4rem; }
}
.chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 999px; font-size: .8rem; font-weight: 650;
    color: var(--text); background: var(--surface-2); border: 1px solid var(--border);
}

/* ================= KPIs: grid 2x2 no celular ================= */
.kpi-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.kpi-card {
    background: linear-gradient(180deg, var(--surface), var(--surface-2));
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px 14px;
    min-width: 0;
}
.kpi-label { color: var(--muted); font-size: .7rem; font-weight: 650; text-transform: uppercase; letter-spacing: .04em; }
.kpi-value { font-size: 1.18rem; font-weight: 800; margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-sub { color: var(--muted); font-size: .72rem; margin-top: 2px; line-height: 1.3; }
.kpi-accent-bar { height: 3px; width: 32px; border-radius: 999px; margin-bottom: 8px; }
@media (min-width: 900px) {
    .kpi-grid { grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 1rem; }
    .kpi-card { padding: 1.1rem 1.2rem; transition: transform .15s ease, border-color .15s ease; }
    .kpi-card:hover { transform: translateY(-2px); border-color: var(--primary); }
    .kpi-value { font-size: 1.6rem; }
    .kpi-label { font-size: .8rem; }
    .kpi-sub { font-size: .8rem; }
}

/* ================= Carrossel horizontal (scroll-snap) ================= */
.carousel {
    display: flex; gap: 12px;
    overflow-x: auto; overscroll-behavior-x: contain;
    scroll-snap-type: x mandatory; scroll-padding: 0 var(--gutter);
    margin: 0 calc(-1 * var(--gutter)); padding: 4px var(--gutter) 10px;
    scrollbar-width: none; -webkit-overflow-scrolling: touch;
}
.carousel::-webkit-scrollbar { display: none; }
.carousel > * { flex: 0 0 84%; scroll-snap-align: start; }
@media (min-width: 768px) {
    .carousel { margin: 0; padding: 4px 0 10px; scrollbar-width: thin; }
    .carousel > * { flex: 0 0 340px; }
}

/* Cartão de crédito (estilo carteira digital) */
.cc {
    position: relative; overflow: hidden;
    aspect-ratio: 1.6 / 1; min-height: 190px;
    border-radius: 20px; padding: 16px 18px;
    display: flex; flex-direction: column; justify-content: space-between;
    color: white;
    background: linear-gradient(135deg, var(--cc), color-mix(in srgb, var(--cc) 45%, #0b0d14));
    border: 2px solid transparent;
    box-shadow: 0 14px 34px -18px var(--cc);
}
.cc::after {
    content: ""; position: absolute; right: -40px; top: -60px;
    width: 180px; height: 180px; border-radius: 50%;
    background: rgba(255,255,255,.08);
}
.cc.sel { border-color: rgba(255,255,255,.85); }
.cc-top { display: flex; justify-content: space-between; align-items: center; font-weight: 750; }
.cc-chip { width: 34px; height: 24px; border-radius: 6px; background: linear-gradient(135deg, #F5D27A, #B8892E); }
.cc-lbl { font-size: .68rem; text-transform: uppercase; letter-spacing: .06em; opacity: .8; }
.cc-big { font-size: 1.45rem; font-weight: 800; line-height: 1.15; }
.cc-bar { height: 6px; border-radius: 999px; background: rgba(255,255,255,.22); overflow: hidden; margin: 6px 0 2px; }
.cc-bar > div { height: 100%; background: white; border-radius: 999px; }
.cc-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; font-size: .78rem; }
.cc-row b { display: block; font-size: .88rem; }

/* ================= Listas em cards (transações, contas a vencer) ================= */
.list { display: flex; flex-direction: column; gap: 8px; }
.row-card {
    display: flex; align-items: center; gap: 12px;
    min-height: 60px; padding: 10px 12px;
    background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
}
.row-date {
    flex: 0 0 44px; height: 44px; border-radius: 12px;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: var(--surface-2); line-height: 1;
}
.row-date b { font-size: 1rem; }
.row-date span { font-size: .62rem; color: var(--muted); text-transform: uppercase; margin-top: 2px; }
.row-main { flex: 1; min-width: 0; }
.row-title { font-weight: 650; font-size: .93rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row-meta { color: var(--muted); font-size: .76rem; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row-end { text-align: right; flex: 0 0 auto; }
.row-val { font-weight: 800; font-size: .95rem; white-space: nowrap; }
.row-end .tag { margin-top: 4px; }

/* Card de transação (Transações / vínculos De/Para) */
.tx-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.tx-title { font-weight: 700; font-size: .98rem; line-height: 1.3; word-break: break-word; }
.tx-meta { color: var(--muted); font-size: .78rem; margin-top: 2px; }
.tx-val { font-weight: 800; font-size: 1.1rem; white-space: nowrap; text-align: right; }
.tx-foot { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: 10px; }
.tx-foot small { color: var(--muted); font-size: .76rem; }
.aloc-bar { height: 6px; border-radius: 999px; background: var(--border); overflow: hidden; margin-top: 10px; }
.aloc-bar > div { height: 100%; border-radius: 999px; }
.aloc-links { margin: 10px 0 0; padding: 8px 10px; border-radius: 10px; background: var(--surface-2); font-size: .8rem; }
.aloc-links div { display: flex; justify-content: space-between; gap: .6rem; padding: 2px 0; }
.aloc-links div span:first-child { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Orçamento: barra por categoria */
.bud-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.bud-cat { font-weight: 700; }
.bud-nums { color: var(--muted); font-size: .8rem; margin-top: 4px; display: flex; justify-content: space-between; }

/* Tags de status */
.tag { display: inline-block; white-space: nowrap; padding: 3px 9px; border-radius: 999px; font-size: .7rem; font-weight: 700; border: 1px solid transparent; }
.tag-ok { color: #4ADE80; background: rgba(34,197,94,.14); border-color: rgba(34,197,94,.35); }
.tag-parcial { color: #FBBF24; background: rgba(245,158,11,.14); border-color: rgba(245,158,11,.35); }
.tag-pendente { color: #FB7185; background: rgba(244,63,94,.12); border-color: rgba(244,63,94,.35); }
.tag-livre { color: #67E8F9; background: rgba(34,211,238,.12); border-color: rgba(34,211,238,.35); }
.tag-erro { color: #FFF; background: var(--despesa); }

/* ================= Containers com borda (cards nativos) ================= */
[data-testid="stVerticalBlockBorderWrapper"], .stVerticalBlock[class*="st-key-card_"] { border-radius: var(--radius); }

/* ================= Toque e formulários ================= */
.stButton button, .stFormSubmitButton button, .stDownloadButton button,
[data-testid="stPopover"] button, [data-testid="stBaseButton-segmented_control"],
[data-testid="stBaseButton-segmented_controlActive"], [data-testid="stBaseButton-pills"],
[data-testid="stBaseButton-pillsActive"] {
    min-height: var(--tap);
    border-radius: 12px;
    font-weight: 650;
}
.stButton button, .stFormSubmitButton button, .stDownloadButton button {
    border: 1px solid var(--border);
    transition: transform .12s ease, box-shadow .12s ease, filter .12s ease;
}
.stButton button:active, .stFormSubmitButton button:active { transform: scale(.98); }
.stFormSubmitButton button, .stButton button[kind="primary"] {
    background: linear-gradient(135deg, var(--primary), #4F7CF0);
    color: white; border: none;
}
/* Segmented control ocupa a largura toda no celular */
[data-testid="stButtonGroup"] { width: 100%; }
@media (max-width: 767px) {
    [data-testid="stButtonGroup"] > div { display: flex; width: 100%; }
    [data-testid="stButtonGroup"] [data-testid^="stBaseButton-segmented_control"] { flex: 1 1 0; }
}

/* Inputs: 16px evita o auto-zoom do iOS; 48px de altura para o toque */
input, textarea, select, [data-baseweb="select"] div, [data-baseweb="input"] input { font-size: 16px !important; }
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] { min-height: 48px; border-radius: 12px !important; }
[data-testid="stNumberInput"] button { min-width: 44px; }
[data-testid="stWidgetLabel"] p { font-size: .88rem; font-weight: 600; }
[data-testid="stForm"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 16px;
}
@media (min-width: 768px) { [data-testid="stForm"] { padding: 1.3rem 1.4rem; } }
/* Formulário dentro do bottom sheet não precisa de um segundo "cartão" */
[data-testid="stDialog"] [data-testid="stForm"] { background: none; border: none; padding: 0; }

/* Botão de envio fixo no rodapé da viewport (dentro do formulário) */
@media (max-width: 767px) {
    [data-testid="stForm"] [data-testid="stElementContainer"]:has(.stFormSubmitButton),
    .st-key-acao_rodape {
        position: sticky;
        bottom: 0;
        z-index: 20;
        width: auto !important;
        margin: 0 -16px -16px;
        padding: 12px 16px calc(12px + var(--safe-bottom));
        background: linear-gradient(180deg, rgba(23,26,35,0), var(--surface) 30%);
    }
    .st-key-acao_rodape { margin: 0; padding: 12px 0 calc(12px + var(--safe-bottom));
        background: linear-gradient(180deg, rgba(14,16,22,0), var(--bg) 30%); }
    .stFormSubmitButton button, .st-key-acao_rodape button { width: 100%; min-height: 52px; font-size: 1rem; }
}

/* ================= Diálogo → Bottom sheet no celular ================= */
@media (max-width: 767px) {
    [data-testid="stDialog"] { align-items: flex-end !important; padding: 0 !important; }
    [data-testid="stDialog"] > div { width: 100% !important; max-width: 100% !important; margin: 0 !important; }
    [data-testid="stDialog"] [role="dialog"] {
        width: 100% !important; max-width: 100% !important; margin: 0 !important;
        max-height: 88dvh; overflow-y: auto; overscroll-behavior: contain;
        border-radius: 22px 22px 0 0 !important;
        padding-bottom: calc(16px + var(--safe-bottom)) !important;
        animation: sheet-up .28s cubic-bezier(.2,.8,.2,1);
    }
    [data-testid="stDialog"] [role="dialog"]::before {
        /* "alça" da gaveta inferior */
        content: ""; position: absolute; top: 8px; left: 50%; margin-left: -22px;
        width: 44px; height: 5px; border-radius: 999px; background: var(--border);
    }
}
@keyframes sheet-up { from { transform: translateY(100%); } to { transform: translateY(0); } }

/* ================= Abas, tabelas e gráficos ================= */
[data-baseweb="tab-list"] { overflow-x: auto; scrollbar-width: none; gap: 4px; }
[data-baseweb="tab-list"]::-webkit-scrollbar { display: none; }
[data-baseweb="tab"] { min-height: var(--tap); padding: 0 14px; }
[data-testid="stDataFrame"], [data-testid="stTable"] { border-radius: 14px; overflow: hidden; border: 1px solid var(--border); }
[data-testid="stMetric"] {
    background: linear-gradient(180deg, var(--surface), var(--surface-2));
    border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 14px;
}
[data-testid="stExpander"] summary { min-height: var(--tap); }

/* Login centralizado */
.st-key-login_box { max-width: 420px; margin: 8vh auto 0; }

/* Container do JS do shell não ocupa espaço */
.st-key-shell_js { display: none; }
"""

# JS do shell: roda uma vez por aba (guarda em window). Faz:
# 1. viewport-fit=cover (habilita env(safe-area-inset-*));
# 2. inputmode="decimal" em todo campo numérico (teclado numérico nativo);
# 3. gesto de swipe: da borda esquerda → abre o menu; para a esquerda → fecha.
_JS = """
<script>
(function () {
  if (window.__finShell) return;
  window.__finShell = true;

  var meta = document.querySelector('meta[name="viewport"]');
  if (meta && meta.content.indexOf('viewport-fit') === -1) meta.content += ', viewport-fit=cover';

  var pendente = false;
  function ajustarInputs() {
    pendente = false;
    document.querySelectorAll('[data-testid="stNumberInput"] input').forEach(function (el) {
      if (el.getAttribute('inputmode') !== 'decimal') {
        el.setAttribute('inputmode', 'decimal');
        el.setAttribute('enterkeyhint', 'done');
      }
    });
  }
  new MutationObserver(function () {
    if (!pendente) { pendente = true; requestAnimationFrame(ajustarInputs); }
  }).observe(document.body, { childList: true, subtree: true });
  ajustarInputs();

  function fecharMenu() {
    var sb = document.querySelector('[data-testid="stSidebar"]');
    if (!sb || sb.getAttribute('aria-expanded') !== 'true') return;
    var fechar = document.querySelector('[data-testid="stSidebarCollapseButton"] button');
    if (fechar) fechar.click();
  }
  // No celular, escolher um item do menu fecha a gaveta (o st.page_link não faz isso sozinho).
  document.addEventListener('click', function (e) {
    if (window.innerWidth < 768 && e.target.closest('[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]')) {
      setTimeout(fecharMenu, 50);
    }
  }, true);

  var x0 = null, y0 = null;
  document.addEventListener('touchstart', function (e) {
    if (e.target.closest('.carousel, [data-testid="stDataFrame"], .js-plotly-plot, [data-baseweb="tab-list"]')) { x0 = null; return; }
    x0 = e.touches[0].clientX; y0 = e.touches[0].clientY;
  }, { passive: true });
  document.addEventListener('touchend', function (e) {
    if (x0 === null) return;
    var t = e.changedTouches[0], dx = t.clientX - x0, dy = t.clientY - y0, inicio = x0;
    x0 = null;
    if (Math.abs(dx) < 70 || Math.abs(dy) > 45) return;
    var sb = document.querySelector('[data-testid="stSidebar"]');
    var aberto = sb && sb.getAttribute('aria-expanded') === 'true';
    if (!aberto && dx > 0 && inicio < 40) {
      var abrir = document.querySelector('[data-testid="stExpandSidebarButton"]');
      if (abrir) abrir.click();
    } else if (aberto && dx < 0) {
      fecharMenu();
    }
  }, { passive: true });
})();
</script>
"""


def setup_app(title: str = "Gestão Financeira", icon: str = "💰"):
    """Configura a página e injeta o CSS/JS do shell. Chamado só pelo app.py."""
    st.set_page_config(page_title=title, page_icon=icon, layout="wide", initial_sidebar_state="auto")
    st.html(f"<style>{_TOKENS}{_CSS}</style>")
    with st.container(key="shell_js"):
        st.html(_JS, unsafe_allow_javascript=True)


def set_titulo_topo(titulo: str):
    """Título exibido na barra superior do celular (via variável CSS)."""
    seguro = titulo.replace("\\", "").replace('"', "")
    st.html(f'<style>:root {{ --page-title: "{seguro}"; }}</style>')


def page_header(title: str, subtitle: str = "", icon: str = ""):
    """Cabeçalho da tela. No desktop é um bloco "hero"; no celular o título vai
    para a barra superior e aqui sobra só a descrição curta."""
    icon_html = f'<span class="hero-icon">{icon}</span>' if icon else ""
    sub_html = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f'<div class="app-hero"><h1>{icon_html}{title}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def esc(texto) -> str:
    """Escapa texto do usuário para HTML."""
    return _html.escape(str(texto if texto is not None else ""))


def md(texto) -> str:
    """Escapa o "$" de "R$": o Markdown do Streamlit trata "$...$" como LaTeX."""
    return str(texto).replace("$", "\\$")


def _fmt_brl(valor: float) -> str:
    """Formata um número como moeda brasileira (R$ 1.234,56)."""
    s = f"{valor:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def chip(texto: str):
    st.markdown(f'<span class="chip">{texto}</span>', unsafe_allow_html=True)


def kpi_row(cards: list[dict]):
    """Grade de KPIs: 2x2 no celular, linha única no desktop.

    Cada dict aceita: label (str), value (str), sub (str, opcional),
    color (str hex, opcional — cor da barrinha de acento e do valor).
    """
    blocos = []
    for c in cards:
        cor = c.get("color", PALETTE["primary"])
        sub = f'<div class="kpi-sub">{c["sub"]}</div>' if c.get("sub") else ""
        blocos.append(
            f'<div class="kpi-card">'
            f'<div class="kpi-accent-bar" style="background:{cor}"></div>'
            f'<div class="kpi-label">{c["label"]}</div>'
            f'<div class="kpi-value" style="color:{cor}">{c["value"]}</div>'
            f'{sub}</div>'
        )
    st.markdown(f'<div class="kpi-grid">{"".join(blocos)}</div>', unsafe_allow_html=True)


def row_card(titulo: str, meta: str, valor: str, data=None, cor_valor: str | None = None, tag: str = "") -> str:
    """HTML de uma linha em card (data à esquerda, valor à direita). Use dentro de
    `<div class="list">…</div>`. `tag` é HTML pronto (ex: '<span class="tag tag-ok">…</span>')."""
    data_html = ""
    if data is not None:
        meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
        data_html = f'<div class="row-date"><b>{data.day:02d}</b><span>{meses[data.month - 1]}</span></div>'
    estilo = f' style="color:{cor_valor}"' if cor_valor else ""
    return (
        f'<div class="row-card">{data_html}'
        f'<div class="row-main"><div class="row-title">{esc(titulo)}</div><div class="row-meta">{esc(meta)}</div></div>'
        f'<div class="row-end"><div class="row-val"{estilo}>{valor}</div>{tag}</div></div>'
    )


def lista(linhas: list[str]):
    st.markdown(f'<div class="list">{"".join(linhas)}</div>', unsafe_allow_html=True)


def style_fig(fig, altura: int | None = None, legenda: bool = True):
    """Layout Plotly consistente com o tema: fundo transparente, margens enxutas
    (o celular tem pouco espaço) e legenda horizontal no topo."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=PALETTE["text"], family="sans-serif", size=12),
        margin=dict(t=30 if legenda else 10, r=8, b=8, l=8),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        showlegend=legenda,
        colorway=CHART_SEQUENCE,
        hoverlabel=dict(font_size=13),
    )
    if altura:
        fig.update_layout(height=altura)
    fig.update_xaxes(gridcolor=PALETTE["border"], zerolinecolor=PALETTE["border"], title=None)
    fig.update_yaxes(gridcolor=PALETTE["border"], zerolinecolor=PALETTE["border"], title=None)
    return fig
