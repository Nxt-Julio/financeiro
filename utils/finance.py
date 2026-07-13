"""Regras de negócio compartilhadas para separar despesas "realizadas" de
"compromissos futuros" nos dashboards.

Uma despesa é considerada **realizada** (já incorrida) quando sua data já
chegou (`data <= hoje`) OU já foi marcada como paga (`pago = True`, inclusive
se paga adiantada). Caso contrário, é um **compromisso futuro** — dinheiro
ainda não gasto, que pertence à Projeção Futura, não aos totais do dia a dia.

Sem essa separação, um parcelamento de várias parcelas futuras (ex: 20x ao
longo de quase 2 anos) inflaria de uma só vez o "Despesas" do mês, produzindo
saldos negativos sem sentido.
"""
import datetime

import pandas as pd


def marcar_realizadas(df: pd.DataFrame, hoje: datetime.date | None = None) -> pd.Series:
    """Retorna uma Series booleana: True para linhas já realizadas (data <= hoje
    ou pago=True). Espera as colunas `data` (string ISO ou date) e `pago`."""
    hoje = hoje or datetime.date.today()
    datas = pd.to_datetime(df["data"]).dt.date
    pago = df["pago"].fillna(False).astype(bool) if "pago" in df.columns else False
    return (datas <= hoje) | pago


def filtrar_realizadas(df: pd.DataFrame, hoje: datetime.date | None = None) -> pd.DataFrame:
    """Subconjunto de `df` com apenas as transações já realizadas."""
    if df.empty:
        return df
    return df[marcar_realizadas(df, hoje)]
