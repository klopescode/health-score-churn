"""
relatorio_email.py
------------------
Automação de envio de relatório semanal de health score por e-mail.

Lê os dados do arquivo relatorio_health_score.csv (gerado pelo health_score.py),
filtra os clientes em risco e envia um e-mail formatado automaticamente via Gmail.

Pré-requisitos:
- Ter rodado o health_score.py antes (para gerar o relatorio_health_score.csv)
- Configurar as variáveis de ambiente EMAIL_REMETENTE e EMAIL_SENHA (veja o README)
"""

import pandas as pd
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date


# --- Configurações ---
EMAIL_REMETENTE = os.environ.get("EMAIL_REMETENTE")  # seu e-mail
EMAIL_SENHA     = os.environ.get("EMAIL_SENHA")       # senha de app do Gmail
EMAIL_DESTINO   = os.environ.get("EMAIL_DESTINO", EMAIL_REMETENTE)  # quem recebe


# --- Leitura dos dados ---
def carregar_relatorio(caminho="relatorio_health_score.csv"):
    df = pd.read_csv(caminho)
    df["semana"] = pd.to_datetime(df["semana"])
    return df


# --- Filtra última semana ---
def ultima_semana(df):
    semana_max = df["semana"].max()
    return df[df["semana"] == semana_max].copy()


# --- Monta o corpo do e-mail em HTML ---
def montar_email(df):
    semana = df["semana"].iloc[0].date()

    em_risco   = df[df["health_score"] < 50].sort_values("health_score")
    atencao    = df[(df["health_score"] >= 50) & (df["health_score"] < 80)].sort_values("health_score")
    saudaveis  = df[df["health_score"] >= 80].sort_values("health_score", ascending=False)

    def linha_tabela(row):
        cor = "#ffcccc" if row["health_score"] < 50 else "#fff9c4" if row["health_score"] < 80 else "#d4edda"
        return f"""
        <tr style="background:{cor}">
            <td style="padding:8px;border:1px solid #ddd">{row['cliente']}</td>
            <td style="padding:8px;border:1px solid #ddd;text-align:center">{int(row['health_score'])} pts</td>
            <td style="padding:8px;border:1px solid #ddd;text-align:center">{row['risco']}</td>
        </tr>"""

    linhas_risco    = "".join(linha_tabela(row) for _, row in em_risco.iterrows())
    linhas_atencao  = "".join(linha_tabela(row) for _, row in atencao.iterrows())
    linhas_saudavel = "".join(linha_tabela(row) for _, row in saudaveis.iterrows())

    alerta = ""
    if not em_risco.empty:
        nomes = ", ".join(em_risco["cliente"].tolist())
        alerta = f"""
        <div style="background:#fff3cd;border-left:4px solid #e74c3c;padding:12px;margin-bottom:20px;border-radius:4px">
            <strong>🚨 Ação necessária:</strong> {len(em_risco)} cliente(s) em risco alto esta semana:<br>
            <strong>{nomes}</strong>
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
def enviar_email(html, semana):
    if not EMAIL_REMETENTE or not EMAIL_SENHA:
        print("⚠️  Variáveis de ambiente não configuradas.")
        print("    Configure EMAIL_REMETENTE e EMAIL_SENHA antes de executar.")
        print("\n📧 Prévia do e-mail gerada — veja o arquivo 'preview_email.html'")
        with open("preview_email.html", "w", encoding="utf-8") as f:
            f.write(html)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Health Score Semanal — {semana}"
    msg["From"]    = EMAIL_REMETENTE
    msg["To"]      = EMAIL_DESTINO
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
            servidor.login(EMAIL_REMETENTE, EMAIL_SENHA)
            servidor.sendmail(EMAIL_REMETENTE, EMAIL_DESTINO, msg.as_string())
        print(f"✅ E-mail enviado para {EMAIL_DESTINO}")
    except Exception as e:
        print(f"❌ Erro ao enviar e-mail: {e}")


# --- Main ---
def main():
    print("\n📂 Carregando relatório...")
    df = carregar_relatorio()

    print("🔍 Filtrando última semana...")
    df_semana = ultima_semana(df)
    semana = df_semana["semana"].iloc[0].date()

    print("📝 Montando e-mail...")
    html = montar_email(df_semana)

    print("📤 Enviando...")
    enviar_email(html, semana)


if __name__ == "__main__":
    main()
