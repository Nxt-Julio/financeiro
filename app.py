"""Ponto de entrada e shell do app (Streamlit multipage via st.navigation).

Toda execução passa por aqui: configura tema/CSS/JS, exige login, garante o
schema, desenha o menu lateral (utils/nav.py) e então roda a tela escolhida
(scripts em views/). As telas não chamam set_page_config nem require_login.
"""
from database import fetch_transacoes, init_db
from utils.auth import require_login
from utils.nav import build_pages, item_atual, render_sidebar
from utils.ui import set_titulo_topo, setup_app

import streamlit as st

setup_app()
require_login()
init_db()

pages = build_pages()
pagina = st.navigation(list(pages.values()), position="hidden")
ativo = item_atual(pages, pagina)

set_titulo_topo(ativo.titulo)
render_sidebar(pages, ativo, fetch_transacoes())

pagina.run()
