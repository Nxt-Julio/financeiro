import datetime

import streamlit as st

from database import (
    ORIGENS,
    TIPOS,
    get_responsaveis,
    init_db,
    inserir_transacao,
)

from utils.ui import page_header, setup_page

setup_page("Lançamento Manual", "✍️")
init_db()

page_header(
    "Lançamento Manual",
    "Registre uma receita ou despesa avulsa (ex: dinheiro em espécie) que não passa pelo extrato ou holerite.",
    "✍️",
)

with st.form("form_lancamento_manual", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        data = st.date_input("Data", value=datetime.date.today())
        descricao = st.text_input("Descrição", placeholder="Ex: Feira da semana")
        estabelecimento = st.text_input("Estabelecimento (opcional)", placeholder="Ex: Feira Livre")
        categoria = st.text_input("Categoria", placeholder="Ex: Alimentação")
    with col2:
        valor = st.number_input("Valor (R$)", min_value=0.01, step=0.01, format="%.2f")
        tipo = st.selectbox("Tipo", TIPOS)
        responsavel = st.selectbox("Responsável", get_responsaveis())
        origem = st.selectbox("Origem", ORIGENS)

    submitted = st.form_submit_button("Registrar lançamento")

if submitted:
    if not descricao.strip():
        st.error("Informe a descrição do lançamento.")
    elif not categoria.strip():
        st.error("Informe a categoria.")
    else:
        inserir_transacao(
            data=data.isoformat(),
            descricao_original=descricao,
            estabelecimento=estabelecimento,
            categoria=categoria,
            valor=valor,
            tipo=tipo,
            responsavel=responsavel,
            origem=origem,
            id_parcelamento=None,
        )

        st.success("Lançamento registrado com sucesso!")
        st.dataframe(
            [
                {
                    "Data": data.isoformat(),
                    "Descrição": descricao,
                    "Estabelecimento": estabelecimento,
                    "Categoria": categoria,
                    "Valor (R$)": valor,
                    "Tipo": tipo,
                    "Responsável": responsavel,
                    "Origem": origem,
                }
            ],
            use_container_width=True,
        )
