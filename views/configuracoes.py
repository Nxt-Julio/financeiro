import streamlit as st

from database import atualizar_responsavel, get_responsaveis
from utils.ui import page_header

page_header(
    "Configurações",
    "Personalize os nomes dos responsáveis. Transações antigas são renomeadas automaticamente.",
    "⚙️",
)

nome1_atual, nome2_atual = get_responsaveis()

with st.form("form_responsaveis"):
    novo_nome1 = st.text_input("Nome do responsável 1", value=nome1_atual)
    novo_nome2 = st.text_input("Nome do responsável 2", value=nome2_atual)

    salvar = st.form_submit_button("Salvar nomes", use_container_width=True)

if salvar:
    novo_nome1 = novo_nome1.strip()
    novo_nome2 = novo_nome2.strip()

    if not novo_nome1 or not novo_nome2:
        st.error("Informe os dois nomes.")
    elif novo_nome1 == novo_nome2:
        st.error("Os dois nomes precisam ser diferentes.")
    else:
        atualizar_responsavel("nome_responsavel_1", novo_nome1)
        atualizar_responsavel("nome_responsavel_2", novo_nome2)
        st.success(f"Nomes atualizados para \"{novo_nome1}\" e \"{novo_nome2}\"!")
        st.rerun()
