"""Importação única de PDFs: o usuário só arrasta o arquivo; o sistema identifica
se é holerite, fatura do cartão ou extrato da conta (utils/document_detector.py),
lê os valores e mostra tudo pronto para conferir e salvar. Quando não consegue identificar,
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
from utils.document_detector import (
    SITUACOES,
    TIPOS_DOCUMENTO,
    classificar_lancamentos,
    detectar_tipo,
    ler_como,
    sugerir_responsavel,
)
from utils.statement_parser import aplicar_regra_categoria, extrair_texto_pdf
from utils.ui import PALETTE, _fmt_brl, kpi_row, page_header

page_header(
    "Importar PDF",
    "Arraste o holerite, a fatura do cartão ou o extrato da conta: o sistema identifica "
    "o tipo, lê os valores e você só confere e salva.",
    "📥",
)

arquivos = st.file_uploader(
    "Arraste os PDFs aqui (pode ser mais de um)",
    type=["pdf"],
    accept_multiple_files=True,
)

if not arquivos:
    st.caption("Tipos reconhecidos: 📄 holerite (contracheque), 💳 fatura do cartão e 🏦 extrato da conta (Nubank).")
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


# ---------- Fatura do cartão / extrato da conta ----------
MOTIVOS = {
    "importado": "já importado — está no sistema",
    "fatura": "pagamento de fatura — as compras já entram pela fatura do cartão",
    "interno": "entre vocês / contas próprias — não é ganho nem gasto",
    "duplicado": "possível duplicado — mesmo valor de um lançamento já cadastrado a até 7 dias (ex: parcela)",
}


def form_lancamentos(estado, dados, chave, documento):
    """Tabela de conferência para a fatura (só saídas, vão para um cartão) e
    para o extrato da conta (entradas e saídas, origem "Conta")."""
    eh_extrato = documento == "extrato_conta"
    transacoes = dados["transacoes"] if eh_extrato else dados
    titular = dados["titular"] if eh_extrato else estado["texto"]

    regras = fetch_regras()
    situacoes = classificar_lancamentos(
        transacoes,
        fetch_transacoes(),
        # Fatura: só compras, nenhuma é "entre vocês"; extrato: Pix do casal/contas próprias.
        set(responsaveis) | {dados["titular"]} if eh_extrato else set(),
        janela_dias=7 if eh_extrato else None,
    )
    df = pd.DataFrame([
        {
            "Importar": situacao == "novo",
            "Data": t["data"],
            "Tipo": t.get("tipo", "despesa"),
            "Descrição": t["descricao_original"],
            "Categoria": aplicar_regra_categoria(t["descricao_original"], regras) or "",
            "Valor": t["valor"],
            "Situação": SITUACOES[situacao],
            "_estab": t.get("estabelecimento") or t["descricao_original"],
        }
        for t, situacao in zip(transacoes, situacoes)
    ])

    entradas = df.loc[df["Tipo"] == "receita", "Valor"].sum()
    saidas = df.loc[df["Tipo"] == "despesa", "Valor"].sum()
    periodo = f"{df['Data'].min().strftime('%d/%m/%Y')} a {df['Data'].max().strftime('%d/%m/%Y')}"
    if eh_extrato:
        confere = (dados["total_entradas"] is not None and dados["total_saidas"] is not None
                   and abs(entradas - dados["total_entradas"]) < 0.01 and abs(saidas - dados["total_saidas"]) < 0.01)
        st.markdown(_md(
            f"**{len(df)} movimentações** · {periodo} · entradas **{_fmt_brl(entradas)}** · "
            f"saídas **{_fmt_brl(saidas)}**" + (" · ✔ confere com o resumo do extrato" if confere else "")
        ))
        if not confere:
            st.warning("Os totais lidos não batem com o resumo do extrato — confira se faltou alguma linha.")
    else:
        st.markdown(_md(f"**{len(df)} lançamentos** · total {_fmt_brl(saidas)} · {periodo}"))

    contagem = {c: situacoes.count(c) for c in MOTIVOS if situacoes.count(c)}
    if contagem and len(contagem) == 1 and contagem.get("importado") == len(df):
        st.info("Todos os lançamentos deste arquivo já estão no sistema — nada novo para importar.")
    elif contagem:
        st.info("Vieram **desmarcados** (marque se quiser importar mesmo assim):\n" + "\n".join(
            f"- **{n}** × {MOTIVOS[c]}" for c, n in contagem.items()
        ))
    if not eh_extrato and df["Descrição"].str.contains(r"Parcela \d+/\d+", case=False).any():
        st.caption("⚠️ Há compras parceladas. Se alguma já estiver cadastrada em **Parcelamentos**, "
                   "desmarque-a aqui para não contar duas vezes.")

    responsavel = _seletor_responsavel(titular, f"resp_{chave}")
    id_cartao = None
    if not eh_extrato:
        cartoes = fetch_cartoes()
        opcoes_cartao = {"— Nenhum —": None} | {c["nome"]: c["id"] for c in cartoes}
        nome_cartao = st.selectbox(
            "Cartão da fatura", list(opcoes_cartao), index=1 if cartoes else 0, key=f"cartao_{chave}",
            disabled=not cartoes, help="Os lançamentos entram na fatura deste cartão (Contas & Cartões).",
        )
        id_cartao = opcoes_cartao[nome_cartao]

    editado = st.data_editor(
        df,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_order=["Importar", "Data", "Tipo", "Descrição", "Categoria", "Valor", "Situação"]
        if eh_extrato else ["Importar", "Data", "Descrição", "Categoria", "Valor", "Situação"],
        column_config={
            "Importar": st.column_config.CheckboxColumn("Importar", width="small"),
            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", disabled=True),
            "Tipo": st.column_config.SelectboxColumn(
                "Tipo", options=["receita", "despesa"], width="small",
                help="receita = entrou na conta · despesa = saiu da conta"),
            "Descrição": st.column_config.TextColumn("Descrição", disabled=True),
            "Categoria": st.column_config.TextColumn("Categoria", help="Sugerida pelas regras de categorização."),
            "Valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f", disabled=True),
            "Situação": st.column_config.TextColumn("Situação", disabled=True, width="small"),
        },
        key=f"editor_{chave}",
    )

    selecionados = editado[editado["Importar"]]
    sel_ent = selecionados.loc[selecionados["Tipo"] == "receita", "Valor"].sum()
    sel_sai = selecionados.loc[selecionados["Tipo"] == "despesa", "Valor"].sum()
    resumo = (f"+{_fmt_brl(sel_ent)} / −{_fmt_brl(sel_sai)}" if eh_extrato else _fmt_brl(sel_sai))
    if st.button(
        _md(f"Salvar {len(selecionados)} lançamento(s) · {resumo}"),
        type="primary",
        use_container_width=True,
        disabled=selecionados.empty,
        key=f"salvar_{chave}",
    ):
        inserir_transacoes_lote([
            {
                "data": linha["Data"].isoformat(),
                "descricao_original": linha["Descrição"],
                "estabelecimento": linha["_estab"],
                "categoria": str(linha["Categoria"]).strip() or "Outros",
                "valor": float(linha["Valor"]),
                "tipo": linha["Tipo"],
                "responsavel": responsavel,
                "origem": "Conta" if eh_extrato else "Cartão",
                "cartao_id": id_cartao,
            }
            for _, linha in selecionados.iterrows()
        ])
        estado["salvo"] = (f"{len(selecionados)} lançamento(s) {'do extrato' if eh_extrato else 'da fatura'} "
                           f"salvos para {responsavel} ({resumo}).")
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
            form_lancamentos(estado, dados, chave, tipo)
