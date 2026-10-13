import numpy as np
import pandas as pd
import pytest

import features as ft
import gerar_dados as gd
import modelos as md


@pytest.fixture(scope="module")
def base():
    return ft.adicionar_alvo(ft.adicionar_features(gd.gerar_dados(n_clientes=120, semente=7)))


# --- Divisão temporal ---

def test_treino_nao_ve_o_periodo_de_teste(base):
    for treino, teste in md.blocos_temporais(base):
        inicio_teste = teste["semana"].min()
        assert (treino["semana"] + pd.Timedelta(weeks=ft.HORIZONTE_SEMANAS) <= inicio_teste).all()
        assert treino["janela_observada"].all() and teste["janela_observada"].all()


def test_blocos_de_teste_sao_seguidos_e_terminam_na_ultima_semana_observavel(base):
    blocos = md.blocos_temporais(base)
    assert len(blocos) == md.BLOCOS_TESTE
    semanas_teste = [sorted(teste["semana"].unique()) for _, teste in blocos]
    assert all(len(s) == md.SEMANAS_POR_BLOCO for s in semanas_teste)
    for anterior, seguinte in zip(semanas_teste, semanas_teste[1:]):
        assert seguinte[0] - anterior[-1] == pd.Timedelta(weeks=1)
    assert semanas_teste[-1][-1] == base.loc[base["janela_observada"], "semana"].max()


def test_blocos_demais_para_poucas_semanas(base):
    with pytest.raises(ValueError):
        md.blocos_temporais(base, n_blocos=10, semanas_por_bloco=8)


# --- Métricas e limiares ---

def test_avaliar_com_exemplo_conhecido():
    teste = pd.DataFrame({
        "cliente": ["A", "A", "B", "B", "C", "C"],
        "semana": pd.to_datetime(["2024-01-05", "2024-01-12"] * 3),
        ft.ALVO: [1, 1, 1, 1, 0, 0],
    })
    alerta = [1, 0, 0, 0, 1, 0]
    risco = [0.9, 0.6, 0.4, 0.3, 0.8, 0.1]
    m = md.avaliar(teste, alerta, risco)
    assert m["Recall"] == 0.25
    assert m["Precisão"] == 0.5
    assert m["Clientes avisados a tempo"] == 0.5   # A foi avisado, B não
    assert m["Alertas por semana"] == 1.0          # 2 alertas em 2 semanas
    assert m["AUC"] == pytest.approx(5 / 8)  # 5 dos 8 pares positivo/negativo em ordem


def test_limiar_para_recall():
    y = np.array([1, 1, 1, 1, 0, 0])
    risco = np.array([0.9, 0.8, 0.7, 0.2, 0.6, 0.1])
    assert md.limiar_para_recall(y, risco, 0.75) == 0.7
    assert md.limiar_para_recall(y, risco, 1.0) == 0.2


def test_limiar_para_volume():
    risco = np.array([0.9, 0.8, 0.8, 0.5, 0.1])
    assert md.limiar_para_volume(risco, n_semanas=1, alertas_por_semana=3) == 0.8
    assert md.limiar_para_volume(risco, n_semanas=1, alertas_por_semana=2) == 0.9  # empate em 0.8
    assert md.limiar_para_volume(risco, n_semanas=1, alertas_por_semana=0) == np.inf


# --- Pesos ---

def test_arredondar_pesos_soma_100_em_multiplos_de_5():
    pesos = md.arredondar_pesos(pd.Series({"a": 33.4, "b": 33.3, "c": 21.6, "d": 11.7}))
    assert sum(pesos.values()) == 100
    assert all(p % 5 == 0 for p in pesos.values())
    assert pesos == {"a": 35, "b": 35, "c": 20, "d": 10}


def test_recalibrar_da_mais_peso_ao_indicador_que_prevê_o_cancelamento():
    rng = np.random.default_rng(0)
    n = 2000
    treino = pd.DataFrame({indicador: rng.integers(0, 2, n) for indicador in ft.INDICADORES})
    # Só a interação influencia o cancelamento
    chance = np.where(treino["interacao"] == 1, 0.02, 0.4)
    treino[ft.ALVO] = (rng.random(n) < chance).astype(int)

    pesos, coeficientes = md.recalibrar_pesos(treino)
    assert sum(pesos.values()) == 100
    assert max(pesos, key=pesos.get) == "interacao"
    assert pesos["interacao"] >= 70
    assert coeficientes["interacao"] < 0


def test_score_com_os_pesos_atuais_e_o_health_score(base):
    assert (md.score_com_pesos(base, md.PESOS) == base["health_score"]).all()


# --- Comparação completa ---

@pytest.fixture(scope="module")
def comparacao(base):
    return md.comparar_metodos(base, n_blocos=2, semanas_por_bloco=8)


def test_comparacao_tem_os_dois_pontos_de_operacao(comparacao):
    tabelas, _ = comparacao
    assert set(tabelas) == {md.MESMO_VOLUME, md.RECALL_META}
    assert tabelas[md.MESMO_VOLUME].index[0] == "Regra atual (score < 50)"
    assert tabelas[md.RECALL_META].index[0] == "Regra atual (score < 80)"
    for ponto, tabela in tabelas.items():
        assert f"Regressão logística, {ponto}" in tabela.index
        metricas = tabela[["Recall", "Precisão", "AUC", "Clientes avisados a tempo"]]
        assert metricas.apply(lambda c: c.between(0, 1)).all().all()


def test_regra_atual_com_corte_50_bate_com_health_score(comparacao):
    tabelas, detalhes = comparacao
    teste = detalhes["teste"]
    esperado = md.avaliar(teste, teste["health_score"] < 50, 100 - teste["health_score"])
    assert tabelas[md.MESMO_VOLUME].loc["Regra atual (score < 50)"].to_dict() == pytest.approx(esperado)


def test_pesos_recalibrados_somam_100(comparacao):
    _, detalhes = comparacao
    assert sum(detalhes["pesos_recalibrados"].values()) == 100


def test_modelo_final_preve_probabilidades(base):
    modelo, limiares = md.treinar_modelo_final(base)
    risco = modelo.predict_proba(base[ft.FEATURES_MODELO])[:, 1]
    assert ((risco >= 0) & (risco <= 1)).all()
    assert set(limiares) == {md.MESMO_VOLUME, md.RECALL_META}
