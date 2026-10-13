"""
gerar_dados.py
--------------
Gera um dataset SIMULADO de clientes de uma agência de marketing, com os mesmos
4 indicadores semanais do health score e o resultado real: se o cliente cancelou
e quando.

Os dados não são reais. Eles seguem comportamentos que observei atuando em
Customer Success, descritos nos parâmetros abaixo:

1. Perfis de cliente
   - estável    : a maioria. Poucos erros, interage no grupo, cancela pouco.
   - silencioso : quase não fala no grupo, mas está satisfeito e raramente cancela.
   - exigente   : pede mais refações, tem mais erros e resultados oscilando. Cancela mais.

2. Antes de cancelar, o cliente passa por uma fase de desgaste de 4 a 10 semanas:
   - some do grupo primeiro (a interação cai logo no começo do desgaste);
   - os resultados pioram;
   - erros operacionais e refações de criativo aumentam aos poucos.

3. Um erro operacional aumenta a chance de o cliente entrar em desgaste nas semanas seguintes.

4. Parte dos desgastes é revertida: o time age e o cliente fica.

5. Parte dos cancelamentos é abrupta (corte de verba, venda do negócio) e não dá sinal nenhum.

6. Nem todo cliente está na carteira desde janeiro: alguns entram ao longo do ano.

Formato da saída (uma linha por cliente por semana em que ele estava ativo):
    semana, cliente, operacional, criativo, resultado, interacao, cancelou, data_cancelamento

- `cancelou` vale 1 em todas as linhas de quem cancelou durante o período.
- `data_cancelamento` fica vazia para quem não cancelou. Depois do cancelamento,
  o cliente não aparece mais.

Uso:
    python src/gerar_dados.py
"""

from pathlib import Path

import numpy as np
import pandas as pd


RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_SINTETICO = RAIZ / "data" / "clientes_sinteticos.csv"

INDICADORES = ["operacional", "criativo", "resultado", "interacao"]

# --- Tamanho do dataset ---
SEMENTE         = 42
N_CLIENTES      = 200
N_SEMANAS       = 52
PRIMEIRA_SEMANA = pd.Timestamp("2024-01-05")  # relatório sai toda sexta-feira

# --- Perfis: proporção na carteira, chance de cada indicador estar OK numa semana normal
#     e multiplicador do risco de entrar em desgaste ---
PERFIS = {
    "estavel": {
        "proporcao": 0.70,
        "ok": {"operacional": 0.93, "criativo": 0.85, "resultado": 0.75, "interacao": 0.85},
        "risco": 1.0,
    },
    "silencioso": {
        "proporcao": 0.12,
        "ok": {"operacional": 0.93, "criativo": 0.88, "resultado": 0.75, "interacao": 0.30},
        "risco": 0.5,
    },
    "exigente": {
        "proporcao": 0.18,
        "ok": {"operacional": 0.85, "criativo": 0.65, "resultado": 0.65, "interacao": 0.85},
        "risco": 2.0,
    },
}

# --- Desgaste antes do cancelamento ---
DURACAO_DESGASTE = (4, 10)  # semanas (mínimo e máximo)

# Chance de cada indicador estar OK no pior momento do desgaste
OK_NO_DESGASTE = {"operacional": 0.70, "criativo": 0.60, "resultado": 0.30, "interacao": 0.10}

# Em que ponto do desgaste cada indicador chega ao pior nível (1.0 = só no final).
# A interação despenca primeiro: o cliente some do grupo antes de reclamar.
PONTO_DE_QUEDA = {"operacional": 1.0, "criativo": 1.0, "resultado": 0.8, "interacao": 0.4}

RISCO_SEMANAL_DESGASTE  = 0.0075  # chance base, por semana, de um cliente entrar em desgaste
MULTIPLICADOR_APOS_ERRO = 2.5     # erro operacional na semana atual ou anterior multiplica esse risco
CHANCE_RECUPERACAO      = 0.25    # fração dos desgastes que o time consegue reverter
RISCO_SEMANAL_ABRUPTO   = 0.0012  # cancelamento sem aviso

# --- Entrada de clientes ---
PROPORCAO_DESDE_O_INICIO = 0.80   # o resto entra em uma semana aleatória
ULTIMA_SEMANA_DE_ENTRADA = 39


def _chance_ok(perfil, indicador, progresso_desgaste):
    """Chance de o indicador estar OK. progresso_desgaste = 0 fora do desgaste, até 1 no final."""
    base = PERFIS[perfil]["ok"][indicador]
    if progresso_desgaste <= 0:
        return base
    queda = min(1.0, progresso_desgaste / PONTO_DE_QUEDA[indicador])
    return base + (OK_NO_DESGASTE[indicador] - base) * queda


def _simular_cliente(rng, nome, perfil, semana_inicio, semanas):
    """Simula as semanas de um cliente. Retorna (linhas, data_cancelamento, tipo_cancelamento)."""
    linhas = []
    erro_semana_passada = False
    em_desgaste = False
    semanas_no_desgaste = duracao = semana_recuperacao = 0

    for k in range(semana_inicio, len(semanas)):
        # 1) O cliente cancela durante a semana k? Se sim, ele não aparece mais a partir dela.
        tipo = None
        if em_desgaste and semana_recuperacao == 0 and semanas_no_desgaste == duracao:
            tipo = "desgaste"
        elif not em_desgaste and k > semana_inicio and rng.random() < RISCO_SEMANAL_ABRUPTO:
            tipo = "abrupto"
        if tipo:
            data_cancelamento = semanas[k] - pd.Timedelta(days=int(rng.integers(0, 7)))
            return linhas, data_cancelamento, tipo

        # 2) Indicadores da semana k
        progresso = (semanas_no_desgaste + 1) / duracao if em_desgaste else 0
        linha = {"semana": semanas[k], "cliente": nome}
        for indicador in INDICADORES:
            linha[indicador] = int(rng.random() < _chance_ok(perfil, indicador, progresso))
        linhas.append(linha)

        # 3) Transições para a próxima semana
        if em_desgaste:
            semanas_no_desgaste += 1
            if semana_recuperacao and semanas_no_desgaste == semana_recuperacao:
                em_desgaste = False
        else:
            teve_erro = linha["operacional"] == 0 or erro_semana_passada
            risco = RISCO_SEMANAL_DESGASTE * PERFIS[perfil]["risco"]
            if teve_erro:
                risco *= MULTIPLICADOR_APOS_ERRO
            if rng.random() < risco:
                em_desgaste = True
                semanas_no_desgaste = 0
                duracao = int(rng.integers(DURACAO_DESGASTE[0], DURACAO_DESGASTE[1] + 1))
                recupera = rng.random() < CHANCE_RECUPERACAO
                semana_recuperacao = int(rng.integers(2, duracao)) if recupera else 0
        erro_semana_passada = linha["operacional"] == 0

    return linhas, pd.NaT, None


def gerar_dados(n_clientes=N_CLIENTES, n_semanas=N_SEMANAS, semente=SEMENTE, incluir_ocultas=False):
    """
    Gera o dataset simulado. Com a mesma semente, o resultado é sempre o mesmo.

    incluir_ocultas=True adiciona as colunas `perfil` e `tipo_cancelamento`, que existem só
    na simulação (na vida real ninguém sabe o perfil "verdadeiro" do cliente). Elas servem
    para explicar os resultados, nunca para treinar modelos.
    """
    rng = np.random.default_rng(semente)
    semanas = [PRIMEIRA_SEMANA + pd.Timedelta(weeks=k) for k in range(n_semanas)]
    nomes_perfis = list(PERFIS)
    proporcoes = [PERFIS[p]["proporcao"] for p in nomes_perfis]

    registros = []
    for i in range(1, n_clientes + 1):
        nome = f"Cliente {i:03d}"
        perfil = str(rng.choice(nomes_perfis, p=proporcoes))
        if rng.random() < PROPORCAO_DESDE_O_INICIO:
            semana_inicio = 0
        else:
            semana_inicio = int(rng.integers(1, min(ULTIMA_SEMANA_DE_ENTRADA, n_semanas - 1) + 1))

        linhas, data_cancelamento, tipo = _simular_cliente(rng, nome, perfil, semana_inicio, semanas)
        for linha in linhas:
            linha["cancelou"] = int(tipo is not None)
            linha["data_cancelamento"] = data_cancelamento
            if incluir_ocultas:
                linha["perfil"] = perfil
                linha["tipo_cancelamento"] = tipo or ""
        registros.extend(linhas)

    df = pd.DataFrame(registros)
    df["data_cancelamento"] = pd.to_datetime(df["data_cancelamento"])
    return df


def salvar_csv(df, caminho=CAMINHO_SINTETICO):
    saida = df.copy()
    saida["semana"] = saida["semana"].dt.strftime("%Y-%m-%d")
    saida["data_cancelamento"] = saida["data_cancelamento"].dt.strftime("%Y-%m-%d").fillna("")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    saida.to_csv(caminho, index=False)


def resumir(df):
    clientes = df.groupby("cliente").agg(cancelou=("cancelou", "first"), tipo=("tipo_cancelamento", "first"))
    return {
        "linhas": len(df),
        "clientes": len(clientes),
        "semanas": df["semana"].nunique(),
        "cancelaram": int(clientes["cancelou"].sum()),
        "cancelamentos_abruptos": int((clientes["tipo"] == "abrupto").sum()),
    }


def main():
    df = gerar_dados(incluir_ocultas=True)
    resumo = resumir(df)
    salvar_csv(df.drop(columns=["perfil", "tipo_cancelamento"]))

    print(f"✅ Dataset simulado salvo em: {CAMINHO_SINTETICO}")
    print(f"   {resumo['clientes']} clientes, {resumo['semanas']} semanas, {resumo['linhas']} linhas")
    print(f"   {resumo['cancelaram']} cancelaram ({resumo['cancelaram'] / resumo['clientes']:.0%}),"
          f" sendo {resumo['cancelamentos_abruptos']} sem nenhum sinal antes")


if __name__ == "__main__":
    main()
