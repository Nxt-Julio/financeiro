"""Regras de cálculo da Alocação Financeira (vínculo De/Para receita -> despesa).

Funções puras (sem banco e sem Streamlit): recebem as transações e os vínculos
já carregados e devolvem, para cada transação, quanto já foi alocado/coberto,
quanto ainda está livre/faltando e o status para os cards.

- **Receita**: `total`, `alocado` (destinado a despesas) e `disponivel` (saldo livre).
- **Despesa**: `total`, `alocado` (já coberto por receitas) e `disponivel` (o que falta cobrir).

A gravação/validação dos vínculos fica em `database.salvar_alocacao`.
"""
from collections import defaultdict

# Diferença máxima (R$) tratada como zero — evita "faltam R$ 0,00" por
# arredondamento de float.
TOLERANCIA = 0.005

# status -> (rótulo, classe CSS da tag). A classe define a cor (ver utils/ui.py).
STATUS_DESPESA = {
    "total": ("Totalmente Coberto", "tag-ok"),
    "parcial": ("Parcialmente Coberto", "tag-parcial"),
    "nenhum": ("Pendente", "tag-pendente"),
    "excedido": ("Cobertura acima do valor", "tag-erro"),
}
STATUS_RECEITA = {
    "total": ("Totalmente Alocada", "tag-ok"),
    "parcial": ("Parcialmente Alocada", "tag-parcial"),
    "nenhum": ("Livre", "tag-livre"),
    "excedido": ("Alocada acima do valor", "tag-erro"),
}


def classificar(total: float, alocado: float) -> str:
    """'total', 'parcial', 'nenhum' ou 'excedido' (quando o valor da transação
    foi editado para baixo depois de vinculado)."""
    if alocado > total + TOLERANCIA:
        return "excedido"
    if alocado <= TOLERANCIA:
        return "nenhum"
    if total - alocado <= TOLERANCIA:
        return "total"
    return "parcial"


def calcular_saldos(transacoes: list[dict], alocacoes: list[dict]) -> dict[int, dict]:
    """Mapa id_transacao -> {total, alocado, disponivel, percentual, status,
    rotulo, classe} para todas as receitas e despesas."""
    alocado = defaultdict(float)
    for a in alocacoes:
        alocado[a["receita_id"]] += a["valor"]
        alocado[a["despesa_id"]] += a["valor"]

    saldos = {}
    for t in transacoes:
        total = round(float(t["valor"]), 2)
        usado = round(alocado[t["id"]], 2)
        status = classificar(total, usado)
        rotulo, classe = (STATUS_RECEITA if t["tipo"] == "receita" else STATUS_DESPESA)[status]
        saldos[t["id"]] = {
            "total": total,
            "alocado": usado,
            "disponivel": round(max(total - usado, 0.0), 2),
            "percentual": min(usado / total, 1.0) if total > 0 else 0.0,
            "status": status,
            "rotulo": rotulo,
            "classe": classe,
        }
    return saldos


def distribuir(capacidade: float, necessidades: list[float]) -> list[float]:
    """Sugestão gulosa de valores ao vincular uma origem a vários destinos: cobre
    cada destino por inteiro, na ordem, até a capacidade da origem acabar.

    >>> distribuir(3000, [2000, 1500, 500])
    [2000.0, 1000.0, 0.0]
    """
    sugestao = []
    restante = max(capacidade, 0.0)
    for necessidade in necessidades:
        valor = round(float(min(necessidade, restante)), 2)
        sugestao.append(valor)
        restante -= valor
    return sugestao
