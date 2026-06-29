# Health Score — Monitoramento de Risco de Churn

Esse projeto nasceu de uma necessidade real do meu trabalho. Na agência onde atuo, acompanho vários clientes ao mesmo tempo e precisava de uma forma de identificar quem estava em risco de cancelar antes que isso acontecesse — sem depender só da intuição.

A solução que criei usava Google Sheets e Apps Script. Aqui refiz a lógica em Python para estudar a linguagem e deixar o projeto mais acessível.

---

## Como funciona

Todo cliente recebe uma pontuação semanal com base em 4 indicadores que acompanhamos na agência:

| Indicador | O que avalia | Peso |
|-----------|-------------|------|
| Operacional | Se houve erro operacional na semana | 30 pts |
| Criativo | Se precisou refazer algum criativo | 20 pts |
| Resultado | Se a semana teve resultado positivo | 30 pts |
| Interação | Se o cliente está ativo no grupo | 20 pts |

A soma define o nível de risco:

- **80 a 100** — cliente saudável, sem ação necessária
- **50 a 79** — atenção, vale acompanhar de perto
- **0 a 49** — risco alto, agir antes que peça cancelamento

---

## O que cada arquivo faz

**health_score.py** — lê os dados do CSV, calcula o score de cada cliente, mostra quem está em risco e compara com a semana anterior pra ver se a situação melhorou ou piorou.

**relatorio_email.py** — pega o resultado gerado pelo script acima e manda um e-mail formatado automaticamente. Criei isso porque na prática precisava compartilhar o relatório com o time toda sexta sem ter que montar nada manualmente.

**dados_clientes.csv** — dados fictícios que usei pra testar. Na versão real, esses dados vinham de uma planilha preenchida semanalmente pela equipe.

---

## Como rodar

Instala o pandas se ainda não tiver:

```bash
pip install pandas
```

Roda o health score primeiro:

```bash
python health_score.py
```

Se quiser também enviar o e-mail, configura suas credenciais:

```bash
export EMAIL_REMETENTE="seuemail@gmail.com"
export EMAIL_SENHA="sua_senha_de_app"
export EMAIL_DESTINO="destinatario@gmail.com"
```

E roda o segundo script:

```bash
python relatorio_email.py
```

Se não configurar o e-mail, ele gera um arquivo `preview_email.html` que você pode abrir no navegador pra ver como ficaria.

> A senha precisa ser uma senha de app do Gmail, não a senha da sua conta. Você gera em: Conta Google → Segurança → Verificação em duas etapas → Senhas de app.

---

## Próximos passos

Tenho vontade de conectar isso direto ao Google Sheets via API, pra não precisar mais do CSV manual. Também quero testar agendar o envio automático toda sexta com algum agendador de tarefas.

---

Feito por [Kamila Lopes](https://github.com/klopescode)
