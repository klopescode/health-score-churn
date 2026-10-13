import pandas as pd
import pytest

import gerar_dados as gd
import health_score as hs


@pytest.fixture(scope="module")
def dados():
    return gd.gerar_dados(incluir_ocultas=True)


def test_mesma_semente_gera_os_mesmos_dados():
    pd.testing.assert_frame_equal(gd.gerar_dados(n_clientes=20), gd.gerar_dados(n_clientes=20))


def test_semente_diferente_gera_dados_diferentes():
    assert not gd.gerar_dados(n_clientes=20, semente=1).equals(gd.gerar_dados(n_clientes=20, semente=2))


def test_tamanho_do_dataset(dados):
    assert dados["cliente"].nunique() == gd.N_CLIENTES
    assert dados["semana"].nunique() == gd.N_SEMANAS
    assert not dados.duplicated(["semana", "cliente"]).any()


def test_semanas_sao_sextas_feiras_seguidas(dados):
    semanas = pd.Series(sorted(dados["semana"].unique()))
    assert semanas.iloc[0] == gd.PRIMEIRA_SEMANA
    assert (semanas.dt.dayofweek == 4).all()
    assert (semanas.diff().dropna() == pd.Timedelta(weeks=1)).all()


def test_cada_cliente_aparece_em_semanas_seguidas(dados):
    for _, historico in dados.groupby("cliente"):
        assert (historico["semana"].diff().dropna() == pd.Timedelta(weeks=1)).all()


def test_indicadores_sao_0_ou_1(dados):
    for indicador in gd.INDICADORES:
        assert dados[indicador].isin([0, 1]).all()


def test_colunas_de_cancelamento_sao_coerentes(dados):
    por_cliente = dados.groupby("cliente").agg(
        cancelou=("cancelou", "nunique"), data=("data_cancelamento", "nunique")
    )
    assert (por_cliente["cancelou"] == 1).all()  # mesmo valor em todas as linhas do cliente
    assert (dados["cancelou"] == 1).eq(dados["data_cancelamento"].notna()).all()


def test_cliente_some_depois_de_cancelar(dados):
    canceladas = dados[dados["cancelou"] == 1].groupby("cliente").agg(
        ultima_semana=("semana", "max"), data=("data_cancelamento", "first")
    )
    dias = (canceladas["data"] - canceladas["ultima_semana"]).dt.days
    assert dias.between(1, 7).all()
    assert (canceladas["data"] <= dados["semana"].max()).all()


def test_taxa_de_cancelamento_plausivel(dados):
    resumo = gd.resumir(dados)
    assert 0.15 <= resumo["cancelaram"] / resumo["clientes"] <= 0.45
    assert 0 < resumo["cancelamentos_abruptos"] < resumo["cancelaram"]


def test_cliente_some_do_grupo_antes_de_cancelar(dados):
    desgaste = dados[dados["tipo_cancelamento"] == "desgaste"]
    ultimas_semanas = desgaste[(desgaste["data_cancelamento"] - desgaste["semana"]).dt.days <= 14]
    quem_ficou = dados[dados["cancelou"] == 0]
    assert ultimas_semanas["interacao"].mean() < quem_ficou["interacao"].mean() - 0.3


def test_colunas_ocultas_so_quando_pedidas():
    assert "perfil" not in gd.gerar_dados(n_clientes=5).columns
    assert {"perfil", "tipo_cancelamento"} <= set(gd.gerar_dados(n_clientes=5, incluir_ocultas=True).columns)


def test_csv_gerado_passa_na_validacao_do_health_score(tmp_path):
    caminho = tmp_path / "sinteticos.csv"
    gd.salvar_csv(gd.gerar_dados(n_clientes=30), caminho)
    df = hs.carregar_dados(caminho)
    assert df["cliente"].nunique() == 30


def test_csv_versionado_e_igual_ao_gerado():
    """Se mudar o gerador, rode `python src/gerar_dados.py` para atualizar o CSV."""
    versionado = pd.read_csv(gd.CAMINHO_SINTETICO, parse_dates=["semana", "data_cancelamento"])
    gerado = gd.gerar_dados()
    pd.testing.assert_frame_equal(versionado, gerado, check_dtype=False)
