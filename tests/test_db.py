from datetime import UTC, datetime, timedelta, timezone

from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlmodel import Session, select

from app import config
from app.db import abrir_banco, banco_do_perfil, config_alembic, fechar_bancos
from app.ia.modelos import ChamadaIA


def _revisao(engine) -> str:
    with engine.connect() as conexao:
        return conexao.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def test_banco_novo_migra_ate_a_ultima_versao():
    engine = banco_do_perfil("ana")
    head = ScriptDirectory.from_config(config_alembic()).get_current_head()
    assert _revisao(engine) == head
    assert {"chamadas_ia", "cache_ia"} <= set(inspect(engine).get_table_names())


def test_banco_fica_na_pasta_do_app_e_com_acento(tmp_path):
    caminho = tmp_path / "Meu Drive" / "Currículo – teste" / "ana.db"
    abrir_banco(caminho)
    assert caminho.exists()
    assert config.caminho_banco("ana").parent == config.pasta_app() / "bancos"


def test_reabrir_mantem_dados():
    engine = banco_do_perfil("ana")
    with Session(engine) as sessao:
        sessao.add(ChamadaIA(tarefa="t", versao_prompt=1, provedor="p", modelo="m"))
        sessao.commit()
    fechar_bancos()

    with Session(banco_do_perfil("ana")) as sessao:
        assert len(sessao.exec(select(ChamadaIA)).all()) == 1


def test_perfis_tem_bancos_isolados():
    with Session(banco_do_perfil("ana")) as sessao:
        sessao.add(ChamadaIA(tarefa="t", versao_prompt=1, provedor="p", modelo="m"))
        sessao.commit()

    with Session(banco_do_perfil("camila")) as sessao:
        assert sessao.exec(select(ChamadaIA)).all() == []
    assert config.caminho_banco("ana") != config.caminho_banco("camila")


def test_datas_voltam_em_utc():
    brasilia = timezone(timedelta(hours=-3))
    momento = datetime(2026, 10, 29, 21, 30, tzinfo=brasilia)
    engine = banco_do_perfil("ana")
    with Session(engine) as sessao:
        sessao.add(
            ChamadaIA(tarefa="t", versao_prompt=1, provedor="p", modelo="m", criado_em=momento)
        )
        sessao.commit()
    with Session(engine) as sessao:
        lido = sessao.exec(select(ChamadaIA)).one().criado_em
    assert lido == momento
    assert lido.tzinfo == UTC


def test_migracoes_batem_com_os_modelos():
    """Tabela ou coluna nova no modelo sem migração (ou o contrário) quebra aqui."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlmodel import SQLModel

    import app.dossie.tabelas  # noqa: F401
    import app.vagas.tabelas  # noqa: F401

    engine = banco_do_perfil("ana")
    with engine.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), SQLModel.metadata)
    assert diferencas == []
