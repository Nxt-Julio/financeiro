from dateutil.relativedelta import relativedelta


def gerar_parcelas(valor_total: float, num_parcelas: int, data_primeira_parcela):
    """Divide valor_total em num_parcelas, projetando vencimentos mensais a partir de data_primeira_parcela.

    Retorna lista de dicts: {parcela_atual, total_parcelas, data_vencimento, valor_parcela}.
    O último centavo residual da divisão é absorvido pela última parcela.
    """
    valor_base = round(valor_total / num_parcelas, 2)
    parcelas = []
    soma_parcial = 0.0

    for i in range(num_parcelas):
        parcela_atual = i + 1
        if parcela_atual == num_parcelas:
            valor_parcela = round(valor_total - soma_parcial, 2)
        else:
            valor_parcela = valor_base
            soma_parcial += valor_parcela

        data_vencimento = data_primeira_parcela + relativedelta(months=i)

        parcelas.append(
            {
                "parcela_atual": parcela_atual,
                "total_parcelas": num_parcelas,
                "data_vencimento": data_vencimento,
                "valor_parcela": valor_parcela,
            }
        )

    return parcelas
