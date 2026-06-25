# 📊 Health Score — Monitoramento de Risco de Churn

Sistema de monitoramento semanal de saúde de clientes, desenvolvido para antecipar riscos de churn em agências de marketing.

---

## 💡 Contexto

Em agências que atendem múltiplos clientes simultaneamente, identificar sinais de insatisfação antes do cancelamento é essencial. Este projeto automatiza o cálculo de um **health score semanal** com base em indicadores comportamentais, permitindo que o time de CS atue de forma proativa.

---

## ⚙️ Como funciona

A cada semana, os dados dos clientes são registrados em um CSV com 4 indicadores:

| Indicador    | Descrição                                      | Pontuação |
|--------------|------------------------------------------------|-----------|
| Operacional  | Ocorrência de erros operacionais               | 30 pts    |
| Criativo     | Necessidade de refazer criativos               | 20 pts    |
| Resultado    | Semana com resultado positivo                  | 30 pts    |
| Interação    | Cliente ativo no grupo de comunicação          | 20 pts    |

**Score máximo: 100 pontos**

### Classificação de risco

| Score     | Status       |
|-----------|--------------|
| 80 – 100  | 🟢 Saudável  |
| 50 – 79   | 🟡 Atenção   |
| 0 – 49    | 🔴 Risco Alto |

---

## 🚀 Como usar

### 1. Clone o repositório
```bash
git clone https://github.com/klopescode/health-score-churn.git
cd health-score-churn
```

### 2. Instale as dependências
```bash
pip install pandas
```

### 3. Execute o script
```bash
python health_score.py
```

### 4. Resultado esperado
O script exibe no terminal:
- Health score de cada cliente na última semana
- Clientes em risco alto que precisam de ação imediata
- Comparativo de variação em relação à semana anterior

Também gera um arquivo `relatorio_health_score.csv` com o histórico completo.

---

## 📁 Estrutura do projeto

```
health-score-churn/
│
├── health_score.py          # Script principal
├── dados_clientes.csv       # Base de dados semanal (fictícia)
├── relatorio_health_score.csv  # Gerado ao executar o script
└── README.md
```

---

## 🛠️ Tecnologias

- Python 3
- Pandas

---

## 📌 Próximos passos

- [ ] Integração direta com Google Sheets via API
- [ ] Envio automático de alertas por e-mail
- [ ] Dashboard visual com matplotlib ou Streamlit

---

## 👩‍💻 Autora

Desenvolvido por [Kamila](https://github.com/klopescode) — projeto baseado em solução real implementada em ambiente corporativo.
