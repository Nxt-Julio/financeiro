"""Período global (mês) escolhido no cabeçalho da sidebar.

O seletor fica em utils/nav.py e grava `st.session_state["periodo"]` como
"AAAA-MM" ou "Todos". As telas leem daqui para filtrar o que mostram.
"""
import datetime

import streamlit as st

TODOS = "Todos"
_MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
_MESES_LONGOS = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def mes_corrente() -> str:
    return datetime.date.today().strftime("%Y-%m")


def opcoes(transacoes: list[dict]) -> list[str]:
    """"Todos" + meses com lançamentos (sempre inclui o mês corrente), do mais
    recente para o mais antigo."""
    meses = {str(t["data"])[:7] for t in transacoes} | {mes_corrente()}
    return [TODOS] + sorted(meses, reverse=True)


def atual() -> str:
    return st.session_state.get("periodo", mes_corrente())


def mes_ou_corrente() -> str:
    """O mês escolhido, ou o corrente quando o período é "Todos" (para telas que
    só fazem sentido mês a mês, como o orçamento)."""
    p = atual()
    return mes_corrente() if p == TODOS else p


def no_periodo(t: dict, periodo: str | None = None) -> bool:
    periodo = periodo or atual()
    return periodo == TODOS or str(t["data"]).startswith(periodo)


def rotulo(periodo: str | None = None, longo: bool = False) -> str:
    periodo = periodo or atual()
    if periodo == TODOS:
        return "Todo o período"
    ano, mes = periodo.split("-")
    if longo:
        return f"{_MESES_LONGOS[int(mes) - 1]} {ano}"
    return f"{_MESES[int(mes) - 1]}/{ano[2:]}"


def filtrar_df(df, periodo: str | None = None):
    """Linhas de um DataFrame (coluna `data`) dentro do período."""
    periodo = periodo or atual()
    if periodo == TODOS or df.empty:
        return df
    return df[df["data"].astype(str).str.startswith(periodo)]
