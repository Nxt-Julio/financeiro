"""Importação única de PDFs: o usuário só arrasta o arquivo; o sistema identifica
se é holerite ou fatura de cartão (utils/document_detector.py), lê os valores e
mostra tudo pronto para conferir e salvar. Quando não consegue identificar,
pergunta do que se trata o PDF.

Substitui as antigas páginas "Leitura de Holerite" e "Leitura de Extrato".
"""
import datetime
import html

import pandas as pd
import streamlit as st

from database import (
    atualizar_transacao,
    fetch_parcelas_pendentes,
    fetch_regras,
    fetch_cartoes,
    fetch_transacoes,
    get_responsaveis,
    inserir_transacao,
    inserir_transacoes_lote,
)
from utils.document_detector import TIPOS_DOCUMENTO, detectar_tipo, ler_como, sugerir_responsavel
from utils.statement_parser import aplicar_regra_categoria, extrair_texto_pdf
from utils.ui import PALETTE, _fmt_brl, kpi_row, page_header

page_header(
    "Importar PDF",
    "Arraste o holerite ou a fatura do cartão: o sistema identifica o tipo, lê os valores "
    "e você só confere e salva.",
    "📥",
)

arquivos = st.file_uploader(
    "Arraste os PDFs aqui (pode ser mais de um)",
    type=["pdf"],
    accept_multiple_files=True,
)

if not arquivos:
    st.caption("Tipos reconhecidos: 📄 holerite (contracheque) e 📑 fatura/extrato de cartão (Nubank).")
    st.stop()

responsaveis = get_responsaveis()

# Estado por arquivo (texto extraído, detecção, mensagem de salvo), para não
# reler o PDF a cada interação. Arquivos removidos do uploader são descartados.
cache = st.session_state.setdefault("importar_pdf", {})
ids_atuais = {a.file_id for a in arquivos}
for file_id in [k for k in cache if k not in ids_atuais]:
    del cache[file_id]


def _md(texto):
    """Escapa o "$" de "R$": o Markdown do Streamlit trata "$...$" como LaTeX."""
    return str(texto).replace("$", "\\$")


def _seletor_responsavel(texto, chave):
    sugerido = sugerir_responsavel(texto, responsaveis)
    indice = responsaveis.index(sugerido) if sugerido in responsaveis else 0
    return st.selectbox(
        "Responsável",
        responsaveis,
        index=indice,
        key=chave,
        help="Sugerido pelo nome que aparece no PDF." if sugerido else None,
    )


# ---------- Holerite ----------
def form_holerite(estado, dados, chave):
    kpi_row([
        {"label": "Salário bruto", "value": _fmt_brl(dados["salario_bruto"]), "color": PALETTE["accent"]},
        {"label": "Descontos", "value": _fmt_brl(dados["descontos"]), "color": PALETTE["despesa"]},
        {"label": "Salário líquido", "value": _fmt_brl(dados["salario_liquido"]), "color": PALETTE["receita"],
         "sub": dados["mes_referencia"]},
    ])

    data_iso = dados["data_referencia"].isoformat()
    ja_existe = any(
        t["tipo"] == "receita" and str(t["data"])[:10] == data_iso
        and round(float(t["valor"]), 2) == round(dados["salario_liquido"], 2)
        for t in fetch_transacoes()
    )
    if ja_existe:
        st.warning(f"Já existe uma receita de {_md(_fmt_brl(dados['salario_liquido']))} em "
                   f"{dados['data_referencia'].strftime('%d/%m/%Y')} — este holerite pode já ter sido importado.")

    # Parcelas em aberto que o holerite já desconta (ex: antecipação salarial),
    # para marcá-las como pagas junto e não contar a mesma saída duas vezes.
    opcoes_parcela = {"— Nenhuma —": None}
    for p in fetch_parcelas_pendentes():
        try:
            venc = datetime.date.fromisoformat(str(p["data_vencimento"])).strftime("%d/%m/%Y")
        except ValueError:
            venc = p["data_vencimento"]
        rotulo = (f"{p['descricao']} — parcela {p['parcela_atual']}/{p['total_parcelas']} "
                  f"— {_fmt_brl(p['valor_parcela'])} — venc. {venc}")
        opcoes_parcela[rotulo] = p["transacao_id"]

    with st.form(f"form_hol_{chave}"):
        responsavel = _seletor_responsavel(estado["texto"], f"resp_{chave}")
        empresa = st.text_input("Empresa (opcional)", key=f"emp_{chave}")
        rotulo_parcela = st.selectbox(
            "Este holerite já desconta alguma parcela em aberto? (opcional)",
            list(opcoes_parcela),
            key=f"parc_{chave}",
            help="Ex: desconto de antecipação salarial que corresponde a uma parcela cadastrada "
                 "em Parcelamentos — ela é marcada como paga junto.",
        )
        salvar = st.form_submit_button(
            f"Salvar salário líquido de {dados['mes_referencia']}", use_container_width=True
        )

    if salvar:
        inserir_transacao(
            data=data_iso,
            descricao_original=f"Salário líquido - {dados['mes_referencia']}",
            estabelecimento=empresa.strip() or None,
            categoria="Salário",
            valor=dados["salario_liquido"],
            tipo="receita",
            responsavel=responsavel,
            origem="Conta",
        )
        mensagem = (f"Salário líquido de {_fmt_brl(dados['salario_liquido'])} ({dados['mes_referencia']}) "
                    f"lançado para {responsavel}.")
        if opcoes_parcela[rotulo_parcela] is not None:
            atualizar_transacao(opcoes_parcela[rotulo_parcela], {"pago": True})
            mensagem += " A parcela selecionada foi marcada como paga."
        estado["salvo"] = mensagem
        st.rerun()


# ---------- Fatura ----------
def form_fatura(estado, transacoes, chave):
    regras = fetch_regras()
    # Lançamentos iguais (data + valor + descrição) já gravados vêm desmarcados,
    # para reimportar a mesma fatura sem duplicar.
    existentes = {
        (str(t["data"])[:10], round(float(t["valor"]), 2), (t["descricao_original"] or "").strip().lower())
        for t in fetch_transacoes() if t["tipo"] == "despesa"
    }
    linhas = []
    for t in transacoes:
        duplicado = (t["data"].isoformat(), round(t["valor"], 2), t["descricao_original"].strip().lower()) in existentes
        linhas.append({
            "Importar": not duplicado,
            "Data": t["data"],
            "Descrição": t["descricao_original"],
            "Categoria": aplicar_regra_categoria(t["descricao_original"], regras) or "",
            "Valor": t["valor"],
            "Situação": "Já importado" if duplicado else "Novo",
        })
    df = pd.DataFrame(linhas)

    n_dup = int((df["Situação"] == "Já importado").sum())
    st.markdown(_md(
        f"**{len(df)} lançamentos** · total {_fmt_brl(df['Valor'].sum())} · "
        f"{df['Data'].min().strftime('%d/%m/%Y')} a {df['Data'].max().strftime('%d/%m/%Y')}"
    ))
    if n_dup == len(df):
        st.info("Todos os lançamentos desta fatura já estão no sistema — nada novo para importar.")
    elif n_dup:
        st.info(f"{n_dup} lançamento(s) já estavam no sistema e vieram desmarcados.")
    if df["Descrição"].str.contains(r"Parcela \d+/\d+", case=False).any():
        st.caption("⚠️ Há compras parceladas. Se alguma já estiver cadastrada em **Parcelamentos**, "
                   "desmarque-a aqui para não contar duas vezes.")

    responsavel = _seletor_responsavel(estado["texto"], f"resp_{chave}")
    cartoes = fetch_cartoes()
    opcoes_cartao = {"— Nenhum —": None} | {c["nome"]: c["id"] for c in cartoes}
    nome_cartao = st.selectbox(
        "Cartão da fatura", list(opcoes_cartao), index=1 if cartoes else 0, key=f"cartao_{chave}",
        disabled=not cartoes, help="Os lançamentos entram na fatura deste cartão (Contas & Cartões).",
    )
    editado = st.data_editor(
        df,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "Importar": st.column_config.CheckboxColumn("Importar", width="small"),
            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", disabled=True),
            "Descrição": st.column_config.TextColumn("Descrição", disabled=True),
            "Categoria": st.column_config.TextColumn("Categoria", help="Sugerida pelas regras de categorização."),
            "Valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f", disabled=True),
            "Situação": st.column_config.TextColumn("Situação", disabled=True, width="small"),
        },
        key=f"editor_{chave}",
    )

    selecionados = editado[editado["Importar"]]
    if st.button(
        f"Salvar {len(selecionados)} lançamento(s) · {_fmt_brl(selecionados['Valor'].sum())}",
        type="primary",
        use_container_width=True,
        disabled=selecionados.empty,
        key=f"salvar_{chave}",
    ):
        inserir_transacoes_lote([
            {
                "data": linha["Data"].isoformat(),
                "descricao_original": linha["Descrição"],
                "estabelecimento": linha["Descrição"],
                "categoria": str(linha["Categoria"]).strip() or "Outros",
                "valor": float(linha["Valor"]),
                "tipo": "despesa",
                "responsavel": responsavel,
                "origem": "Cartão",
                "cartao_id": opcoes_cartao[nome_cartao],
            }
            for _, linha in selecionados.iterrows()
        ])
        estado["salvo"] = (f"{len(selecionados)} lançamento(s) da fatura salvos para {responsavel} "
                           f"({_fmt_brl(selecionados['Valor'].sum())}).")
        st.rerun()


# ---------- Um bloco por arquivo ----------
for arquivo in arquivos:
    chave = arquivo.file_id
    estado = cache.get(chave)
    if estado is None:
        try:
            texto = extrair_texto_pdf(arquivo)
        except Exception:  # noqa: BLE001 - PDF corrompido/protegido
            texto = ""
        estado = {"texto": texto, "deteccao": detectar_tipo(texto), "salvo": None}
        cache[chave] = estado

    with st.container(border=True):
        st.markdown(f"#### 📎 {html.escape(arquivo.name)}")

        if estado["salvo"]:
            st.success(_md(f"✅ {estado['salvo']}"))
            continue

        deteccao = estado["deteccao"]
        if not estado["texto"].strip():
            st.error(_md(deteccao["erro"]) + " Use o **Lançamento Manual** para registrar os valores.")
            continue

        opcoes = list(TIPOS_DOCUMENTO)
        if deteccao["tipo"]:
            st.caption("🔎 Tipo identificado automaticamente — troque abaixo se não for isso.")
        else:
            st.warning("🤔 Não consegui identificar do que se trata este PDF. **Escolha o tipo:**")
        tipo = st.radio(
            "Tipo do documento",
            opcoes,
            index=opcoes.index(deteccao["tipo"]) if deteccao["tipo"] else None,
            format_func=TIPOS_DOCUMENTO.get,
            horizontal=True,
            key=f"tipo_{chave}",
            label_visibility="collapsed",
        )
        if tipo is None:
            continue

        if tipo == deteccao["tipo"]:
            dados, erro = deteccao["dados"], deteccao["erro"]
        else:
            dados, erro = ler_como(tipo, estado["texto"])

        if not dados:
            st.error(_md(
                f"Não consegui ler este PDF como {TIPOS_DOCUMENTO[tipo].split(' ', 1)[1].lower()}: {erro}. "
                "O layout pode ser diferente do esperado — use o **Lançamento Manual** para registrar os valores."
            ))
            continue

        if tipo == "holerite":
            form_holerite(estado, dados, chave)
        else:
            form_fatura(estado, dados, chave)
