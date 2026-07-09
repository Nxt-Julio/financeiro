"""Sistema de design compartilhado do app (tema, CSS e componentes reutilizáveis).

Todas as páginas devem chamar `setup_page(...)` no topo (que substitui a chamada
direta a `st.set_page_config`) e opcionalmente `page_header(...)` para um cabeçalho
consistente. Assim o visual fica coeso em todo o sistema.
"""
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
}

# Sequência de cores para gráficos categóricos (pizza, barras por categoria).
CHART_SEQUENCE = [
    "#6366F1", "#22D3EE", "#22C55E", "#F59E0B", "#F43F5E",
    "#A855F7", "#14B8A6", "#EAB308", "#EC4899", "#38BDF8",
]

_CSS = f"""
<style>
/* ---------- Base ---------- */
.stApp {{
    background:
        radial-gradient(1200px 600px at 15% -10%, rgba(99,102,241,0.14), transparent 60%),
        radial-gradient(1000px 500px at 100% 0%, rgba(34,211,238,0.08), transparent 55%),
        {PALETTE['bg']};
}}
/* Container principal: largura fluida (sem cap fixo), padding lateral que
   cresce em telas largas via clamp para não colar o conteúdo nas bordas. */
.block-container {{
    max-width: 100%;
    padding-top: 2.2rem;
    padding-bottom: 3rem;
    padding-left: clamp(1.2rem, 3.5vw, 4rem);
    padding-right: clamp(1.2rem, 3.5vw, 4rem);
}}

/* Mais respiro vertical entre os blocos e nos títulos de seção */
[data-testid="stVerticalBlock"] {{ gap: 1.1rem; }}
h2, h3 {{ margin-top: .4rem; }}
[data-testid="stHorizontalBlock"] {{ gap: 1.4rem; }}

/* Tipografia dos títulos */
h1, h2, h3 {{ letter-spacing: -0.02em; font-weight: 700; }}

/* ---------- Header / hero customizado ---------- */
.app-hero {{
    background: linear-gradient(135deg, rgba(99,102,241,0.20), rgba(34,211,238,0.10));
    border: 1px solid {PALETTE['border']};
    border-radius: 20px;
    padding: 1.6rem 1.8rem;
    margin-bottom: 1.6rem;
    box-shadow: 0 10px 40px -18px rgba(99,102,241,0.55);
}}
.app-hero h1 {{ margin: 0; font-size: 1.9rem; line-height: 1.15; }}
.app-hero p {{ margin: .4rem 0 0; color: {PALETTE['muted']}; font-size: .98rem; }}
.app-hero .hero-icon {{ font-size: 2rem; margin-right: .4rem; }}

/* ---------- Cards de KPI ---------- */
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 1rem; margin: .2rem 0 1.4rem; }}
.kpi-card {{
    background: linear-gradient(180deg, {PALETTE['surface']}, {PALETTE['surface_2']});
    border: 1px solid {PALETTE['border']};
    border-radius: 16px;
    padding: 1.1rem 1.2rem;
    transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
}}
.kpi-card:hover {{
    transform: translateY(-3px);
    border-color: {PALETTE['primary']};
    box-shadow: 0 14px 30px -18px rgba(99,102,241,0.8);
}}
.kpi-label {{ color: {PALETTE['muted']}; font-size: .82rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }}
.kpi-value {{ font-size: 1.7rem; font-weight: 800; margin-top: .35rem; }}
.kpi-sub {{ color: {PALETTE['muted']}; font-size: .8rem; margin-top: .25rem; }}
.kpi-accent-bar {{ height: 4px; width: 42px; border-radius: 999px; margin-bottom: .8rem; }}

/* ---------- Cards de navegação (home) ----------
   O card é um <a> com filhos apenas inline (<span>) estilizados como bloco.
   Isso evita que o parser de HTML quebre a âncora (o que ocorre quando um <a>
   envolve elementos de bloco), mantendo o card inteiro clicável. */
a.nav-card {{
    display: block;
    text-decoration: none !important;
    color: inherit !important;
    background: {PALETTE['surface']};
    border: 1px solid {PALETTE['border']};
    border-radius: 16px;
    padding: 1.1rem 1.2rem;
    height: 100%;
    transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
}}
a.nav-card:hover {{ transform: translateY(-3px); border-color: {PALETTE['primary_soft']}; box-shadow: 0 14px 30px -20px rgba(99,102,241,0.9); }}
.nav-card .nav-emoji {{ display: block; font-size: 1.6rem; }}
.nav-card .nav-title {{ display: block; margin: .5rem 0 .3rem; font-size: 1.05rem; font-weight: 700; color: {PALETTE['text']}; }}
.nav-card .nav-desc {{ display: block; margin: 0; color: {PALETTE['muted']}; font-size: .86rem; line-height: 1.4; }}

/* ---------- Métricas nativas do Streamlit ---------- */
[data-testid="stMetric"] {{
    background: linear-gradient(180deg, {PALETTE['surface']}, {PALETTE['surface_2']});
    border: 1px solid {PALETTE['border']};
    border-radius: 16px;
    padding: 1rem 1.1rem;
}}
[data-testid="stMetricValue"] {{ font-weight: 800; }}

/* ---------- Botões ---------- */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
    border-radius: 12px;
    font-weight: 650;
    border: 1px solid {PALETTE['border']};
    transition: transform .12s ease, box-shadow .12s ease, filter .12s ease;
}}
.stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 8px 20px -12px rgba(99,102,241,0.9);
    filter: brightness(1.06);
}}
.stFormSubmitButton > button {{
    background: linear-gradient(135deg, {PALETTE['primary']}, {PALETTE['accent']});
    color: white;
    border: none;
}}

/* ---------- Inputs e forms ---------- */
[data-testid="stForm"] {{
    background: {PALETTE['surface']};
    border: 1px solid {PALETTE['border']};
    border-radius: 18px;
    padding: 1.3rem 1.4rem;
}}
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input {{ border-radius: 10px; }}

/* ---------- Tabelas / dataframes ---------- */
[data-testid="stDataFrame"], [data-testid="stTable"] {{
    border-radius: 14px; overflow: hidden; border: 1px solid {PALETTE['border']};
}}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {PALETTE['surface']}, {PALETTE['bg']});
    border-right: 1px solid {PALETTE['border']};
}}
[data-testid="stSidebar"] > div {{ padding-top: .6rem; }}
[data-testid="stSidebarNav"] {{ padding-top: .2rem; }}
[data-testid="stSidebarNav"] ul {{ gap: 2px; }}
[data-testid="stSidebarNav"] li {{ margin: 0; }}
[data-testid="stSidebarNav"] a {{
    border-radius: 10px;
    padding: .5rem .7rem;
    margin: 1px .5rem;
    transition: background .12s ease, color .12s ease, transform .12s ease;
}}
[data-testid="stSidebarNav"] a:hover {{
    background: rgba(99,102,241,0.14);
    transform: translateX(2px);
}}
[data-testid="stSidebarNav"] a[aria-current="page"] {{
    background: linear-gradient(135deg, rgba(99,102,241,0.28), rgba(34,211,238,0.12));
    border: 1px solid rgba(99,102,241,0.35);
}}
[data-testid="stSidebarNav"] a[aria-current="page"] span {{ font-weight: 700; color: {PALETTE['text']}; }}
[data-testid="stSidebarNav"] a span {{ font-size: .93rem; }}

/* Divisor sutil */
hr {{ border-color: {PALETTE['border']}; }}

/* ---------- Responsivo / celular (Chrome Android) ---------- */
@media (max-width: 640px) {{
    .block-container {{ padding-top: 1.2rem; padding-left: 0.9rem; padding-right: 0.9rem; }}

    /* Colunas do Streamlit empilham em vez de espremer lado a lado */
    [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; gap: 0.6rem; }}
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
        min-width: 100% !important; flex: 1 1 100% !important;
    }}

    .app-hero {{ padding: 1.1rem 1.1rem; border-radius: 16px; }}
    .app-hero h1 {{ font-size: 1.35rem; }}
    .app-hero p {{ font-size: .88rem; }}

    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); gap: .7rem; }}
    .kpi-value {{ font-size: 1.35rem; }}
    .kpi-label {{ font-size: .72rem; }}

    h1 {{ font-size: 1.5rem; }}
    h2 {{ font-size: 1.25rem; }}
}}
</style>
"""


def setup_page(title: str, icon: str, layout: str = "wide"):
    """Configura a página e injeta o CSS do sistema de design. Substitui
    `st.set_page_config`."""
    st.set_page_config(page_title=title, page_icon=icon, layout=layout)
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", icon: str = ""):
    """Renderiza um cabeçalho (hero) consistente no topo da página."""
    icon_html = f'<span class="hero-icon">{icon}</span>' if icon else ""
    sub_html = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f'<div class="app-hero"><h1>{icon_html}{title}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def _fmt_brl(valor: float) -> str:
    """Formata um número como moeda brasileira (R$ 1.234,56)."""
    s = f"{valor:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def kpi_row(cards: list[dict]):
    """Renderiza uma linha de cards de KPI.

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


def style_fig(fig):
    """Aplica um layout Plotly consistente com o tema (fundo transparente,
    fonte e cores da paleta)."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=PALETTE["text"], family="sans-serif"),
        margin=dict(t=60, r=20, b=40, l=20),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        colorway=CHART_SEQUENCE,
    )
    fig.update_xaxes(gridcolor=PALETTE["border"], zerolinecolor=PALETTE["border"])
    fig.update_yaxes(gridcolor=PALETTE["border"], zerolinecolor=PALETTE["border"])
    return fig
