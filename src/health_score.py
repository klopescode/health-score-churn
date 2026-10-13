"""
health_score.py
---------------
Sistema de monitoramento de risco de churn para clientes de marketing.

Calcula o health score semanal de cada cliente com base em 4 indicadores:
- Operacional: se houve erro operacional na semana (0 = erro, 1 = ok)
- Criativo: se houve necessidade de refazer criativos (0 = refez, 1 = ok)
- Resultado: se a semana teve resultado positivo (0 = não, 1 = sim)
- Interacao: se o cliente interagiu no grupo (0 = não interagiu, 1 = interagiu)

Pontuação por indicador:
- Operacional : 30 pontos
- Criativo    : 20 pontos
- Resultado   : 30 pontos
- Interação   : 20 pontos
Total máximo  : 100 pontos

Classificação de risco:
- 80 a 100 : Saudável   🟢
- 50 a 79  : Atenção    🟡
- 0 a 49   : Risco Alto 🔴
"""

import argparse
import sys
from pathlib import Path

import pandas as pd


# --- Caminhos (relativos à raiz do projeto, para rodar de qualquer lugar) ---
RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_DADOS     = RAIZ / "data" / "dados_clientes.csv"
PASTA_SAIDAS      = RAIZ / "saidas"
CAMINHO_RELATORIO = PASTA_SAIDAS / "relatorio_health_score.csv"

# --- Configurações de pontuação ---
PESOS = {
    "operacional": 30,
    "criativo":    20,
    "resultado":   30,
    "interacao":   20,
}

# --- Limites de classificação (usados também pelo relatorio_email.py) ---
LIMITE_SAUDAVEL = 80  # a partir daqui o cliente é saudável
LIMITE_ATENCAO  = 50  # abaixo daqui o cliente está em risco alto

COLUNAS_OBRIGATORIAS = ["semana", "cliente", *PESOS]


class DadosInvalidosError(Exception):
    """Erro nos dados lidos de um CSV (entrada ou relatório)."""


# --- Classificação de risco ---
def classificar_risco(score):
    if score >= LIMITE_SAUDAVEL:
        return "🟢 Saudável"
    elif score >= LIMITE_ATENCAO:
        return "🟡 Atenção"
    else:
        return "🔴 Risco Alto"


# --- Cálculo do health score ---
def calcular_health_score(row):
    score = 0
    for coluna, peso in PESOS.items():
        score += row[coluna] * peso
    return score


# --- Validação dos dados ---
def validar_dados(df):
    """
    Confere o CSV antes do cálculo e junta todos os problemas numa mensagem só,
    indicando a linha do arquivo, para facilitar a correção na planilha.
    """
    faltando = [coluna for coluna in COLUNAS_OBRIGATORIAS if coluna not in df.columns]
    if faltando:
        raise DadosInvalidosError(f"Colunas ausentes no CSV: {', '.join(faltando)}")

    if df.empty:
        raise DadosInvalidosError("O CSV não tem nenhuma linha de dados.")

    erros = []
    datas = pd.to_datetime(df["semana"], format="%Y-%m-%d", errors="coerce")

    for indice, row in df.iterrows():
        linha = indice + 2  # +1 do cabeçalho, +1 porque o arquivo começa na linha 1

        if row["semana"] == "":
            erros.append(f"linha {linha}: 'semana' está vazia")
        elif pd.isna(datas[indice]):
            erros.append(f"linha {linha}: data inválida '{row['semana']}' (use o formato AAAA-MM-DD)")

        if row["cliente"] == "":
            erros.append(f"linha {linha}: 'cliente' está vazio")

        for coluna in PESOS:
            valor = row[coluna]
            if valor == "":
                erros.append(f"linha {linha}: '{coluna}' está vazio")
            elif valor not in ("0", "1"):
                erros.append(f"linha {linha}: '{coluna}' deve ser 0 ou 1, mas está '{valor}'")

    preenchidos = (df["semana"] != "") & (df["cliente"] != "")
    repetidos = df[df.duplicated(["semana", "cliente"], keep=False) & preenchidos]
    for (semana, cliente), grupo in repetidos.groupby(["semana", "cliente"]):
        linhas = ", ".join(str(indice + 2) for indice in grupo.index)
        erros.append(f"linhas {linhas}: '{cliente}' aparece mais de uma vez na semana {semana}")

    if erros:
        raise DadosInvalidosError("Problemas encontrados no CSV:\n  - " + "\n  - ".join(erros))


# --- Leitura dos dados ---
def carregar_dados(caminho_csv=CAMINHO_DADOS):
    try:
        # Lê tudo como texto para conseguir validar células vazias e valores digitados errado
        df = pd.read_csv(caminho_csv, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        raise DadosInvalidosError(f"O arquivo {caminho_csv} está vazio.")

    for coluna in df.columns:
        df[coluna] = df[coluna].str.strip()

    validar_dados(df)

    df["semana"] = pd.to_datetime(df["semana"], format="%Y-%m-%d")
    for coluna in PESOS:
        df[coluna] = df[coluna].astype(int)
    return df


# --- Semanas seguidas em risco ---
def contar_semanas_em_risco(df):
    """
    Conta há quantas semanas seguidas cada cliente está em risco alto,
    considerando as semanas em que o cliente aparece no CSV.
    O contador volta para 0 quando o cliente sai do risco.
    """
    contagem = {}
    sequencias = {}
    for indice, row in df.sort_values(["cliente", "semana"]).iterrows():
        cliente = row["cliente"]
        if row["health_score"] < LIMITE_ATENCAO:
            contagem[cliente] = contagem.get(cliente, 0) + 1
        else:
            contagem[cliente] = 0
        sequencias[indice] = contagem[cliente]
    return pd.Series(sequencias).reindex(df.index)


# --- Relatório semanal ---
def gerar_relatorio(df):
    df["health_score"] = df.apply(calcular_health_score, axis=1)
    df["risco"] = df["health_score"].apply(classificar_risco)
    df["semanas_em_risco"] = contar_semanas_em_risco(df)
    return df


# --- Tendência: compara última semana com a anterior ---
def calcular_tendencia(df):
    """
    Retorna um DataFrame indexado por cliente com o score atual, o anterior e a variação.
    Clientes novos ficam sem score anterior; clientes sem dados na última semana ficam sem score atual.
    Retorna None se houver menos de duas semanas.
    """
    semanas = sorted(df["semana"].unique())

    if len(semanas) < 2:
        return None

    semana_atual    = semanas[-1]
    semana_anterior = semanas[-2]

    atual    = df[df["semana"] == semana_atual][["cliente", "health_score"]].set_index("cliente")
    anterior = df[df["semana"] == semana_anterior][["cliente", "health_score"]].set_index("cliente")

    comparativo = atual.join(anterior, how="outer", lsuffix="_atual", rsuffix="_anterior")
    comparativo["variacao"] = comparativo["health_score_atual"] - comparativo["health_score_anterior"]
    comparativo.attrs["semana_atual"]    = semana_atual
    comparativo.attrs["semana_anterior"] = semana_anterior
    return comparativo


def exibir_tendencia(comparativo):
    if comparativo is None:
        print("⚠️  Dados insuficientes para análise de tendência.")
        return

    semana_anterior = comparativo.attrs["semana_anterior"]
    semana_atual    = comparativo.attrs["semana_atual"]

    print("\n" + "="*55)
    print(f"📊 COMPARATIVO: {semana_anterior.date()} → {semana_atual.date()}")
    print("="*55)

    for cliente, row in comparativo.iterrows():
        if pd.isna(row["health_score_anterior"]):
            sinal = "🆕 novo (sem semana anterior)"
        elif pd.isna(row["health_score_atual"]):
            sinal = "⚠️  sem dados nesta semana"
        elif row["variacao"] > 0:
            sinal = f"▲ +{int(row['variacao'])}"
        elif row["variacao"] < 0:
            sinal = f"▼ {int(row['variacao'])}"
        else:
            sinal = "→  0"
        print(f"  {cliente:<35} {sinal}")


# --- Exibição do relatório da última semana ---
def descrever_sequencia(semanas):
    if semanas <= 1:
        return "entrou em risco esta semana"
    return f"{int(semanas)}ª semana seguida em risco"


def exibir_ultima_semana(df):
    ultima_semana = df["semana"].max()
    recorte = df[df["semana"] == ultima_semana].sort_values("health_score")

    print("\n" + "="*55)
    print(f"📋 HEALTH SCORE — Semana: {ultima_semana.date()}")
    print("="*55)

    for _, row in recorte.iterrows():
        print(f"  {row['cliente']:<35} {int(row['health_score']):>3} pts  {row['risco']}")

    # Clientes em risco, do que está há mais tempo para o mais recente
    em_risco = recorte[recorte["health_score"] < LIMITE_ATENCAO].sort_values(
        ["semanas_em_risco", "health_score"], ascending=[False, True]
    )
    if not em_risco.empty:
        print("\n🚨 AÇÃO NECESSÁRIA — Clientes em risco alto:")
        for _, row in em_risco.iterrows():
            print(f"   → {row['cliente']} ({int(row['health_score'])} pts) — {descrever_sequencia(row['semanas_em_risco'])}")
    else:
        print("\n✅ Nenhum cliente em risco alto esta semana.")


# --- Main ---
def main(argv=None):
    parser = argparse.ArgumentParser(description="Calcula o health score semanal de cada cliente.")
    parser.add_argument(
        "dados", nargs="?", type=Path,
        help="CSV com os indicadores semanais (padrão: data/dados_clientes.csv)",
    )
    caminho_dados = parser.parse_args(argv).dados or CAMINHO_DADOS

    print("\n🔍 Carregando dados...")
    try:
        df = carregar_dados(caminho_dados)
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {caminho_dados}")
        sys.exit(1)
    except DadosInvalidosError as e:
        print(f"❌ {e}")
        sys.exit(1)

    print("⚙️  Calculando health scores...")
    df = gerar_relatorio(df)

    exibir_ultima_semana(df)
    exibir_tendencia(calcular_tendencia(df))

    # Salva relatório completo em CSV
    CAMINHO_RELATORIO.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CAMINHO_RELATORIO, index=False)
    print(f"\n💾 Relatório salvo em: {CAMINHO_RELATORIO}\n")


if __name__ == "__main__":
    main()
