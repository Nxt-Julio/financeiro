"""Regras de cálculo dos cartões de crédito (Contas & Cartões).

Funções puras (sem banco e sem Streamlit). Convenção de ciclo usada aqui (a do
Nubank e da maioria dos bancos): a fatura **fecha** no `dia_fechamento`; compras
feitas a partir desse dia já caem na fatura seguinte — por isso o "melhor dia de
compra" é o próprio dia de fechamento. A fatura vence no próximo
`dia_vencimento` depois do fechamento.

Limite usado: como o app não registra pagamento de fatura, considera-se que as
faturas já vencidas foram pagas. O limite comprometido é a soma das despesas do
cartão ainda não pagas a partir do início do ciclo atual (fatura aberta +
parcelas futuras já lançadas) e da fatura fechada que ainda não venceu.
"""
import calendar
import datetime


def _dia(ano: int, mes: int, dia: int) -> datetime.date:
    """Data com o dia limitado ao último dia do mês (ex: dia 31 em fevereiro)."""
    return datetime.date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


def _somar_meses(ano: int, mes: int, n: int) -> tuple[int, int]:
    total = ano * 12 + (mes - 1) + n
    return total // 12, total % 12 + 1


def fechamento(ano: int, mes: int, dia_fechamento: int) -> datetime.date:
    return _dia(ano, mes, dia_fechamento)


def vencimento_apos(data_fechamento: datetime.date, dia_vencimento: int) -> datetime.date:
    """Primeiro `dia_vencimento` estritamente depois do fechamento."""
    candidato = _dia(data_fechamento.year, data_fechamento.month, dia_vencimento)
    if candidato <= data_fechamento:
        ano, mes = _somar_meses(data_fechamento.year, data_fechamento.month, 1)
        candidato = _dia(ano, mes, dia_vencimento)
    return candidato


def ciclos(cartao: dict, hoje: datetime.date) -> dict:
    """Ciclos da fatura **aberta** (recebendo compras hoje) e da **fechada**
    (a anterior). Cada um: inicio (incl.), fim (excl. = dia do fechamento) e
    vencimento."""
    dia_f = int(cartao["dia_fechamento"])
    fech_mes = fechamento(hoje.year, hoje.month, dia_f)
    if hoje < fech_mes:
        fim_aberta = fech_mes
    else:
        fim_aberta = fechamento(*_somar_meses(hoje.year, hoje.month, 1), dia_f)
    inicio_aberta = fechamento(*_somar_meses(fim_aberta.year, fim_aberta.month, -1), dia_f)
    inicio_fechada = fechamento(*_somar_meses(inicio_aberta.year, inicio_aberta.month, -1), dia_f)
    dia_v = int(cartao["dia_vencimento"])
    return {
        "aberta": {"inicio": inicio_aberta, "fim": fim_aberta, "vencimento": vencimento_apos(fim_aberta, dia_v)},
        "fechada": {"inicio": inicio_fechada, "fim": inicio_aberta, "vencimento": vencimento_apos(inicio_aberta, dia_v)},
    }


def _data(t: dict) -> datetime.date:
    return datetime.date.fromisoformat(str(t["data"])[:10])


def lancamentos_no_ciclo(transacoes: list[dict], cartao_id: int, ciclo: dict) -> list[dict]:
    """Despesas do cartão com data dentro do ciclo, mais recentes primeiro."""
    return sorted(
        (t for t in transacoes
         if t.get("cartao_id") == cartao_id and t["tipo"] == "despesa" and ciclo["inicio"] <= _data(t) < ciclo["fim"]),
        key=lambda t: str(t["data"]),
        reverse=True,
    )


def resumo_cartao(cartao: dict, transacoes: list[dict], hoje: datetime.date | None = None) -> dict:
    """Números do card do cartão: fatura aberta/fechada, limite usado/disponível,
    melhor dia de compra."""
    hoje = hoje or datetime.date.today()
    c = ciclos(cartao, hoje)
    aberta = lancamentos_no_ciclo(transacoes, cartao["id"], c["aberta"])
    fechada = lancamentos_no_ciclo(transacoes, cartao["id"], c["fechada"])
    total_aberta = round(sum(float(t["valor"]) for t in aberta), 2)
    total_fechada = round(sum(float(t["valor"]) for t in fechada), 2)

    # Fatura fechada ainda não vencida também ocupa o limite.
    inicio_uso = c["fechada"]["inicio"] if c["fechada"]["vencimento"] >= hoje else c["aberta"]["inicio"]
    usado = round(sum(
        float(t["valor"]) for t in transacoes
        if t.get("cartao_id") == cartao["id"] and t["tipo"] == "despesa"
        and not t.get("pago") and _data(t) >= inicio_uso
    ), 2)
    limite = float(cartao["limite"] or 0)
    return {
        "ciclos": c,
        "aberta": aberta,
        "fechada": fechada,
        "total_aberta": total_aberta,
        "total_fechada": total_fechada,
        "limite": limite,
        "usado": usado,
        "disponivel": round(limite - usado, 2),
        "percentual_usado": min(usado / limite, 1.0) if limite > 0 else 0.0,
        "melhor_dia": int(cartao["dia_fechamento"]),
    }
