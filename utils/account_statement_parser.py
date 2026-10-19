"""Parsing puro do extrato da CONTA (corrente) Nubank em PDF — tudo o que entrou
e saiu da conta —, sem dependência de Streamlit.

Diferente da fatura do cartão: tem entradas (receitas) e saídas (despesas), e o
valor fica no fim da linha sem "R$". Layout calibrado com extratos reais
("NU_<conta>_01AGO2026_31AGO2026.pdf"), extraídos com pdfplumber:

    Movimentações
    04 AGO 2026 Total de entradas + 672,00
    Transferência recebida pelo Pix FULANO DE TAL - •••.245.899-•• - BANCO 672,00
    Agência: 3039 Conta: 1098157-            <- linhas de detalhe (ignoradas)
    Total de saídas - 1.671,36
    Pagamento de boleto efetuado SANTANDER ... 1.671,36

O dia vem no cabeçalho "DD MMM AAAA Total de ..."; dias com entradas e saídas
repetem só o "Total de saídas" (sem data). Cada lançamento é uma linha que
termina em valor no formato BR.
"""
import re
from datetime import date

from utils.statement_parser import MESES_PT, valor_br_para_float

_NUM_BR = r"\d{1,3}(?:\.\d{3})*,\d{2}"
_RE_DIA = re.compile(r"^(\d{2}) ([A-ZÇ]{3}) (\d{4})\s+(.*)$")
_RE_TOTAL_DIA = re.compile(rf"^Total de (entradas|sa[íi]das)\s*[+\-−]\s*{_NUM_BR}$", re.IGNORECASE)
_RE_ITEM = re.compile(rf"^(.*\S)\s+({_NUM_BR})$")

# Prefixo do lançamento -> rótulo curto. A contraparte é o que vem depois.
_PREFIXOS = [
    ("Transferência recebida pelo Pix", "Pix recebido"),
    ("Transferência enviada pelo Pix", "Pix enviado"),
    ("Transferência Recebida", "Transferência recebida"),
    ("Transferência enviada", "Transferência enviada"),
    ("Pagamento de boleto efetuado", "Boleto"),
    ("Pagamento de fatura", "Pagamento de fatura"),
    ("Compra no débito", "Débito"),
]


def _totais_documento(texto: str) -> tuple[float | None, float | None]:
    """Totais do resumo do período ("Total de entradas +5.329,00")."""
    ent = re.search(rf"Total de entradas\s*\+\s*({_NUM_BR})", texto)
    sai = re.search(rf"Total de sa[íi]das\s*[-−]\s*({_NUM_BR})", texto)
    return (valor_br_para_float(ent.group(1)) if ent else None,
            valor_br_para_float(sai.group(1)) if sai else None)


def _descrever(texto_linha: str) -> tuple[str, str]:
    """(descrição curta, contraparte). Ex: ("Pix recebido: ALVARO ...", "ALVARO ...")."""
    for prefixo, rotulo in _PREFIXOS:
        if texto_linha.lower().startswith(prefixo.lower()):
            resto = texto_linha[len(prefixo):].strip()
            # Contraparte vai até o primeiro " - " (depois vêm CPF/CNPJ mascarado e banco).
            contraparte = re.split(r"\s+-\s+", resto)[0].strip(" -") if resto else ""
            return (f"{rotulo}: {contraparte}" if contraparte else rotulo), contraparte
    limpo = re.split(r"\s+-\s+", texto_linha)[0].strip()
    return limpo, limpo


def parse_extrato_conta(texto: str) -> dict:
    """Extrai as movimentações do extrato da conta.

    Retorna {"titular", "transacoes", "total_entradas", "total_saidas"}, onde
    cada transação tem: data (date), descricao_original, estabelecimento
    (contraparte), valor (positivo) e tipo ("receita" | "despesa").
    `total_*` são os totais declarados no resumo do PDF (para conferência).

    Levanta ValueError amigável se o texto não tiver o layout esperado.
    """
    if not texto or not texto.strip():
        raise ValueError("Não foi possível extrair texto do PDF enviado")

    inicio = re.search(r"^Movimenta[çc][õo]es\s*$", texto, re.MULTILINE)
    if not inicio or not re.search(r"Total de entradas", texto):
        raise ValueError("Não foi possível localizar as movimentações da conta no PDF")

    titular = texto.strip().splitlines()[0].strip()
    transacoes = []
    dia_atual = None
    tipo_atual = None

    for linha in texto[inicio.end():].splitlines():
        linha = linha.strip()
        if not linha:
            continue

        m_dia = _RE_DIA.match(linha)
        if m_dia:
            mes = MESES_PT.get(m_dia.group(2).lower())
            if mes:
                try:
                    dia_atual = date(int(m_dia.group(3)), mes, int(m_dia.group(1)))
                except ValueError:
                    dia_atual = None
                linha = m_dia.group(4).strip()

        m_total = _RE_TOTAL_DIA.match(linha)
        if m_total:
            tipo_atual = "receita" if m_total.group(1).lower() == "entradas" else "despesa"
            continue

        m_item = _RE_ITEM.match(linha)
        if not m_item or dia_atual is None or tipo_atual is None:
            continue  # cabeçalho/rodapé de página ou linha de detalhe

        descricao, contraparte = _descrever(m_item.group(1).strip())
        transacoes.append({
            "data": dia_atual,
            "descricao_original": descricao,
            "estabelecimento": contraparte,
            "valor": valor_br_para_float(m_item.group(2)),
            "tipo": tipo_atual,
        })

    if not transacoes:
        raise ValueError("Não foi possível localizar movimentações no extrato da conta")

    total_entradas, total_saidas = _totais_documento(texto)
    return {
        "titular": titular,
        "transacoes": transacoes,
        "total_entradas": total_entradas,
        "total_saidas": total_saidas,
    }
