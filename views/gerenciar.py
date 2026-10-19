import datetime

import pandas as pd
import streamlit as st

from database import (
    ORIGENS,
    TIPOS,
    atualizar_transacao,
    excluir_transacao,
    fetch_cartoes,
    fetch_transacoes,
    get_responsaveis,
)
from utils.ui import _fmt_brl, page_header

page_header(
    "Editar lançamentos",
    "Edite categorias e outros campos direto na tabela, ou marque linhas para excluir. "
    "As correções refletem imediatamente nos dashboards.",
    "🗂️",
)

transacoes = fetch_transacoes()

if not transacoes:
    st.info("Nenhum lançamento cadastrado ainda.")
    st.stop()

df = pd.DataFrame(transacoes)
df["data"] = pd.to_datetime(df["data"]).dt.date

responsaveis = get_responsaveis()

df["pago"] = df["pago"].fillna(False).astype(bool)

# Cartão aparece pelo nome na tabela e é convertido de volta para id ao salvar.
cartoes = fetch_cartoes()
nome_por_id = {c["id"]: c["nome"] for c in cartoes}
id_por_nome = {c["nome"]: c["id"] for c in cartoes}
df["cartao"] = df["cartao_id"].map(nome_por_id)

# ---------- Filtros ----------
with st.expander("🔎 Filtros", expanded=False):
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)
    with col1:
        filtro_resp = st.multiselect("Responsável", responsaveis, default=[])
    with col2:
        filtro_tipo = st.multiselect("Tipo", TIPOS, default=[])
    with col3:
        filtro_status = st.selectbox("Status", ["Todos", "Pendentes", "Pagas"])
    with col4:
        busca = st.text_input("Buscar na descrição/categoria", "")

df_filtrado = df.copy()
if filtro_resp:
    df_filtrado = df_filtrado[df_filtrado["responsavel"].isin(filtro_resp)]
if filtro_tipo:
    df_filtrado = df_filtrado[df_filtrado["tipo"].isin(filtro_tipo)]
if filtro_status == "Pendentes":
    df_filtrado = df_filtrado[~df_filtrado["pago"]]
elif filtro_status == "Pagas":
    df_filtrado = df_filtrado[df_filtrado["pago"]]
if busca.strip():
    termo = busca.strip().lower()
    mask = (
        df_filtrado["descricao_original"].fillna("").str.lower().str.contains(termo)
        | df_filtrado["categoria"].fillna("").str.lower().str.contains(termo)
    )
    df_filtrado = df_filtrado[mask]

# Resumo pago/pendente das despesas do recorte atual
despesas = df_filtrado[df_filtrado["tipo"] == "despesa"]
total_pago = despesas.loc[despesas["pago"], "valor"].sum()
total_pendente = despesas.loc[~despesas["pago"], "valor"].sum()
c1, c2, c3 = st.columns(3)
c1.metric("Lançamentos exibidos", f"{len(df_filtrado)} de {len(df)}")
c2.metric("Despesas pagas", _fmt_brl(total_pago))
c3.metric("Despesas pendentes", _fmt_brl(total_pendente))

# ---------- Tabela editável ----------
# Snapshot pré-edição (indexado por id) para reconciliar as mudanças ao salvar.
original_por_id = df_filtrado.set_index("id").to_dict("index")

df_editor = df_filtrado.copy()
df_editor.insert(0, "Excluir", False)

# Opções de categoria: as já existentes + as presentes no recorte atual.
categorias_existentes = sorted(
    {c for c in df["categoria"].dropna().unique() if str(c).strip()}
)

edited = st.data_editor(
    df_editor,
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
    column_order=[
        "Excluir", "pago", "data", "descricao_original", "estabelecimento",
        "categoria", "valor", "tipo", "responsavel", "origem", "cartao",
    ],
    column_config={
        "id": None,
        "id_parcelamento": None,
        "cartao_id": None,
        "Excluir": st.column_config.CheckboxColumn("Excluir", width="small"),
        "pago": st.column_config.CheckboxColumn("Pago", width="small", help="Marque as parcelas/lançamentos já quitados."),
        "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "descricao_original": st.column_config.TextColumn("Descrição"),
        "estabelecimento": st.column_config.TextColumn("Estabelecimento"),
        "categoria": st.column_config.TextColumn(
            "Categoria",
            help="Digite ou padronize a categoria. Existentes: " + ", ".join(categorias_existentes[:20]),
        ),
        "valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f", min_value=0.0),
        "tipo": st.column_config.SelectboxColumn("Tipo", options=TIPOS),
        "responsavel": st.column_config.SelectboxColumn("Responsável", options=responsaveis),
        "origem": st.column_config.SelectboxColumn("Origem", options=ORIGENS),
        "cartao": st.column_config.SelectboxColumn("Cartão", options=list(id_por_nome)),
    },
    key="editor_lancamentos",
)

with st.container(key="acao_rodape"):
    salvar = st.button("💾 Salvar alterações", type="primary", use_container_width=True)

if salvar:
    campos = ["data", "descricao_original", "estabelecimento", "categoria", "valor", "tipo", "responsavel", "origem", "pago", "cartao"]
    n_editados = 0
    n_excluidos = 0

    for _, linha in edited.iterrows():
        id_transacao = int(linha["id"])

        if linha["Excluir"]:
            excluir_transacao(id_transacao)
            n_excluidos += 1
            continue

        original = original_por_id.get(id_transacao, {})
        alteracoes = {}
        for campo in campos:
            novo = linha[campo]
            antigo = original.get(campo)

            if campo == "data":
                novo = novo.isoformat() if hasattr(novo, "isoformat") else str(novo)
                antigo = antigo.isoformat() if hasattr(antigo, "isoformat") else str(antigo)
            elif campo == "valor":
                novo = round(float(novo), 2)
                antigo = round(float(antigo), 2)
            elif campo == "pago":
                novo = bool(novo)
                antigo = bool(antigo)
            elif campo == "cartao":
                novo = None if pd.isna(novo) else novo
                antigo = None if pd.isna(antigo) else antigo

            if novo != antigo:
                if campo == "cartao":
                    alteracoes["cartao_id"] = id_por_nome.get(novo)
                    if novo:
                        alteracoes["origem"] = "Cartão"
                else:
                    alteracoes[campo] = novo

        if alteracoes:
            atualizar_transacao(id_transacao, alteracoes)
            n_editados += 1

    if n_editados or n_excluidos:
        st.success(f"{n_editados} lançamento(s) atualizado(s) e {n_excluidos} excluído(s).")
        st.rerun()
    else:
        st.info("Nenhuma alteração para salvar.")
