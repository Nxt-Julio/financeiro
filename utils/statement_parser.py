"""Parsing puro de extrato/fatura de cartão de crédito em PDF, sem dependência
de Streamlit, mais motor de aplicação das regras de categorização.

Calibrado a partir de uma fatura Nubank real, extraída com pdfplumber como
texto corrido (sem tabela estruturada). As duas funções utilitárias
(`extrair_texto_pdf` e `valor_br_para_float`) seguem o mesmo padrão usado em
`utils/payslip_parser.py`, mas são duplicadas aqui de propósito para manter os
módulos de cada fase independentes (sem acoplamento entre parsers).
"""
import re
from datetime import date

import pdfplumber

MESES_PT = {
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}

# Início de uma linha de transação: "DD MMM " (ex: "07 MAI ")
_RE_INICIO_TRANSACAO = re.compile(r"^(\d{2})\s+([A-ZÇ]{3})\s+", re.MULTILINE)

# Valor monetário no corpo do texto: opcionalmente precedido de "−" (minus
# sign unicode) e "R$", seguido do número em formato BR.
_RE_VALOR = re.compile(r"(−)?R\$\s*([\d.]+,\d{2})")

# Lançamentos que não são gasto novo: "Saldo em rotativo" é o saldo da fatura
# anterior rolado para esta — as compras dele já entraram na importação anterior.
_RE_IGNORAR = re.compile(r"^saldo em rotativo", re.IGNORECASE)


def valor_br_para_float(texto: str) -> float:
    """Converte um número no formato brasileiro (ex: "1.234,56") para float (1234.56).

    Remove pontos de milhar e troca a vírgula decimal por ponto.
    """
    limpo = texto.strip().replace(".", "").replace(",", ".")
    return float(limpo)


def extrair_texto_pdf(arquivo) -> str:
    """Extrai o texto de todas as páginas de um PDF de extrato/fatura.

    Aceita tanto um caminho (str/Path) quanto um objeto file-like (ex: o
    BytesIO retornado por st.file_uploader).
    """
    partes = []
    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            texto_pagina = page.extract_text()
            if texto_pagina:
                partes.append(texto_pagina)
    return "\n".join(partes)


def extrair_ano_fatura(texto: str) -> int:
    """Localiza o ano da fatura a partir do cabeçalho do documento.

    Procura padrões como "FATURA 15 JUN 2026" ou "Data de vencimento: 15 JUN
    2026". Levanta ValueError amigável se não encontrar.
    """
    match = re.search(
        r"FATURA\s+\d{2}\s+[A-ZÇ]{3}\s+(\d{4})",
        texto,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"Data\s+de\s+vencimento:?\s*\d{2}\s+[A-ZÇ]{3}\s+(\d{4})",
            texto,
            re.IGNORECASE,
        )
    if not match:
        raise ValueError("Não foi possível localizar o ano da fatura no PDF")

    return int(match.group(1))


def _localizar_secao_transacoes(texto: str) -> str:
    """Recorta o texto a partir do primeiro cabeçalho "TRANSAÇÕES" encontrado.

    Se o cabeçalho não existir, retorna o texto completo (o filtro por linhas
    que começam com "DD MMM" já elimina a maior parte do ruído de cabeçalho).
    """
    # Cabeçalho real da lista na Nubank: "TRANSAÇÕES DE 07 SET A 07 OUT". A
    # palavra solta "transações" aparece antes, nos textos explicativos.
    match = re.search(r"TRANSA[ÇC][ÕO]ES\s+DE\s+\d{2}", texto)
    if not match:
        match = re.search(r"TRANSA[ÇC][ÕO]ES", texto, re.IGNORECASE)
    if match:
        return texto[match.end():]
    return texto


def parse_transacoes(texto: str) -> list[dict]:
    """Extrai as transações de despesa de uma fatura de cartão.

    Retorna uma lista de dicts com as chaves:
        data (date), descricao_original (str), valor (float, sempre positivo)

    Transações negativas (pagamentos/créditos, prefixadas com o unicode
    minus "−R$") são pagamentos e ficam de fora do resultado.

    Levanta ValueError com mensagem amigável se nenhuma transação for
    encontrada.
    """
    if not texto or not texto.strip():
        raise ValueError("Não foi possível extrair texto do PDF enviado")

    ano = extrair_ano_fatura(texto)
    m_fatura = re.search(r"FATURA\s+\d{2}\s+([A-ZÇ]{3})\s+\d{4}", texto, re.IGNORECASE)
    mes_fatura = MESES_PT.get(m_fatura.group(1).lower()) if m_fatura else None
    secao = _localizar_secao_transacoes(texto)

    inicios = list(_RE_INICIO_TRANSACAO.finditer(secao))
    if not inicios:
        raise ValueError("Não foi possível localizar transações no PDF")

    transacoes = []
    for i, m in enumerate(inicios):
        inicio_bloco = m.start()
        fim_bloco = inicios[i + 1].start() if i + 1 < len(inicios) else len(secao)
        bloco = secao[inicio_bloco:fim_bloco]

        dia = int(m.group(1))
        mes_abrev = m.group(2).lower()
        mes_num = MESES_PT.get(mes_abrev)
        if not mes_num:
            # mês não reconhecido - ignora este bloco (provavelmente falso positivo)
            continue

        # Descrição: texto entre o fim do cabeçalho "DD MMM " e a primeira
        # quebra de linha do bloco (ou até o primeiro "R$"/"−R$", o que vier
        # primeiro).
        resto_primeira_linha = bloco[m.end() - inicio_bloco:]
        quebra = resto_primeira_linha.find("\n")
        linha_transacao = resto_primeira_linha if quebra == -1 else resto_primeira_linha[:quebra]
        # remove um eventual valor já presente na primeira linha
        descricao = re.sub(r"\s+", " ", re.split(r"−?R\$", linha_transacao)[0]).strip()

        if _RE_IGNORAR.search(descricao):
            continue

        # Valor: o da própria linha da transação. As linhas de detalhe abaixo
        # dela trazem outros valores que NÃO são o da compra (cotação do dólar,
        # "Total a pagar: R$ X (... + R$ Y de juros)", "Valor original: R$ Z"),
        # então só olhamos o resto do bloco quando a linha não tem valor
        # (descrição quebrada em duas linhas).
        valor_match = _RE_VALOR.search(linha_transacao) or _RE_VALOR.search(bloco)
        if not valor_match:
            # bloco sem valor associado (dado incompleto) - ignora
            continue
        negativo = valor_match.group(1) == "−"
        valor = valor_br_para_float(valor_match.group(2))

        if negativo:
            # pagamento/crédito - não é despesa, não entra no resultado
            continue

        # Fatura de JAN traz compras de DEZ do ano anterior.
        ano_transacao = ano - 1 if mes_fatura and mes_num > mes_fatura else ano
        try:
            data_transacao = date(ano_transacao, mes_num, dia)
        except ValueError:
            continue

        transacoes.append({
            "data": data_transacao,
            "descricao_original": descricao,
            "valor": valor,
        })

    if not transacoes:
        raise ValueError("Não foi possível localizar transações no PDF")

    return transacoes


def aplicar_regra_categoria(descricao: str, regras) -> str | None:
    """Retorna a categoria destino da primeira regra cujo termo_busca aparece
    como palavra inteira (case-insensitive) na descrição informada, ou None se
    nenhuma regra casar. Palavra inteira para "Cooper" (mercado) não pegar
    "Banco Cooperativo Sicoob".

    `regras` é uma lista de tuplas (termo_busca, categoria_destino) — mantém o
    parser desacoplado do banco (as regras são carregadas pela camada de dados).
    """
    for termo_busca, categoria_destino in regras:
        termo = termo_busca.strip()
        if termo and re.search(rf"(?<!\w){re.escape(termo)}(?!\w)", descricao, re.IGNORECASE):
            return categoria_destino
    return None
