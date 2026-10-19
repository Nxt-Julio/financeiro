"""Identifica automaticamente do que se trata um PDF importado (holerite,
fatura do cartão ou extrato da conta), para a página única de importação.

Estratégia, da mais para a menos confiável:
1. Roda todos os parsers no texto. Se só um deles consegue ler, é esse o tipo
   (e os dados já saem prontos).
2. Se nenhum (ou mais de um) leu, conta "sinais" típicos de cada documento
   (ex: "Referente ao mês", "RESUMO DA FATURA"). Um tipo com sinais claros é
   aceito, mas sem dados — a página explica o que não pôde ser lido.
3. Sem sinais claros, devolve tipo None e a página pergunta ao usuário.

Funções puras (sem Streamlit e sem banco).
"""
import datetime
import re
import unicodedata

from utils.account_statement_parser import parse_extrato_conta
from utils.payslip_parser import parse_holerite
from utils.statement_parser import parse_transacoes

TIPOS_DOCUMENTO = {
    "holerite": "📄 Holerite (contracheque)",
    "fatura": "💳 Fatura do cartão",
    "extrato_conta": "🏦 Extrato da conta",
}

PARSERS = {"holerite": parse_holerite, "fatura": parse_transacoes, "extrato_conta": parse_extrato_conta}

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
    "extrato_conta": [
        r"Total de entradas",
        r"Total de sa[íi]das",
        r"Saldo inicial",
        r"^Movimenta[çc][õo]es\s*$",
        r"VALORES EM R\$",
    ],
}
_MIN_SINAIS = 2


def _contar_sinais(texto: str) -> dict[str, int]:
    return {
        tipo: sum(bool(re.search(padrao, texto, re.IGNORECASE | re.MULTILINE)) for padrao in padroes)
        for tipo, padroes in _SINAIS.items()
    }


def ler_como(tipo: str, texto: str):
    """Roda o parser do tipo informado. Devolve (dados, erro)."""
    try:
        return PARSERS[tipo](texto), None
    except ValueError as erro:
        return None, str(erro)


def detectar_tipo(texto: str) -> dict:
    """Retorna {"tipo": "holerite" | "fatura" | "extrato_conta" | None, "dados": ..., "erro": str | None}.

    `dados` é o resultado do parser do tipo detectado (dict do holerite, lista
    de transações da fatura ou dict do extrato da conta), ou None quando o tipo
    foi reconhecido só pelos sinais e o parser falhou — nesse caso `erro` diz o
    que faltou.
    """
    if not texto or not texto.strip():
        return {"tipo": None, "dados": None, "erro": "O PDF não tem texto legível (talvez seja uma imagem escaneada)."}

    resultados = {tipo: ler_como(tipo, texto) for tipo in PARSERS}
    lidos = [tipo for tipo, (dados, _) in resultados.items() if dados]
    sinais = _contar_sinais(texto)

    if len(lidos) == 1:
        tipo = lidos[0]
    else:
        # Nenhum (ou mais de um) parser leu: decide pelos sinais, se forem claros.
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


# Situação de cada lançamento lido, para a tabela de conferência da importação.
# Só "novo" vem marcado para importar; os demais vêm desmarcados com o motivo.
SITUACOES = {
    "novo": "Novo",
    "importado": "Já importado",
    "fatura": "Pagamento de fatura",
    "interno": "Entre vocês",
    "duplicado": "Possível duplicado",
}


def _primeiro_nome(texto: str) -> str:
    partes = _sem_acento(texto or "").split()
    return partes[0] if partes else ""


def classificar_lancamentos(novos: list[dict], existentes: list[dict], nomes_internos: set[str],
                            janela_dias: int | None = None) -> list[str]:
    """Uma chave de SITUACOES para cada lançamento de `novos`.

    - importado: mesma data, valor, descrição e tipo de algo já gravado;
    - fatura: pagamento da fatura do cartão (as compras já entram pela fatura);
    - interno: contraparte é um de vocês (ex: Pix entre contas próprias ou do
      casal) — não é ganho nem gasto;
    - duplicado: mesmo tipo e valor de algo já gravado a até `janela_dias`
      dias (ex: boleto que já é uma parcela cadastrada). Desligado se None.
    """
    def _data(t):
        return str(t["data"])[:10]

    exatos = {
        (_data(t), round(float(t["valor"]), 2), (t.get("descricao_original") or "").strip().lower(), t["tipo"])
        for t in existentes
    }
    datas_por_valor = {}
    for t in existentes:
        datas_por_valor.setdefault((t["tipo"], round(float(t["valor"]), 2)), []).append(_data(t))

    internos = {_primeiro_nome(n) for n in nomes_internos} - {""}
    situacoes = []
    for t in novos:
        tipo = t.get("tipo", "despesa")
        valor = round(float(t["valor"]), 2)
        descricao = (t.get("descricao_original") or "").strip().lower()
        if (_data(t), valor, descricao, tipo) in exatos:
            situacoes.append("importado")
        elif descricao.startswith("pagamento de fatura"):
            situacoes.append("fatura")
        elif internos and _primeiro_nome(t.get("estabelecimento")) in internos:
            situacoes.append("interno")
        elif janela_dias is not None and any(
            abs((t["data"] - datetime.date.fromisoformat(d)).days) <= janela_dias
            for d in datas_por_valor.get((tipo, valor), [])
        ):
            situacoes.append("duplicado")
        else:
            situacoes.append("novo")
    return situacoes
