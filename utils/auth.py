"""Portão de login por senha para proteger o app na web.

A senha fica em `st.secrets["auth"]["password"]` (arquivo `.streamlit/secrets.toml`
localmente e nos *Secrets* do Streamlit Cloud) ou na variável de ambiente
`AUTH_PASSWORD` (deploys self-hosted, ex: Coolify, sem suporte a secrets.toml) —
nunca no código nem no GitHub.

Uso: o `app.py` (roteador) chama `require_login()` antes de montar a navegação.
Enquanto a sessão não estiver autenticada, mostra o formulário de senha e
interrompe a renderização (`st.stop()`), de modo que nenhum dado é exibido nem
consultado. O botão "Sair" e o aviso de sandbox ficam no rodapé da sidebar
(utils/nav.py).

Comportamento **fail-closed**: se a senha não estiver configurada, o acesso é
bloqueado (em vez de liberar tudo).

**Exceção deliberada e restrita**: quando a variável de ambiente `FORCE_LOCAL_DB`
está ativa (modo sandbox local, ver `database.py`), o login é pulado — só para
facilitar testes no banco de dados clonado/local. Isso nunca afeta a produção:
o Streamlit Cloud jamais define `FORCE_LOCAL_DB`, então esse desvio só existe
quando alguém já rodou `iniciar_testes.bat` de propósito na própria máquina.
"""
import hmac
import os

import streamlit as st


def modo_sandbox():
    return os.getenv("FORCE_LOCAL_DB", "").lower() in ("1", "true", "yes")


def _senha_configurada():
    try:
        valor = st.secrets["auth"]["password"]
        if valor:
            return str(valor)
    except Exception:
        pass
    return os.getenv("AUTH_PASSWORD") or None


def require_login():
    """Bloqueia a página até a sessão estar autenticada."""
    if modo_sandbox():
        st.session_state["auth_ok"] = True
        return

    if st.session_state.get("auth_ok"):
        return

    senha_real = _senha_configurada()
    if not senha_real:
        st.error(
            "🔒 Login ainda não configurado. Defina `[auth] password` em "
            "`.streamlit/secrets.toml` (local) e nos *Secrets* do Streamlit Cloud."
        )
        st.stop()

    with st.container(key="login_box"):
        st.markdown("## 🔒 Acesso restrito")
        st.caption("Informe a senha para acessar suas informações financeiras.")
        with st.form("login_form"):
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", use_container_width=True)

        if entrar:
            if hmac.compare_digest(senha.encode("utf-8"), senha_real.encode("utf-8")):
                st.session_state["auth_ok"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")

    st.stop()


def sair():
    st.session_state["auth_ok"] = False
