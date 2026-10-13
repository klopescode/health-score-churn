"""
modelos.py
----------
Compara a regra manual do health score com modelos de machine learning na tarefa
"o cliente vai cancelar nas próximas 4 semanas?".

Como a comparação é feita:

1. Validação temporal. As últimas 32 semanas observáveis são divididas em 4 blocos de
   8 semanas. Cada bloco é previsto por modelos treinados só com as semanas anteriores a
   ele, como seria na prática: o modelo aprende com o passado e é usado no futuro.
   Uma linha de treino só entra se a janela de 4 semanas do alvo dela termina antes do
   início do bloco, para que o treino não "veja" cancelamentos do período de teste.
   As métricas juntam as previsões dos 4 blocos.

2. Métrica principal: recall. Deixar passar um cliente que vai sair custa mais que um
   alarme falso. Também medimos precisão, AUC, quantos clientes que cancelaram foram
   avisados pelo menos uma vez a tempo e quantos alertas o time recebe por semana.

3. Pontos de operação. Cada método gera uma pontuação de risco, e o limiar de alerta é
   escolhido no treino (com validação cruzada por cliente, no caso dos modelos) de dois jeitos:
   - "mesmo volume": o mesmo número médio de alertas por semana que a regra atual
     (score < 50) gera hoje. Responde: com o mesmo trabalho para o time, quem avisa mais?
   - "recall 80%": o limiar mais alto que ainda avisa 80% das semanas que antecedem um
     cancelamento. Responde: quanto custa, em alertas, priorizar o recall?

4. Pesos recalibrados. Uma regressão logística com só os 4 indicadores da semana mostra
   quanto cada um pesa no risco. Os coeficientes viram pesos que somam 100.

Uso:
    python src/modelos.py
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from features import ALVO, FEATURES_MODELO, HORIZONTE_SEMANAS, INDICADORES, preparar_base
from health_score import LIMITE_ATENCAO, LIMITE_SAUDAVEL, PASTA_SAIDAS, PESOS


META_RECALL       = 0.80
BLOCOS_TESTE      = 4
SEMANAS_POR_BLOCO = 8
SEMENTE           = 42

MESMO_VOLUME = "mesmo volume"
RECALL_META  = "recall 80%"

REGRA_ATUAL       = "Regra atual"
REGRA_RECALIBRADA = "Regra recalibrada"


# --- Divisão treino/teste ---
def dividir_treino_teste(base, inicio_teste, fim_teste=None, horizonte=HORIZONTE_SEMANAS):
    """
    Teste: semanas em [inicio_teste, fim_teste). Treino: semanas cuja janela do alvo
    (as `horizonte` semanas seguintes) termina até o início do teste.
    Linhas sem a janela do alvo completa no dataset ficam de fora dos dois.
    """
    observada = base[base["janela_observada"]]
    no_teste = observada["semana"] >= inicio_teste
    if fim_teste is not None:
        no_teste &= observada["semana"] < fim_teste
    teste = observada[no_teste]
    treino = observada[observada["semana"] + pd.Timedelta(weeks=horizonte) <= inicio_teste]
    return treino.copy(), teste.copy()


def blocos_temporais(base, n_blocos=BLOCOS_TESTE, semanas_por_bloco=SEMANAS_POR_BLOCO,
                     horizonte=HORIZONTE_SEMANAS):
    """Divide as últimas n_blocos * semanas_por_bloco semanas observáveis em blocos de teste."""
    semanas = sorted(base.loc[base["janela_observada"], "semana"].unique())
    if n_blocos * semanas_por_bloco >= len(semanas):
        raise ValueError("Poucas semanas observáveis para essa quantidade de blocos de teste.")
    blocos = []
    for i in range(n_blocos, 0, -1):
        inicio = semanas[-i * semanas_por_bloco]
        fim = inicio + pd.Timedelta(weeks=semanas_por_bloco)
        blocos.append(dividir_treino_teste(base, inicio, fim, horizonte))
    return blocos


# --- Métricas ---
def avaliar(teste, alerta, risco):
    """
    teste : linhas avaliadas (com o alvo, o cliente e a semana).
    alerta: 1 quando o método avisaria o time sobre o cliente naquela semana.
    risco : pontuação contínua (quanto maior, mais risco), usada na AUC.
    """
    y = teste[ALVO].to_numpy()
    alerta = np.asarray(alerta).astype(int)

    # Por cliente: dos que cancelaram, quantos receberam pelo menos 1 alerta
    # nas 4 semanas anteriores ao cancelamento
    positivos = teste.assign(alerta=alerta)[y == 1]
    avisados = positivos.groupby("cliente")["alerta"].max()

    return {
        "Recall": recall_score(y, alerta, zero_division=0),
        "Precisão": precision_score(y, alerta, zero_division=0),
        "AUC": roc_auc_score(y, risco),
        "Clientes avisados a tempo": avisados.mean() if len(avisados) else np.nan,
        "Alertas por semana": alerta.sum() / teste["semana"].nunique(),
    }


# --- Escolha do limiar ---
def limiar_para_recall(y, risco, meta_recall=META_RECALL):
    """Maior limiar de risco que ainda alcança a meta de recall."""
    _, recall, limiares = precision_recall_curve(y, risco)
    atingem = limiares[recall[:-1] >= meta_recall]
    return atingem.max() if len(atingem) else limiares.min()


def limiar_para_volume(risco, n_semanas, alertas_por_semana):
    """Menor limiar de risco que gera no máximo `alertas_por_semana` alertas, em média."""
    risco = np.asarray(risco, dtype=float)
    maximo = int(np.floor(alertas_por_semana * n_semanas))
    for limiar in np.sort(np.unique(risco)):
        if (risco >= limiar).sum() <= maximo:
            return limiar
    return np.inf


def alertas_por_semana_da_regra(df, corte=LIMITE_ATENCAO):
    return (df["health_score"] < corte).sum() / df["semana"].nunique()


# --- Regra manual ---
def score_com_pesos(df, pesos):
    return sum(df[indicador] * peso for indicador, peso in pesos.items())


def recalibrar_pesos(treino):
    """
    Treina uma regressão logística só com os 4 indicadores da semana e transforma os
    coeficientes em pesos que somam 100, no mesmo formato da regra atual.
    Como 1 = indicador OK, um coeficiente negativo significa "reduz o risco de cancelar":
    quanto mais negativo, mais o indicador protege e maior o peso dele.
    """
    modelo = LogisticRegression(class_weight="balanced", max_iter=1000)
    modelo.fit(treino[INDICADORES], treino[ALVO])
    coeficientes = pd.Series(modelo.coef_[0], index=INDICADORES)
    protecao = (-coeficientes).clip(lower=0)
    return arredondar_pesos(protecao / protecao.sum() * 100), coeficientes


def arredondar_pesos(pesos, passo=5):
    """Arredonda para múltiplos de `passo` mantendo a soma em 100 (maiores restos primeiro)."""
    base = (pesos // passo) * passo
    falta = int(round((100 - base.sum()) / passo))
    restos = (pesos - base).sort_values(ascending=False)
    for indicador in restos.index[:falta]:
        base[indicador] += passo
    return {indicador: int(base[indicador]) for indicador in pesos.index}


# --- Modelos ---
def criar_modelos():
    return {
        "Regressão logística": make_pipeline(
            StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000)
        ),
        "Árvore de decisão": DecisionTreeClassifier(
            max_depth=4, min_samples_leaf=30, class_weight="balanced", random_state=SEMENTE
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=200, min_samples_leaf=10, class_weight="balanced_subsample",
            random_state=SEMENTE, n_jobs=-1,
        ),
    }


def risco_fora_da_amostra(modelo, treino, features=FEATURES_MODELO):
    """Probabilidades do treino via validação cruzada por cliente (sem o modelo ver a própria linha)."""
    return cross_val_predict(
        modelo, treino[features], treino[ALVO],
        groups=treino["cliente"], cv=GroupKFold(n_splits=5), method="predict_proba",
    )[:, 1]


def limiares_do_treino(treino, risco_treino, meta_recall=META_RECALL):
    """Limiar de cada ponto de operação, calculado só com o treino."""
    return {
        MESMO_VOLUME: limiar_para_volume(
            risco_treino, treino["semana"].nunique(), alertas_por_semana_da_regra(treino)
        ),
        RECALL_META: limiar_para_recall(treino[ALVO], risco_treino, meta_recall),
    }


def treinar_modelo(nome, treino, meta_recall=META_RECALL):
    """Treina um dos modelos de criar_modelos() e calcula os limiares de alerta no próprio treino."""
    modelo = criar_modelos()[nome]
    limiares = limiares_do_treino(treino, risco_fora_da_amostra(modelo, treino), meta_recall)
    modelo.fit(treino[FEATURES_MODELO], treino[ALVO])
    return modelo, limiares


def treinar_modelo_final(base, nome="Regressão logística", meta_recall=META_RECALL):
    """Modelo para usar no dia a dia: treinado com todas as semanas que já têm o alvo conhecido."""
    return treinar_modelo(nome, base[base["janela_observada"]], meta_recall)


# --- Comparação completa ---
def _prever_bloco(treino, teste, meta_recall):
    """Para cada método: (risco no teste, limiares calculados no treino)."""
    previsoes = {}

    pesos_novos, _ = recalibrar_pesos(treino)
    regras = {
        REGRA_ATUAL: PESOS,
        REGRA_RECALIBRADA: pesos_novos,
    }
    for nome, pesos in regras.items():
        risco_treino = 100 - score_com_pesos(treino, pesos)
        risco_teste = 100 - score_com_pesos(teste, pesos)
        previsoes[nome] = (risco_teste, limiares_do_treino(treino, risco_treino, meta_recall))

    for nome in criar_modelos():
        modelo, limiares = treinar_modelo(nome, treino, meta_recall)
        previsoes[nome] = (modelo.predict_proba(teste[FEATURES_MODELO])[:, 1], limiares)

    return previsoes


def comparar_metodos(base, meta_recall=META_RECALL, n_blocos=BLOCOS_TESTE,
                     semanas_por_bloco=SEMANAS_POR_BLOCO):
    """
    Retorna (tabelas, detalhes).
    tabelas : {ponto de operação: tabela com uma linha por método}. Cada tabela começa
              com a regra atual do jeito que é usada hoje (corte < 50 ou < 80).
    detalhes: blocos usados, risco e alertas de cada método e pesos recalibrados com todos os dados.
    """
    blocos = blocos_temporais(base, n_blocos, semanas_por_bloco)
    testes, risco, alerta = [], {}, {}
    for treino, teste in blocos:
        testes.append(teste)
        for nome, (risco_bloco, limiares) in _prever_bloco(treino, teste, meta_recall).items():
            risco_bloco = np.asarray(risco_bloco, dtype=float)
            risco.setdefault(nome, []).append(risco_bloco)
            for ponto, limiar in limiares.items():
                alerta.setdefault((ponto, nome), []).append((risco_bloco >= limiar).astype(int))

    teste = pd.concat(testes)
    risco = {nome: np.concatenate(valores) for nome, valores in risco.items()}
    alerta = {chave: np.concatenate(valores) for chave, valores in alerta.items()}

    # Cada tabela começa com a regra atual do jeito que é usada hoje: o corte < 50 (risco alto)
    # é a referência de volume; o corte < 80 (atenção ou risco) é o jeito atual de ter mais recall.
    # No "mesmo volume", a regra atual com limiar ajustado é igual ao corte < 50, então não repete.
    cortes_de_hoje = {MESMO_VOLUME: LIMITE_ATENCAO, RECALL_META: LIMITE_SAUDAVEL}
    tabelas = {}
    for ponto, corte in cortes_de_hoje.items():
        linhas = {
            f"{REGRA_ATUAL} (score < {corte})":
                avaliar(teste, teste["health_score"] < corte, risco[REGRA_ATUAL])
        }
        for nome in risco:
            if ponto == MESMO_VOLUME and nome == REGRA_ATUAL:
                continue
            linhas[f"{nome}, {ponto}"] = avaliar(teste, alerta[(ponto, nome)], risco[nome])
        tabela = pd.DataFrame(linhas).T
        tabela.index.name = "Método"
        tabelas[ponto] = tabela

    pesos_novos, coeficientes = recalibrar_pesos(base[base["janela_observada"]])
    detalhes = {
        "blocos": blocos,
        "teste": teste,
        "risco": risco,
        "alerta": alerta,
        "pesos_recalibrados": pesos_novos,
        "coeficientes": coeficientes,
    }
    return tabelas, detalhes


def formatar_tabela(tabela):
    """Tabela em Markdown, com porcentagens, pronta para colar no README."""
    colunas = list(tabela.columns)
    linhas = ["| Método | " + " | ".join(colunas) + " |", "|---|" + "---:|" * len(colunas)]
    for metodo, row in tabela.iterrows():
        valores = []
        for coluna in colunas:
            if coluna == "AUC":
                valores.append(f"{row[coluna]:.2f}")
            elif coluna == "Alertas por semana":
                valores.append(f"{row[coluna]:.1f}")
            else:
                valores.append(f"{row[coluna]:.0%}")
        linhas.append(f"| {metodo} | " + " | ".join(valores) + " |")
    return "\n".join(linhas)


def main():
    base = preparar_base()
    tabelas, detalhes = comparar_metodos(base)
    teste = detalhes["teste"]

    print("\nBlocos de teste (cada um previsto com modelos treinados só no passado):")
    for treino_bloco, teste_bloco in detalhes["blocos"]:
        print(f"  treino até {treino_bloco['semana'].max().date()} ({len(treino_bloco)} linhas) → "
              f"teste {teste_bloco['semana'].min().date()} a {teste_bloco['semana'].max().date()} "
              f"({teste_bloco[ALVO].sum()} linhas positivas)")
    print(f"Total no teste: {len(teste)} linhas, {teste[ALVO].sum()} positivas, "
          f"{teste.loc[teste[ALVO] == 1, 'cliente'].nunique()} clientes que cancelaram")

    PASTA_SAIDAS.mkdir(parents=True, exist_ok=True)
    titulos = {
        MESMO_VOLUME: "Com o mesmo volume de alertas que a regra atual gera hoje",
        RECALL_META: f"Com o limiar ajustado para recall de {META_RECALL:.0%}",
    }
    for ponto, tabela in tabelas.items():
        print(f"\n{titulos[ponto]}:\n")
        print(formatar_tabela(tabela))
        nome_arquivo = "comparacao_" + ponto.replace(" ", "_").replace("%", "") + ".csv"
        tabela.to_csv(PASTA_SAIDAS / nome_arquivo)

    pesos_atuais = "/".join(str(p) for p in PESOS.values())
    pesos_novos = "/".join(str(p) for p in detalhes["pesos_recalibrados"].values())
    print(f"\nPesos ({'/'.join(INDICADORES)}): intuição {pesos_atuais} → dados {pesos_novos}"
          " (regressão logística com todas as semanas observáveis)")
    print(f"\n💾 Tabelas salvas em: {PASTA_SAIDAS}\n")


if __name__ == "__main__":
    main()
