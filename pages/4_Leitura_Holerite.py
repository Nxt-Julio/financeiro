import streamlit as st

from database import get_responsaveis, init_db, inserir_transacao
from utils.payslip_parser import extrair_texto_pdf, parse_holerite
from utils.ui import page_header, setup_page
from utils.auth import require_login

setup_page("Leitura de Holerite", "📄")
require_login()
init_db()

page_header(
    "Leitura de Holerite (PDF)",
    "Envie o PDF do holerite para extrair Salário Bruto, Descontos e Líquido, e lançar o líquido como receita.",
    "📄",
)

arquivo = st.file_uploader("Selecione o PDF do holerite", type=["pdf"])

if "holerite_dados" not in st.session_state:
    st.session_state.holerite_dados = None

if arquivo is not None:
    try:
        texto = extrair_texto_pdf(arquivo)
        dados = parse_holerite(texto)
        st.session_state.holerite_dados = dados
    except ValueError as erro:
        st.session_state.holerite_dados = None
        st.error(f"Não foi possível ler o holerite: {erro}")
    except Exception as erro:  # noqa: BLE001 - erro inesperado de parsing/PDF
        st.session_state.holerite_dados = None
        st.error(f"Ocorreu um erro ao processar o PDF: {erro}")

dados = st.session_state.holerite_dados

if dados:
    st.subheader(f"Dados extraídos — Referente a {dados['mes_referencia']}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Salário Bruto (R$)", f"{dados['salario_bruto']:.2f}")
    col2.metric("Descontos (R$)", f"{dados['descontos']:.2f}")
    col3.metric("Salário Líquido (R$)", f"{dados['salario_liquido']:.2f}")

    st.write("Confira os valores acima antes de salvar. Se algo estiver incorreto, "
             "verifique se o PDF enviado é um holerite compatível.")

    with st.form("form_holerite"):
        responsavel = st.selectbox("Responsável (dono do holerite)", get_responsaveis())
        estabelecimento = st.text_input(
            "Empresa / estabelecimento (opcional)",
            value="",
            placeholder="Ex: Nome da empresa",
        )
        st.text_input("Origem", value="Conta", disabled=True)
        st.text_input("Tipo", value="receita", disabled=True)

        confirmar = st.form_submit_button("Confirmar e salvar")

    if confirmar:
        inserir_transacao(
            data=dados["data_referencia"].isoformat(),
            descricao_original=f"Salário líquido - {dados['mes_referencia']}",
            estabelecimento=estabelecimento.strip() or None,
            categoria="Salário",
            valor=dados["salario_liquido"],
            tipo="receita",
            responsavel=responsavel,
            origem="Conta",
        )

        st.success(
            f"Salário líquido de R$ {dados['salario_liquido']:.2f} "
            f"referente a {dados['mes_referencia']} lançado para {responsavel} com sucesso!"
        )
        st.session_state.holerite_dados = None
