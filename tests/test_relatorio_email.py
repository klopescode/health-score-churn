import smtplib

import pytest

import health_score as hs
import relatorio_email as rel


@pytest.fixture
def relatorio(tmp_path):
    """Gera o relatório a partir dos dados de exemplo, como o health_score.py faz."""
    caminho = tmp_path / "relatorio.csv"
    hs.gerar_relatorio(hs.carregar_dados(hs.CAMINHO_DADOS)).to_csv(caminho, index=False)
    return caminho


@pytest.fixture
def com_credenciais(monkeypatch):
    monkeypatch.setattr(rel, "EMAIL_REMETENTE", "remetente@example.com")
    monkeypatch.setattr(rel, "EMAIL_SENHA", "senha")
    monkeypatch.setattr(rel, "EMAIL_DESTINO", "destino@example.com")


@pytest.fixture
def sem_credenciais(monkeypatch):
    monkeypatch.setattr(rel, "EMAIL_REMETENTE", None)
    monkeypatch.setattr(rel, "EMAIL_SENHA", None)


class SMTPFalso:
    enviados = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def login(self, usuario, senha):
        pass

    def sendmail(self, remetente, destino, mensagem):
        SMTPFalso.enviados.append(destino)


class SMTPRecusaLogin(SMTPFalso):
    def login(self, usuario, senha):
        raise smtplib.SMTPAuthenticationError(535, b"senha incorreta")


def montar(relatorio):
    return rel.montar_email(rel.ultima_semana(rel.carregar_relatorio(relatorio)))


# --- Conteúdo do e-mail ---

def test_email_separa_clientes_pelos_limites(relatorio):
    html = montar(relatorio)
    assert "Risco Alto (2 cliente(s))" in html
    assert "Atenção (1 cliente(s))" in html
    assert "Saudáveis (2 cliente(s))" in html


def test_email_mostra_ha_quantas_semanas_o_cliente_esta_em_risco(relatorio):
    html = montar(relatorio)
    assert "Churrascaria Gaúcha</strong> (4ª semana seguida em risco)" in html
    assert "Pizzaria Bella Napoli</strong> (3ª semana seguida em risco)" in html


def test_email_escapa_caracteres_especiais_do_nome(tmp_path):
    dados = tmp_path / "dados.csv"
    dados.write_text(
        "semana,cliente,operacional,criativo,resultado,interacao\n"
        "2024-01-05,<b>Bar</b> & Cia,0,0,0,0\n",
        encoding="utf-8",
    )
    relatorio = tmp_path / "relatorio.csv"
    hs.gerar_relatorio(hs.carregar_dados(dados)).to_csv(relatorio, index=False)

    html = montar(relatorio)
    assert "&lt;b&gt;Bar&lt;/b&gt; &amp; Cia" in html
    assert "<b>Bar</b>" not in html


def test_cliente_chamado_na_nao_vira_valor_vazio(tmp_path):
    dados = tmp_path / "dados.csv"
    dados.write_text(
        "semana,cliente,operacional,criativo,resultado,interacao\n"
        "2024-01-05,NA,1,1,1,1\n",
        encoding="utf-8",
    )
    relatorio = tmp_path / "relatorio.csv"
    hs.gerar_relatorio(hs.carregar_dados(dados)).to_csv(relatorio, index=False)
    assert ">NA</td>" in montar(relatorio)


def test_relatorio_antigo_sem_coluna_nova(tmp_path):
    caminho = tmp_path / "relatorio.csv"
    caminho.write_text("semana,cliente,health_score,risco\n2024-01-05,A,100,ok\n", encoding="utf-8")
    with pytest.raises(hs.DadosInvalidosError, match="semanas_em_risco"):
        rel.carregar_relatorio(caminho)


# --- Envio ---

def test_sem_credenciais_gera_previa(tmp_path, sem_credenciais):
    previa = tmp_path / "preview.html"
    assert rel.enviar_email("<html></html>", "2024-01-26", previa) is True
    assert previa.read_text(encoding="utf-8") == "<html></html>"


def test_envio_com_sucesso(tmp_path, com_credenciais, monkeypatch):
    SMTPFalso.enviados = []
    monkeypatch.setattr(smtplib, "SMTP_SSL", SMTPFalso)
    assert rel.enviar_email("<html></html>", "2024-01-26", tmp_path / "preview.html") is True
    assert SMTPFalso.enviados == ["destino@example.com"]


def test_falha_no_login_retorna_false(tmp_path, com_credenciais, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP_SSL", SMTPRecusaLogin)
    assert rel.enviar_email("<html></html>", "2024-01-26", tmp_path / "preview.html") is False


def test_falha_de_conexao_retorna_false(tmp_path, com_credenciais, monkeypatch):
    def sem_rede(*args, **kwargs):
        raise OSError("Name or service not known")

    monkeypatch.setattr(smtplib, "SMTP_SSL", sem_rede)
    assert rel.enviar_email("<html></html>", "2024-01-26", tmp_path / "preview.html") is False


# --- Execução completa ---

def test_main_sai_com_erro_quando_envio_falha(relatorio, com_credenciais, monkeypatch):
    monkeypatch.setattr(rel, "CAMINHO_RELATORIO", relatorio)
    monkeypatch.setattr(smtplib, "SMTP_SSL", SMTPRecusaLogin)
    with pytest.raises(SystemExit) as saida:
        rel.main()
    assert saida.value.code == 1


def test_main_gera_previa_sem_credenciais(relatorio, tmp_path, sem_credenciais, monkeypatch):
    previa = tmp_path / "preview.html"
    monkeypatch.setattr(rel, "CAMINHO_RELATORIO", relatorio)
    monkeypatch.setattr(rel, "CAMINHO_PREVIEW", previa)
    rel.main()
    assert "Relatório de Health Score — 2024-01-26" in previa.read_text(encoding="utf-8")


def test_main_sem_relatorio_pede_para_rodar_health_score(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rel, "CAMINHO_RELATORIO", tmp_path / "nao_existe.csv")
    with pytest.raises(SystemExit) as saida:
        rel.main()
    assert saida.value.code == 1
    assert "Rode o health_score.py antes" in capsys.readouterr().out
