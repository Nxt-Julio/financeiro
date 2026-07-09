"""Parsing puro de holerite (contracheque) em PDF, sem dependência de Streamlit.

Calibrado a partir de um holerite real gerado pelo sistema "SCI Novo Visual",
extraído com pdfplumber como texto corrido (sem tabela estruturada).
"""
import re
from datetime import date
from calendar import monthrange

import pdfplumber

MESES_PT = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


def valor_br_para_float(texto: str) -> float:
    """Converte um número no formato brasileiro (ex: "5.218,65") para float (5218.65).

    Remove pontos de milhar e troca a vírgula decimal por ponto.
    """
    limpo = texto.strip().replace(".", "").replace(",", ".")
    return float(limpo)


def extrair_texto_pdf(arquivo) -> str:
    """Extrai o texto de todas as páginas de um PDF de holerite.

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


def _extrair_mes_referencia(texto: str) -> tuple[str, date]:
    """Localiza "Referente ao mês: <Mês>/<Ano>" e converte para (string original, date).

    Usamos o ÚLTIMO dia do mês referenciado como "data de recebimento" porque
    holerites desse tipo costumam ser fechados/pagos ainda no próprio mês de
    referência (não há indicação de pagamento no mês seguinte no documento);
    isso também evita ambiguidade quando o holerite é o único dado disponível.
    """
    match = re.search(
        r"Referente ao m[êe]s:\s*([A-Za-zçÇãÃõÕ]+)\s*/\s*(\d{4})",
        texto,
    )
    if not match:
        raise ValueError("Não foi possível localizar o mês de referência no PDF")

    nome_mes_original = match.group(1)
    ano = int(match.group(2))
    mes_num = MESES_PT.get(nome_mes_original.lower())
    if not mes_num:
        raise ValueError(f"Mês de referência não reconhecido: '{nome_mes_original}'")

    ultimo_dia = monthrange(ano, mes_num)[1]
    data_referencia = date(ano, mes_num, ultimo_dia)
    mes_referencia = f"{nome_mes_original}/{ano}"
    return mes_referencia, data_referencia


def _extrair_totais(texto: str) -> tuple[float, float, float]:
    """Localiza Proventos totais, Descontos totais e Salário Líquido.

    Formato esperado no texto extraído (dois números BR seguidos, na linha de
    "Totais", seguidos logo depois por "SALÁRIO LÍQUIDO R$ <valor>"):
        Totais 5.218,65 4.196,65
        ...
        SALÁRIO LÍQUIDO R$ 1.022,00
    """
    numero_br = r"(\d{1,3}(?:\.\d{3})*,\d{2})"

    match_totais = re.search(
        rf"Totais\s+{numero_br}\s+{numero_br}",
        texto,
    )
    if not match_totais:
        raise ValueError("Não foi possível localizar os Totais de Proventos/Descontos no PDF")

    salario_bruto = valor_br_para_float(match_totais.group(1))
    descontos = valor_br_para_float(match_totais.group(2))

    match_liquido = re.search(
        rf"SAL[ÁA]RIO\s+L[ÍI]QUIDO\s*R\$\s*{numero_br}",
        texto,
        re.IGNORECASE,
    )
    if not match_liquido:
        raise ValueError("Não foi possível localizar o Salário Líquido no PDF")

    salario_liquido = valor_br_para_float(match_liquido.group(1))

    return salario_bruto, descontos, salario_liquido


def parse_holerite(texto: str) -> dict:
    """Extrai os dados essenciais de um holerite a partir do texto extraído do PDF.

    Retorna um dict com as chaves:
        mes_referencia (str), data_referencia (date),
        salario_bruto (float), descontos (float), salario_liquido (float)

    Levanta ValueError com mensagem amigável se algum dado essencial não for
    encontrado, para que a página Streamlit possa exibir com st.error.
    """
    if not texto or not texto.strip():
        raise ValueError("Não foi possível extrair texto do PDF enviado")

    mes_referencia, data_referencia = _extrair_mes_referencia(texto)
    salario_bruto, descontos, salario_liquido = _extrair_totais(texto)

    return {
        "mes_referencia": mes_referencia,
        "data_referencia": data_referencia,
        "salario_bruto": salario_bruto,
        "descontos": descontos,
        "salario_liquido": salario_liquido,
    }
