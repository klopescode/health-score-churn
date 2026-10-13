"""
relatorio_email.py
------------------
Automação de envio de relatório semanal de health score por e-mail.

Lê os dados do arquivo relatorio_health_score.csv (gerado pelo health_score.py),
filtra os clientes em risco e envia um e-mail formatado automaticamente via Gmail.

Pré-requisitos:
- Ter rodado o health_score.py antes (para gerar o relatorio_health_score.csv)
- Configurar as variáveis de ambiente EMAIL_REMETENTE e EMAIL_SENHA (veja o README)

Se o envio falhar, o script termina com código de saída 1, para que um
agendador de tarefas consiga perceber o erro.
"""

import pandas as pd
import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date
from html import escape

from health_score import (
    CAMINHO_RELATORIO,
    LIMITE_ATENCAO,
    LIMITE_SAUDAVEL,
    PASTA,
    DadosInvalidosError,
    descrever_sequencia,
)


# --- Configurações ---
EMAIL_REMETENTE = os.environ.get("EMAIL_REMETENTE")  # seu e-mail
EMAIL_SENHA     = os.environ.get("EMAIL_SENHA")       # senha de app do Gmail
EMAIL_DESTINO   = os.environ.get("EMAIL_DESTINO", EMAIL_REMETENTE)  # quem recebe

CAMINHO_PREVIEW = PASTA / "preview_email.html"

COLUNAS_RELATORIO = ["semana", "cliente", "health_score", "risco", "semanas_em_risco"]


# --- Leitura dos dados ---
def carregar_relatorio(caminho=CAMINHO_RELATORIO):
    df = pd.read_csv(caminho, dtype={"cliente": str, "risco": str}, keep_default_na=False)
    faltando = [coluna for coluna in COLUNAS_RELATORIO if coluna not in df.columns]
    if faltando:
        raise DadosInvalidosError(
            f"O relatório não tem as colunas: {', '.join(faltando)}. Rode o health_score.py de novo."
        )
    df["semana"] = pd.to_datetime(df["semana"])
    return df


# --- Filtra última semana ---
def ultima_semana(df):
    semana_max = df["semana"].max()
    return df[df["semana"] == semana_max].copy()


# --- Monta o corpo do e-mail em HTML ---
def montar_email(df):
    semana = df["semana"].iloc[0].date()

    em_risco   = df[df["health_score"] < LIMITE_ATENCAO].sort_values(
        ["semanas_em_risco", "health_score"], ascending=[False, True]
    )
    atencao    = df[(df["health_score"] >= LIMITE_ATENCAO) & (df["health_score"] < LIMITE_SAUDAVEL)].sort_values("health_score")
    saudaveis  = df[df["health_score"] >= LIMITE_SAUDAVEL].sort_values("health_score", ascending=False)

    def linha_tabela(row):
        cor = "#ffcccc" if row["health_score"] < LIMITE_ATENCAO else "#fff9c4" if row["health_score"] < LIMITE_SAUDAVEL else "#d4edda"
        return f"""
        <tr style="background:{cor}">
            <td style="padding:8px;border:1px solid #ddd">{escape(row['cliente'])}</td>
            <td style="padding:8px;border:1px solid #ddd;text-align:center">{int(row['health_score'])} pts</td>
            <td style="padding:8px;border:1px solid #ddd;text-align:center">{escape(row['risco'])}</td>
        </tr>"""

    linhas_risco    = "".join(linha_tabela(row) for _, row in em_risco.iterrows())
    linhas_atencao  = "".join(linha_tabela(row) for _, row in atencao.iterrows())
    linhas_saudavel = "".join(linha_tabela(row) for _, row in saudaveis.iterrows())

    alerta = ""
    if not em_risco.empty:
        nomes = "<br>".join(
            f"<strong>{escape(row['cliente'])}</strong> ({descrever_sequencia(row['semanas_em_risco'])})"
            for _, row in em_risco.iterrows()
        )
        alerta = f"""
        <div style="background:#fff3cd;border-left:4px solid #e74c3c;padding:12px;margin-bottom:20px;border-radius:4px">
            <strong>🚨 Ação necessária:</strong> {len(em_risco)} cliente(s) em risco alto esta semana:<br>
            {nomes}
        </div>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:auto">

        <h2 style="color:#1A3A5C;border-bottom:2px solid #2E75B6;padding-bottom:8px">
            📊 Relatório de Health Score — {semana}
        </h2>

        <p>Olá! Segue o relatório semanal de monitoramento de clientes.</p>

        {alerta}

        <h3 style="color:#c0392b">🔴 Risco Alto ({len(em_risco)} cliente(s))</h3>
        {"<p style='color:#888'>Nenhum cliente em risco alto esta semana. ✅</p>" if em_risco.empty else f"<table style='width:100%;border-collapse:collapse'><tr style='background:#1A3A5C;color:white'><th style='padding:8px;text-align:left'>Cliente</th><th style='padding:8px'>Score</th><th style='padding:8px'>Status</th></tr>{linhas_risco}</table>"}

        <br>
        <h3 style="color:#e67e22">🟡 Atenção ({len(atencao)} cliente(s))</h3>
        {"<p style='color:#888'>Nenhum cliente em atenção.</p>" if atencao.empty else f"<table style='width:100%;border-collapse:collapse'><tr style='background:#1A3A5C;color:white'><th style='padding:8px;text-align:left'>Cliente</th><th style='padding:8px'>Score</th><th style='padding:8px'>Status</th></tr>{linhas_atencao}</table>"}

        <br>
        <h3 style="color:#27ae60">🟢 Saudáveis ({len(saudaveis)} cliente(s))</h3>
        {"<p style='color:#888'>Nenhum cliente saudável.</p>" if saudaveis.empty else f"<table style='width:100%;border-collapse:collapse'><tr style='background:#1A3A5C;color:white'><th style='padding:8px;text-align:left'>Cliente</th><th style='padding:8px'>Score</th><th style='padding:8px'>Status</th></tr>{linhas_saudavel}</table>"}

        <br>
        <p style="color:#888;font-size:12px;border-top:1px solid #eee;padding-top:12px">
            Relatório gerado automaticamente em {date.today()} via health_score.py
        </p>

    </body></html>"""

    return html


# --- Envia o e-mail ---
def enviar_email(html, semana, caminho_preview=CAMINHO_PREVIEW):
    """
    Envia o e-mail, ou gera a prévia em HTML se as credenciais não estiverem configuradas.
    Retorna False se o envio falhar.
    """
    if not EMAIL_REMETENTE or not EMAIL_SENHA:
        print("⚠️  Variáveis de ambiente não configuradas.")
        print("    Configure EMAIL_REMETENTE e EMAIL_SENHA antes de executar.")
        print(f"\n📧 Prévia do e-mail gerada — veja o arquivo '{caminho_preview.name}'")
        with open(caminho_preview, "w", encoding="utf-8") as f:
            f.write(html)
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Health Score Semanal — {semana}"
    msg["From"]    = EMAIL_REMETENTE
    msg["To"]      = EMAIL_DESTINO
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
            servidor.login(EMAIL_REMETENTE, EMAIL_SENHA)
            servidor.sendmail(EMAIL_REMETENTE, EMAIL_DESTINO, msg.as_string())
    except (smtplib.SMTPException, OSError) as e:
        print(f"❌ Erro ao enviar e-mail: {e}")
        return False

    print(f"✅ E-mail enviado para {EMAIL_DESTINO}")
    return True


# --- Main ---
def main():
    print("\n📂 Carregando relatório...")
    try:
        df = carregar_relatorio(CAMINHO_RELATORIO)
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {CAMINHO_RELATORIO.name}")
        print("    Rode o health_score.py antes para gerar o relatório.")
        sys.exit(1)
    except DadosInvalidosError as e:
        print(f"❌ {e}")
        sys.exit(1)

    print("🔍 Filtrando última semana...")
    df_semana = ultima_semana(df)
    semana = df_semana["semana"].iloc[0].date()

    print("📝 Montando e-mail...")
    html = montar_email(df_semana)

    print("📤 Enviando...")
    if not enviar_email(html, semana, CAMINHO_PREVIEW):
        sys.exit(1)


if __name__ == "__main__":
    main()
