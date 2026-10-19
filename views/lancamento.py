"""Novo lançamento: cadastro rápido de receita/despesa avulsa ou de compra
parcelada (gera as parcelas futuras automaticamente). Substitui as antigas
telas "Lançamento Manual" e "Parcelamentos".

No celular: campos empilhados, valores com teclado numérico (inputmode via JS
do shell) e botão de salvar fixo no rodapé (CSS em utils/ui.py)."""
import datetime

import streamlit as st
from dateutil.relativedelta import relativedelta

from database import (
    ORIGENS,
    criar_parcelamento,
    fetch_cartoes,
    fetch_categorias,
    get_responsaveis,
    inserir_transacoes_lote,
)
from utils.installments import gerar_parcelas
from utils.ui import _fmt_brl, lista, md, page_header, row_card

page_header(
    "Novo lançamento",
    "Registre uma receita ou despesa avulsa, ou uma compra parcelada.",
    "➕",
)

flash = st.session_state.pop("lanc_flash", None)
if flash:
    st.success(md(flash))

MODOS = {"avulso": "Avulso", "parcelado": "Parcelado"}
modo = st.segmented_control("Tipo de lançamento", list(MODOS), format_func=MODOS.get, default="avulso",
                            required=True, key="lanc_modo", label_visibility="collapsed", width="stretch")

responsaveis = get_responsaveis()
cartoes = fetch_cartoes()
SEM_CARTAO = "— Nenhum —"
opcoes_cartao = {SEM_CARTAO: None} | {c["nome"]: c["id"] for c in cartoes}
categorias = fetch_categorias()


def _origem_e_cartao(origem, nome_cartao):
    """Escolher um cartão implica origem "Cartão"."""
    cartao_id = opcoes_cartao[nome_cartao]
    return ("Cartão" if cartao_id else origem), cartao_id


if modo == "avulso":
    # O tipo fica FORA do formulário de propósito: com clear_on_submit ele
    # voltaria para "Saída" a cada envio, e lançamentos seguidos de entrada
    # (ex: salário de vários meses) acabavam gravados como despesa.
    tipo = st.segmented_control("Tipo", ["despesa", "receita"], default="despesa", required=True,
                                format_func=lambda t: "💸 Saída" if t == "despesa" else "💚 Entrada",
                                key="lanc_tipo", width="stretch")
    eh_receita = tipo == "receita"
    nome_tipo = "entrada" if eh_receita else "saída"
    with st.form("form_lancamento", clear_on_submit=True):
        valor = st.number_input("Valor (R$)", min_value=0.0, step=1.0, format="%.2f", value=None,
                                placeholder="0,00")
        descricao = st.text_input("Descrição", placeholder="Ex: Salário" if eh_receita else "Ex: Feira da semana")
        categoria = st.selectbox("Categoria", categorias, index=None, accept_new_options=True,
                                 placeholder="Escolha ou digite uma nova")
        data = st.date_input("Data", value=datetime.date.today(), format="DD/MM/YYYY")
        repetir = st.number_input("Repetir por quantos meses", min_value=1, max_value=36, step=1, value=1,
                                  help="Cria o mesmo lançamento todo mês a partir da data — ex: salário, aluguel.")
        responsavel = st.selectbox("Responsável", responsaveis)
        origem = st.selectbox("Origem", ORIGENS, index=ORIGENS.index("Conta") if eh_receita else 0)
        nome_cartao = st.selectbox("Cartão (opcional)", list(opcoes_cartao), disabled=not cartoes or eh_receita,
                                   help="Escolher um cartão coloca o lançamento na fatura dele.")
        estabelecimento = st.text_input("Estabelecimento (opcional)", placeholder="Ex: Feira Livre")
        enviar = st.form_submit_button(f"Salvar {nome_tipo}", use_container_width=True)

    if enviar:
        if not valor:
            st.error("Informe o valor.")
        elif not descricao.strip():
            st.error("Informe a descrição.")
        elif not (categoria or "").strip():
            st.error("Informe a categoria.")
        else:
            origem, cartao_id = _origem_e_cartao(origem, nome_cartao)
            if eh_receita:
                cartao_id = None  # entrada nunca entra em fatura de cartão
            meses = int(repetir)
            inserir_transacoes_lote([
                {
                    "data": (data + relativedelta(months=i)).isoformat(),
                    "descricao_original": descricao.strip(),
                    "estabelecimento": estabelecimento.strip() or None,
                    "categoria": categoria.strip(),
                    "valor": float(valor),
                    "tipo": tipo,
                    "responsavel": responsavel,
                    "origem": origem,
                    "cartao_id": cartao_id,
                }
                for i in range(meses)
            ])
            repeticao = f" por {meses} meses" if meses > 1 else ""
            st.session_state["lanc_flash"] = (f"{nome_tipo.capitalize()} de {_fmt_brl(valor)}{repeticao} "
                                              f"registrada: {descricao.strip()}.")
            st.rerun()

else:
    with st.form("form_parcelamento", clear_on_submit=True):
        valor_total = st.number_input("Valor total (R$)", min_value=0.0, step=1.0, format="%.2f", value=None,
                                      placeholder="0,00")
        num_parcelas = st.number_input("Número de parcelas", min_value=1, max_value=48, step=1, value=2)
        descricao = st.text_input("Descrição da compra", placeholder="Ex: Geladeira")
        categoria = st.selectbox("Categoria", categorias, index=None, accept_new_options=True,
                                 placeholder="Escolha ou digite uma nova")
        data_primeira = st.date_input("Data da 1ª parcela", value=datetime.date.today(), format="DD/MM/YYYY")
        responsavel = st.selectbox("Responsável", responsaveis)
        origem = st.selectbox("Origem", ORIGENS, index=ORIGENS.index("Cartão"))
        nome_cartao = st.selectbox("Cartão (opcional)", list(opcoes_cartao), disabled=not cartoes)
        enviar = st.form_submit_button("Gerar parcelas", use_container_width=True)

    if enviar:
        if not valor_total:
            st.error("Informe o valor total.")
        elif not descricao.strip():
            st.error("Informe a descrição da compra.")
        elif not (categoria or "").strip():
            st.error("Informe a categoria.")
        else:
            origem, cartao_id = _origem_e_cartao(origem, nome_cartao)
            parcelas = gerar_parcelas(float(valor_total), int(num_parcelas), data_primeira)
            criar_parcelamento(
                descricao=descricao.strip(),
                categoria=categoria.strip(),
                responsavel=responsavel,
                origem=origem,
                parcelas=parcelas,
                cartao_id=cartao_id,
            )
            st.success(md(f"{len(parcelas)} parcela(s) gerada(s) — {_fmt_brl(valor_total)} em {descricao.strip()}."))
            lista([
                row_card(f"Parcela {p['parcela_atual']}/{p['total_parcelas']}", descricao.strip(),
                         _fmt_brl(p["valor_parcela"]), data=p["data_vencimento"])
                for p in parcelas
            ])
