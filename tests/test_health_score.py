from pathlib import Path

import pandas as pd
import pytest

import health_score as hs


CABECALHO = "semana,cliente,operacional,criativo,resultado,interacao\n"


def escrever_csv(tmp_path, linhas, cabecalho=CABECALHO):
    caminho = tmp_path / "dados.csv"
    caminho.write_text(cabecalho + "".join(linha + "\n" for linha in linhas), encoding="utf-8")
    return caminho


def relatorio_de(tmp_path, linhas):
    return hs.gerar_relatorio(hs.carregar_dados(escrever_csv(tmp_path, linhas)))


def ultima_semana_por_cliente(df):
    return df[df["semana"] == df["semana"].max()].set_index("cliente")


# --- Cálculo e classificação ---

def test_score_maximo_e_minimo():
    assert hs.calcular_health_score({"operacional": 1, "criativo": 1, "resultado": 1, "interacao": 1}) == 100
    assert hs.calcular_health_score({"operacional": 0, "criativo": 0, "resultado": 0, "interacao": 0}) == 0


def test_score_soma_apenas_indicadores_ok():
    assert hs.calcular_health_score({"operacional": 1, "criativo": 0, "resultado": 1, "interacao": 0}) == 60


@pytest.mark.parametrize("score, esperado", [
    (100, "🟢 Saudável"),
    (80, "🟢 Saudável"),
    (79, "🟡 Atenção"),
    (50, "🟡 Atenção"),
    (49, "🔴 Risco Alto"),
    (0, "🔴 Risco Alto"),
])
def test_classificar_risco_nos_limites(score, esperado):
    assert hs.classificar_risco(score) == esperado


# --- Leitura e validação ---

def test_carrega_dados_de_exemplo():
    df = hs.carregar_dados(hs.CAMINHO_DADOS)
    assert len(df) == 20
    assert df["semana"].dtype.kind == "M"
    for coluna in hs.PESOS:
        assert df[coluna].isin([0, 1]).all()


def test_caminho_padrao_fica_na_pasta_do_script():
    assert hs.CAMINHO_DADOS == Path(hs.__file__).resolve().parent / "dados_clientes.csv"


def test_espacos_extras_sao_ignorados(tmp_path):
    df = hs.carregar_dados(escrever_csv(tmp_path, ["2024-01-05, Cliente A , 1 ,1,1, 0"]))
    assert df.loc[0, "cliente"] == "Cliente A"
    assert df.loc[0, "operacional"] == 1


def test_celula_vazia_indica_a_linha(tmp_path):
    caminho = escrever_csv(tmp_path, [
        "2024-01-05,Cliente A,1,1,1,1",
        "2024-01-05,Cliente B,1,1,1,",
    ])
    with pytest.raises(hs.DadosInvalidosError, match="linha 3: 'interacao' está vazio"):
        hs.carregar_dados(caminho)


def test_valor_diferente_de_0_ou_1(tmp_path):
    caminho = escrever_csv(tmp_path, ["2024-01-05,Cliente A,1,1,1,2"])
    with pytest.raises(hs.DadosInvalidosError, match="'interacao' deve ser 0 ou 1, mas está '2'"):
        hs.carregar_dados(caminho)


def test_texto_no_lugar_do_numero(tmp_path):
    caminho = escrever_csv(tmp_path, ["2024-01-05,Cliente A,sim,1,1,1"])
    with pytest.raises(hs.DadosInvalidosError, match="'operacional' deve ser 0 ou 1, mas está 'sim'"):
        hs.carregar_dados(caminho)


def test_data_invalida(tmp_path):
    caminho = escrever_csv(tmp_path, ["05/01/2024,Cliente A,1,1,1,1"])
    with pytest.raises(hs.DadosInvalidosError, match="data inválida '05/01/2024'"):
        hs.carregar_dados(caminho)


def test_cliente_vazio(tmp_path):
    caminho = escrever_csv(tmp_path, ["2024-01-05,,1,1,1,1"])
    with pytest.raises(hs.DadosInvalidosError, match="linha 2: 'cliente' está vazio"):
        hs.carregar_dados(caminho)


def test_cliente_repetido_na_mesma_semana(tmp_path):
    caminho = escrever_csv(tmp_path, [
        "2024-01-05,Cliente A,1,1,1,1",
        "2024-01-05,Cliente A,0,0,0,0",
    ])
    with pytest.raises(hs.DadosInvalidosError, match="linhas 2, 3: 'Cliente A' aparece mais de uma vez"):
        hs.carregar_dados(caminho)


def test_coluna_ausente(tmp_path):
    caminho = escrever_csv(tmp_path, ["2024-01-05,Cliente A,1,1,1"],
                           cabecalho="semana,cliente,operacional,criativo,resultado\n")
    with pytest.raises(hs.DadosInvalidosError, match="Colunas ausentes no CSV: interacao"):
        hs.carregar_dados(caminho)


def test_csv_so_com_cabecalho(tmp_path):
    with pytest.raises(hs.DadosInvalidosError, match="nenhuma linha de dados"):
        hs.carregar_dados(escrever_csv(tmp_path, []))


def test_arquivo_vazio(tmp_path):
    with pytest.raises(hs.DadosInvalidosError, match="está vazio"):
        hs.carregar_dados(escrever_csv(tmp_path, [], cabecalho=""))


def test_lista_todos_os_erros_de_uma_vez(tmp_path):
    caminho = escrever_csv(tmp_path, [
        "2024-01-05,Cliente A,1,,1,1",
        "2024-01-05,Cliente B,1,1,3,1",
    ])
    with pytest.raises(hs.DadosInvalidosError) as erro:
        hs.carregar_dados(caminho)
    assert "linha 2: 'criativo' está vazio" in str(erro.value)
    assert "linha 3: 'resultado' deve ser 0 ou 1" in str(erro.value)


# --- Semanas seguidas em risco ---

def test_semanas_em_risco_nos_dados_de_exemplo():
    df = hs.gerar_relatorio(hs.carregar_dados(hs.CAMINHO_DADOS))
    ultima = ultima_semana_por_cliente(df)
    assert ultima.loc["Churrascaria Gaúcha", "semanas_em_risco"] == 4
    assert ultima.loc["Pizzaria Bella Napoli", "semanas_em_risco"] == 3
    assert ultima.loc["Hamburgueria Top Burguer", "semanas_em_risco"] == 0
    assert ultima.loc["Restaurante Sabor & Arte", "semanas_em_risco"] == 0


def test_contador_zera_quando_cliente_sai_do_risco(tmp_path):
    df = relatorio_de(tmp_path, [
        "2024-01-05,Cliente A,0,0,0,0",
        "2024-01-12,Cliente A,1,1,1,1",
        "2024-01-19,Cliente A,0,0,0,0",
    ])
    assert df.sort_values("semana")["semanas_em_risco"].tolist() == [1, 0, 1]


def test_contador_e_separado_por_cliente(tmp_path):
    df = relatorio_de(tmp_path, [
        "2024-01-05,Cliente A,0,0,0,0",
        "2024-01-05,Cliente B,1,1,1,1",
        "2024-01-12,Cliente A,0,0,0,0",
        "2024-01-12,Cliente B,0,0,0,0",
    ])
    ultima = ultima_semana_por_cliente(df)
    assert ultima.loc["Cliente A", "semanas_em_risco"] == 2
    assert ultima.loc["Cliente B", "semanas_em_risco"] == 1


def test_descrever_sequencia():
    assert hs.descrever_sequencia(1) == "entrou em risco esta semana"
    assert hs.descrever_sequencia(3) == "3ª semana seguida em risco"


# --- Tendência ---

def test_tendencia_calcula_variacao(tmp_path):
    df = relatorio_de(tmp_path, [
        "2024-01-05,Cliente A,0,0,0,0",
        "2024-01-12,Cliente A,1,1,1,0",
    ])
    comparativo = hs.calcular_tendencia(df)
    assert comparativo.loc["Cliente A", "variacao"] == 80


def test_tendencia_marca_cliente_novo_e_cliente_sem_dados(tmp_path, capsys):
    df = relatorio_de(tmp_path, [
        "2024-01-05,Cliente Antigo,1,1,1,1",
        "2024-01-05,Cliente Sumido,1,1,1,1",
        "2024-01-12,Cliente Antigo,1,1,1,1",
        "2024-01-12,Cliente Novo,0,0,0,0",
    ])
    comparativo = hs.calcular_tendencia(df)
    assert pd.isna(comparativo.loc["Cliente Novo", "health_score_anterior"])
    assert pd.isna(comparativo.loc["Cliente Sumido", "health_score_atual"])

    hs.exibir_tendencia(comparativo)
    saida = capsys.readouterr().out
    assert "Cliente Novo" in saida and "🆕 novo" in saida
    assert "Cliente Sumido" in saida and "sem dados nesta semana" in saida


def test_tendencia_com_uma_semana_so(tmp_path, capsys):
    df = relatorio_de(tmp_path, ["2024-01-05,Cliente A,1,1,1,1"])
    assert hs.calcular_tendencia(df) is None
    hs.exibir_tendencia(None)
    assert "Dados insuficientes" in capsys.readouterr().out


# --- Execução completa ---

def test_main_salva_relatorio_independente_da_pasta_atual(tmp_path, monkeypatch, capsys):
    relatorio = tmp_path / "relatorio.csv"
    monkeypatch.setattr(hs, "CAMINHO_RELATORIO", relatorio)
    outra_pasta = tmp_path / "outra"
    outra_pasta.mkdir()
    monkeypatch.chdir(outra_pasta)

    hs.main()

    salvo = pd.read_csv(relatorio)
    assert {"health_score", "risco", "semanas_em_risco"} <= set(salvo.columns)
    assert "4ª semana seguida em risco" in capsys.readouterr().out


def test_main_com_dados_invalidos_sai_com_erro(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hs, "CAMINHO_DADOS", escrever_csv(tmp_path, ["2024-01-05,Cliente A,1,1,1,"]))
    with pytest.raises(SystemExit) as saida:
        hs.main()
    assert saida.value.code == 1
    assert "'interacao' está vazio" in capsys.readouterr().out


def test_main_sem_arquivo_sai_com_erro(tmp_path, monkeypatch):
    monkeypatch.setattr(hs, "CAMINHO_DADOS", tmp_path / "nao_existe.csv")
    with pytest.raises(SystemExit) as saida:
        hs.main()
    assert saida.value.code == 1
