"""Identifica automaticamente do que se trata um PDF importado (holerite ou
fatura/extrato de cartão), para a página única de importação.

Estratégia, da mais para a menos confiável:
1. Roda os dois parsers no texto. Se só um deles consegue ler, é esse o tipo
   (e os dados já saem prontos).
2. Se nenhum (ou os dois) leu, conta "sinais" típicos de cada documento
   (ex: "Referente ao mês", "RESUMO DA FATURA"). Um tipo com sinais claros é
   aceito, mas sem dados — a página explica o que não pôde ser lido.
3. Sem sinais claros, devolve tipo None e a página pergunta ao usuário.

Funções puras (sem Streamlit e sem banco).
"""
import re
import unicodedata

from utils.payslip_parser import parse_holerite
from utils.statement_parser import parse_transacoes

TIPOS_DOCUMENTO = {
    "holerite": "📄 Holerite (contracheque)",
    "fatura": "📑 Fatura / extrato de cartão",
}

PARSERS = {"holerite": parse_holerite, "fatura": parse_transacoes}

_SINAIS = {
    "holerite": [
        r"referente ao m[eê]s",
        r"sal[aá]rio\s+l[ií]quido",
        r"holerite|contracheque|recibo de pagamento de sal[aá]rio",
        r"proventos|vencimentos",
        r"\b(FGTS|INSS|IRRF)\b",
    ],
    "fatura": [
        r"TRANSA[ÇC][ÕO]ES\s+DE\s+\d{2}",
        r"RESUMO DA FATURA",
        r"Nu Pagamentos|nubank",
        r"\bFATURA\s+\d{2}\s+[A-ZÇ]{3}\s+\d{4}",
        r"limite (total|dispon[ií]vel)|pagamento m[ií]nimo",
    ],
}
_MIN_SINAIS = 2


def _contar_sinais(texto: str) -> dict[str, int]:
    return {
        tipo: sum(bool(re.search(padrao, texto, re.IGNORECASE)) for padrao in padroes)
        for tipo, padroes in _SINAIS.items()
    }


def ler_como(tipo: str, texto: str):
    """Roda o parser do tipo informado. Devolve (dados, erro)."""
    try:
        return PARSERS[tipo](texto), None
    except ValueError as erro:
        return None, str(erro)


def detectar_tipo(texto: str) -> dict:
    """Retorna {"tipo": "holerite" | "fatura" | None, "dados": ..., "erro": str | None}.

    `dados` é o resultado do parser do tipo detectado (dict do holerite ou lista
    de transações da fatura), ou None quando o tipo foi reconhecido só pelos
    sinais e o parser falhou — nesse caso `erro` diz o que faltou.
    """
    if not texto or not texto.strip():
        return {"tipo": None, "dados": None, "erro": "O PDF não tem texto legível (talvez seja uma imagem escaneada)."}

    resultados = {tipo: ler_como(tipo, texto) for tipo in PARSERS}
    lidos = [tipo for tipo, (dados, _) in resultados.items() if dados]
    sinais = _contar_sinais(texto)

    if len(lidos) == 1:
        tipo = lidos[0]
    else:
        # Nenhum (ou os dois) parsers leram: decide pelos sinais, se forem claros.
        candidatos = lidos or list(PARSERS)
        melhor = max(candidatos, key=lambda t: sinais[t])
        outros = [sinais[t] for t in candidatos if t != melhor]
        if sinais[melhor] < _MIN_SINAIS or (outros and sinais[melhor] == max(outros)):
            return {"tipo": None, "dados": None, "erro": None}
        tipo = melhor

    dados, erro = resultados[tipo]
    return {"tipo": tipo, "dados": dados, "erro": erro}


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).upper()


def sugerir_responsavel(texto: str, responsaveis: list[str]) -> str | None:
    """Responsável cujo primeiro nome aparece no PDF (ex: titular da fatura,
    funcionário do holerite). None se nenhum ou mais de um aparecer."""
    texto_norm = _sem_acento(texto)
    achados = [
        nome for nome in responsaveis
        if (primeiro := _sem_acento(nome).split()[0] if nome.strip() else "")
        and len(primeiro) >= 3
        and re.search(rf"\b{re.escape(primeiro)}\b", texto_norm)
    ]
    return achados[0] if len(achados) == 1 else None
