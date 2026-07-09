import pandas as pd
import streamlit as st

from database import fetch_regras, get_responsaveis, init_db, inserir_transacoes_lote
from utils.statement_parser import (
    aplicar_regra_categoria,
    extrair_ano_fatura,
    extrair_texto_pdf,
    parse_transacoes,
)
from utils.ui import page_header, setup_page

setup_page("Leitura de Extrato", "📑")
init_db()

page_header(
    "Leitura de Extrato/Fatura (PDF)",
    "Importe o extrato ou fatura em PDF; as categorias são sugeridas automaticamente para você revisar.",
    "📑",
)

if "extrato_transacoes" not in st.session_state:
    st.session_state.extrato_transacoes = None

responsavel = st.selectbox("Responsável (dono do cartão/fatura)", get_responsaveis())

arquivo = st.file_uploader("Selecione o PDF do extrato/fatura", type=["pdf"])

if arquivo is not None:
    try:
        texto = extrair_texto_pdf(arquivo)
        extrair_ano_fatura(texto)  # usado internamente pelo parser, se necessário
        transacoes = parse_transacoes(texto)

        regras = fetch_regras()
        for transacao in transacoes:
            categoria_sugerida = aplicar_regra_categoria(transacao["descricao_original"], regras)
            transacao["categoria"] = categoria_sugerida or ""

        st.session_state.extrato_transacoes = transacoes

        if not transacoes:
            st.warning("Nenhuma transação de despesa foi encontrada neste PDF.")
    except ValueError as erro:
        st.session_state.extrato_transacoes = None
        st.error(f"Não foi possível ler o extrato/fatura: {erro}")
    except Exception as erro:  # noqa: BLE001 - erro inesperado de parsing/PDF
        st.session_state.extrato_transacoes = None
        st.error(f"Ocorreu um erro ao processar o PDF: {erro}")

transacoes = st.session_state.extrato_transacoes

if transacoes:
    st.subheader(f"Transações extraídas ({len(transacoes)})")
    st.write(
        "As categorias sugeridas abaixo foram preenchidas automaticamente com base nas "
        "regras de categorização cadastradas. Ajuste o que for necessário antes de salvar."
    )

    df = pd.DataFrame(
        [
            {
                "Data": t["data"],
                "Descrição": t["descricao_original"],
                "Categoria": t["categoria"],
                "Valor": t["valor"],
            }
            for t in transacoes
        ]
    )

    df_editado = st.data_editor(
        df,
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "Data": st.column_config.DateColumn("Data", disabled=True),
            "Descrição": st.column_config.TextColumn("Descrição", disabled=True),
            "Categoria": st.column_config.TextColumn("Categoria"),
            "Valor": st.column_config.NumberColumn("Valor", format="%.2f", disabled=True),
        },
        key="extrato_data_editor",
    )

    if st.button("Salvar transações"):
        linhas = []
        for _, linha in df_editado.iterrows():
            categoria = str(linha["Categoria"]).strip() or "Outros"
            descricao = linha["Descrição"]
            data_valor = linha["Data"]
            data_iso = data_valor.isoformat() if hasattr(data_valor, "isoformat") else str(data_valor)

            linhas.append({
                "data": data_iso,
                "descricao_original": descricao,
                "estabelecimento": descricao,
                "categoria": categoria,
                "valor": float(linha["Valor"]),
                "tipo": "despesa",
                "responsavel": responsavel,
                "origem": "Cartão",
            })

        inserir_transacoes_lote(linhas)

        st.success(f"{len(linhas)} transação(ões) salva(s) com sucesso!")
        st.dataframe(df_editado, use_container_width=True)

        st.session_state.extrato_transacoes = None
