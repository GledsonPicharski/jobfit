from pathlib import Path

from app import config


def test_sem_arquivo_usa_padrao():
    cfg = config.carregar_config()
    assert cfg.pasta_dados is None
    assert cfg.porta == 8765


def test_salvar_e_recarregar_com_acento_e_espaco(tmp_path):
    pasta = tmp_path / "G Meu Drive" / "Currículo – teste"
    config.salvar_config(config.AppConfig(pasta_dados=pasta, ultimo_perfil="ana-exemplo"))

    cfg = config.carregar_config()
    assert cfg.pasta_dados == pasta
    assert cfg.ultimo_perfil == "ana-exemplo"
    assert "Currículo" in config.caminho_config().read_text(encoding="utf-8")


def test_pasta_do_app_respeita_variavel_de_ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBFIT_HOME", str(tmp_path / "outro"))
    assert config.pasta_app() == tmp_path / "outro"
    assert config.caminho_banco("ana") == tmp_path / "outro" / "bancos" / "ana.db"


def test_pasta_do_app_padrao_fica_fora_do_repositorio(monkeypatch):
    monkeypatch.delenv("JOBFIT_HOME")
    pasta = config.pasta_app()
    assert pasta.name == "JobFit"
    assert Path(__file__).resolve().parents[1] not in pasta.parents
