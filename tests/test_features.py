import pandas as pd
import pytest

import features as ft


def historico(linhas):
    """linhas: (semana, cliente, operacional, criativo, resultado, interacao, data_cancelamento)"""
    df = pd.DataFrame(linhas, columns=["semana", "cliente", *ft.INDICADORES, "data_cancelamento"])
    df["semana"] = pd.to_datetime(df["semana"])
    df["data_cancelamento"] = pd.to_datetime(df["data_cancelamento"])
    return df


def semanas(n, inicio="2024-01-05"):
    return [(pd.Timestamp(inicio) + pd.Timedelta(weeks=k)).strftime("%Y-%m-%d") for k in range(n)]


@pytest.fixture
def um_cliente():
    #               op cr re in
    indicadores = [(1, 1, 1, 1),   # 100
                   (1, 1, 1, 0),   # 80
                   (1, 1, 0, 0),   # 50
                   (0, 1, 0, 0),   # 20
                   (0, 0, 0, 0),   # 0
                   (1, 1, 1, 1)]   # 100
    linhas = [(s, "A", *ind, None) for s, ind in zip(semanas(6), indicadores)]
    return ft.adicionar_features(historico(linhas))


def test_health_score_da_regra(um_cliente):
    assert um_cliente["health_score"].tolist() == [100, 80, 50, 20, 0, 100]


def test_media_das_ultimas_4_semanas(um_cliente):
    assert um_cliente["media_score_4s"].tolist() == [100, 90, pytest.approx(230 / 3), 62.5, 37.5, 42.5]


def test_variacao_em_relacao_a_semana_anterior(um_cliente):
    assert um_cliente["variacao_score"].tolist() == [0, -20, -30, -30, -20, 100]


def test_semanas_seguidas_sem_interacao(um_cliente):
    assert um_cliente["semanas_sem_interacao"].tolist() == [0, 1, 2, 3, 4, 0]


def test_semanas_seguidas_em_risco(um_cliente):
    assert um_cliente["semanas_em_risco"].tolist() == [0, 0, 0, 1, 2, 0]


def test_taxa_de_interacao_nas_ultimas_4_semanas(um_cliente):
    assert um_cliente["taxa_interacao_4s"].tolist() == [1, 0.5, pytest.approx(1 / 3), 0.25, 0, 0.25]


def test_features_sao_calculadas_por_cliente():
    linhas = [(s, "A", 0, 0, 0, 0, None) for s in semanas(3)]
    linhas += [(s, "B", 1, 1, 1, 1, None) for s in semanas(3)]
    df = ft.adicionar_features(historico(linhas)).set_index(["cliente", "semana"])
    assert (df.loc["B", "media_score_4s"] == 100).all()
    assert (df.loc["B", "semanas_sem_interacao"] == 0).all()
    assert df.loc["B", "variacao_score"].tolist() == [0, 0, 0]


def test_features_nao_usam_o_futuro():
    linhas = [(s, "A", 1, 1, 1, 1, None) for s in semanas(6)]
    original = ft.adicionar_features(historico(linhas))
    linhas[-1] = (linhas[-1][0], "A", 0, 0, 0, 0, None)  # muda só a última semana
    alterado = ft.adicionar_features(historico(linhas))
    colunas = ft.FEATURES_MODELO
    pd.testing.assert_frame_equal(original[colunas].iloc[:-1], alterado[colunas].iloc[:-1])


def test_alvo_marca_as_4_semanas_antes_do_cancelamento():
    # Cliente A cancela 3 dias depois da 7ª semana; B nunca cancela. O dataset tem 12 semanas.
    datas = semanas(12)
    cancelamento = (pd.Timestamp(datas[6]) + pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    linhas = [(s, "A", 1, 1, 1, 1, cancelamento) for s in datas[:7]]
    linhas += [(s, "B", 1, 1, 1, 1, None) for s in datas]
    df = ft.adicionar_alvo(ft.adicionar_features(historico(linhas)))

    alvo_a = df[df["cliente"] == "A"][ft.ALVO].tolist()
    assert alvo_a == [0, 0, 0, 1, 1, 1, 1]
    assert df[df["cliente"] == "A"]["semanas_ate_cancelar"].tolist()[-4:] == [4, 3, 2, 1]
    assert df[df["cliente"] == "B"][ft.ALVO].sum() == 0


def test_ultimas_4_semanas_do_dataset_ficam_sem_janela_observada():
    linhas = [(s, "B", 1, 1, 1, 1, None) for s in semanas(10)]
    df = ft.adicionar_alvo(ft.adicionar_features(historico(linhas)))
    assert df["janela_observada"].tolist() == [True] * 6 + [False] * 4


def test_preparar_base_com_o_dataset_simulado():
    base = ft.preparar_base()
    assert set(ft.FEATURES_MODELO) <= set(base.columns)
    assert base[ft.FEATURES_MODELO].notna().all().all()
    # Cada cliente que cancelou com pelo menos 4 semanas de histórico tem exatamente 4 linhas positivas
    positivas = base[base["cancelou"] == 1].groupby("cliente").agg(
        positivas=(ft.ALVO, "sum"), semanas=("semana", "size")
    )
    assert (positivas.loc[positivas["semanas"] >= 4, "positivas"] == 4).all()
