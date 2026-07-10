import datetime

import streamlit as st

from database import (
    ORIGENS,
    criar_parcelamento,
    get_responsaveis,
    init_db,
)
from utils.installments import gerar_parcelas
from utils.ui import page_header, setup_page
from utils.auth import require_login

setup_page("Parcelamentos", "🧾")
require_login()
init_db()

page_header(
    "Controle de Parcelados",
    "Registre uma compra parcelada e o sistema gera as parcelas futuras automaticamente.",
    "🧾",
)

with st.form("form_parcelamento", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        descricao = st.text_input("Descrição da compra", placeholder="Ex: Compra na loja X")
        valor_total = st.number_input("Valor total (R$)", min_value=0.01, step=0.01, format="%.2f")
        num_parcelas = st.number_input("Número de parcelas", min_value=1, max_value=48, step=1, value=1)
    with col2:
        data_primeira_parcela = st.date_input("Data da 1ª parcela", value=datetime.date.today())
        categoria = st.text_input("Categoria", placeholder="Ex: Eletrônicos")
        responsavel = st.selectbox("Responsável", get_responsaveis())
        origem = st.selectbox("Origem", ORIGENS, index=ORIGENS.index("Cartão"))

    submitted = st.form_submit_button("Gerar parcelas")

if submitted:
    if not descricao.strip():
        st.error("Informe a descrição da compra.")
    elif not categoria.strip():
        st.error("Informe a categoria.")
    else:
        parcelas = gerar_parcelas(valor_total, int(num_parcelas), data_primeira_parcela)

        criar_parcelamento(
            descricao=descricao,
            categoria=categoria,
            responsavel=responsavel,
            origem=origem,
            parcelas=parcelas,
        )

        st.success(f"{len(parcelas)} parcela(s) gerada(s) com sucesso!")
        st.dataframe(
            [
                {
                    "Parcela": f"{p['parcela_atual']}/{p['total_parcelas']}",
                    "Vencimento": p["data_vencimento"].isoformat(),
                    "Valor (R$)": p["valor_parcela"],
                }
                for p in parcelas
            ],
            use_container_width=True,
        )
