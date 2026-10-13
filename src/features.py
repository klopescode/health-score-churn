"""
features.py
-----------
Transforma o histórico semanal em uma tabela pronta para análise e modelagem.
Cada linha é um cliente numa semana e traz:

- o health score da regra atual (30/20/30/20);
- features de tendência, calculadas só com o passado do cliente (nada do futuro);
- o alvo: o cliente cancela nas próximas 4 semanas?

Definição de churn usada no projeto: cancelamento formal do contrato.
O objetivo é avisar com antecedência, por isso o alvo olha para as 4 semanas
seguintes ao relatório, e não para a semana em que o cliente cancela.
"""

import pandas as pd

from gerar_dados import CAMINHO_SINTETICO
from health_score import PESOS, calcular_health_score, contar_semanas_em_risco


INDICADORES = list(PESOS)
HORIZONTE_SEMANAS = 4  # antecedência do aviso
JANELA_MEDIA = 4       # semanas usadas nas médias móveis

ALVO = "cancela_em_4_semanas"

FEATURES_TENDENCIA = [
    "media_score_4s",
    "variacao_score",
    "semanas_sem_interacao",
    "semanas_em_risco",
    *[f"taxa_{indicador}_4s" for indicador in INDICADORES],
]
FEATURES_MODELO = [*INDICADORES, "health_score", *FEATURES_TENDENCIA]


def carregar_historico(caminho=CAMINHO_SINTETICO):
    df = pd.read_csv(caminho, parse_dates=["semana", "data_cancelamento"])
    return df.sort_values(["cliente", "semana"]).reset_index(drop=True)


def _semanas_seguidas(condicao, clientes):
    """Quantas semanas seguidas, até a atual, a condição é verdadeira para cada cliente."""
    contagem = []
    atual = {}
    for cliente, verdadeira in zip(clientes, condicao):
        atual[cliente] = atual.get(cliente, 0) + 1 if verdadeira else 0
        contagem.append(atual[cliente])
    return pd.Series(contagem, index=condicao.index)


def adicionar_features(df):
    """Espera o histórico ordenado por cliente e semana, com uma linha por semana ativa."""
    df = df.sort_values(["cliente", "semana"]).reset_index(drop=True)
    por_cliente = df.groupby("cliente")

    df["health_score"] = calcular_health_score(df)
    df["media_score_4s"] = por_cliente["health_score"].transform(
        lambda s: s.rolling(JANELA_MEDIA, min_periods=1).mean()
    )
    df["variacao_score"] = por_cliente["health_score"].diff().fillna(0)
    df["semanas_sem_interacao"] = _semanas_seguidas(df["interacao"] == 0, df["cliente"])
    df["semanas_em_risco"] = contar_semanas_em_risco(df)
    for indicador in INDICADORES:
        df[f"taxa_{indicador}_4s"] = por_cliente[indicador].transform(
            lambda s: s.rolling(JANELA_MEDIA, min_periods=1).mean()
        )
    return df


def adicionar_alvo(df, horizonte=HORIZONTE_SEMANAS):
    """
    cancela_em_4_semanas = 1 se o cancelamento acontece depois da semana do relatório
    e em até `horizonte` semanas.

    janela_observada = False nas últimas semanas do dataset: ainda não dá para saber
    se esses clientes vão cancelar, então essas linhas ficam fora do treino e do teste.
    """
    dias_ate_cancelar = (df["data_cancelamento"] - df["semana"]).dt.days
    df[ALVO] = ((dias_ate_cancelar > 0) & (dias_ate_cancelar <= 7 * horizonte)).astype(int)
    df["semanas_ate_cancelar"] = (dias_ate_cancelar + 6) // 7  # 1 = cancela na semana seguinte
    df["janela_observada"] = df["semana"] + pd.Timedelta(weeks=horizonte) <= df["semana"].max()
    return df


def preparar_base(caminho=CAMINHO_SINTETICO, horizonte=HORIZONTE_SEMANAS):
    return adicionar_alvo(adicionar_features(carregar_historico(caminho)), horizonte)
