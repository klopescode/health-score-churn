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

import pandas as pd


# --- Configurações de pontuação ---
PESOS = {
    "operacional": 30,
    "criativo":    20,
    "resultado":   30,
    "interacao":   20,
}

# --- Classificação de risco ---
def classificar_risco(score):
    if score >= 80:
        return "🟢 Saudável"
    elif score >= 50:
        return "🟡 Atenção"
    else:
        return "🔴 Risco Alto"


# --- Cálculo do health score ---
def calcular_health_score(row):
    score = 0
    for coluna, peso in PESOS.items():
        score += row[coluna] * peso
    return score


# --- Leitura dos dados ---
def carregar_dados(caminho_csv):
    df = pd.read_csv(caminho_csv)
    df["semana"] = pd.to_datetime(df["semana"])
    return df


# --- Relatório semanal ---
def gerar_relatorio(df):
    df["health_score"] = df.apply(calcular_health_score, axis=1)
    df["risco"] = df["health_score"].apply(classificar_risco)
    return df


# --- Tendência: compara última semana com a anterior ---
def analisar_tendencia(df):
    semanas = sorted(df["semana"].unique())

    if len(semanas) < 2:
        print("⚠️  Dados insuficientes para análise de tendência.")
        return

    semana_atual   = semanas[-1]
    semana_anterior = semanas[-2]

    atual    = df[df["semana"] == semana_atual][["cliente", "health_score"]].set_index("cliente")
    anterior = df[df["semana"] == semana_anterior][["cliente", "health_score"]].set_index("cliente")

    comparativo = atual.join(anterior, lsuffix="_atual", rsuffix="_anterior")
    comparativo["variacao"] = comparativo["health_score_atual"] - comparativo["health_score_anterior"]

    print("\n" + "="*55)
    print(f"📊 COMPARATIVO: {semana_anterior.date()} → {semana_atual.date()}")
    print("="*55)

    for cliente, row in comparativo.iterrows():
        variacao = row["variacao"]
        if variacao > 0:
            sinal = f"▲ +{int(variacao)}"
        elif variacao < 0:
            sinal = f"▼ {int(variacao)}"
        else:
            sinal = "→  0"
        print(f"  {cliente:<35} {sinal}")


# --- Exibição do relatório da última semana ---
def exibir_ultima_semana(df):
    ultima_semana = df["semana"].max()
    recorte = df[df["semana"] == ultima_semana].sort_values("health_score")

    print("\n" + "="*55)
    print(f"📋 HEALTH SCORE — Semana: {ultima_semana.date()}")
    print("="*55)

    for _, row in recorte.iterrows():
        print(f"  {row['cliente']:<35} {int(row['health_score']):>3} pts  {row['risco']}")

    # Clientes em risco
    em_risco = recorte[recorte["health_score"] < 50]
    if not em_risco.empty:
        print("\n🚨 AÇÃO NECESSÁRIA — Clientes em risco alto:")
        for _, row in em_risco.iterrows():
            print(f"   → {row['cliente']} ({int(row['health_score'])} pts)")
    else:
        print("\n✅ Nenhum cliente em risco alto esta semana.")


# --- Main ---
def main():
    print("\n🔍 Carregando dados...")
    df = carregar_dados("dados_clientes.csv")

    print("⚙️  Calculando health scores...")
    df = gerar_relatorio(df)

    exibir_ultima_semana(df)
    analisar_tendencia(df)

    # Salva relatório completo em CSV
    df.to_csv("relatorio_health_score.csv", index=False)
    print("\n💾 Relatório salvo em: relatorio_health_score.csv\n")


if __name__ == "__main__":
    main()
