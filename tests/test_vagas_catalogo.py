"""Catálogo de portais e empresas-alvo: o do repositório mais o local da pessoa."""

import importlib

import pytest

from app.vagas.catalogo import (
    ErroCatalogo,
    acrescentar_empresa,
    acrescentar_portal,
    carregar_catalogo,
)


def test_catalogo_do_repositorio_e_valido():
    catalogo = carregar_catalogo()
    ids = [p.id for p in catalogo.portais]
    assert len(ids) == len(set(ids))
    assert len(catalogo.portais) >= 69
    assert {"greenhouse", "lever", "ashby", "remotive", "weworkremotely", "himalayas"} <= {
        p.id for p in catalogo.ativos()
    }
    assert catalogo.portal("linkedin").modo_leitura == "alerta_email"
    assert catalogo.portal("remote-ok").status == "descartado"
    assert catalogo.portal("remote-ok").motivo_descarte


def test_todo_portal_ativo_tem_leitor():
    for portal in carregar_catalogo().ativos():
        modulo = importlib.import_module(f"app.vagas.portais.{portal.leitor}")
        assert callable(modulo.buscar) and callable(modulo.ainda_aberta), portal.id


def test_empresas_do_repositorio():
    catalogo = carregar_catalogo()
    assert len(catalogo.empresas) >= 30
    assert {e.ats for e in catalogo.empresas} == {"greenhouse", "lever", "ashby"}
    assert len({(e.ats, e.quadro) for e in catalogo.empresas}) == len(catalogo.empresas)
    assert [e.nome for e in catalogo.empresas_do("ashby")]


def test_lembretes_sao_os_portais_sem_leitura_automatica():
    catalogo = carregar_catalogo()
    lembretes = {p.id for p in catalogo.lembretes()}
    assert {"wellfound", "toptal", "linkedin"} <= lembretes
    assert "greenhouse" not in lembretes
    assert not any(catalogo.portal(i).status == "descartado" for i in lembretes)


def test_catalogo_local_acrescenta_sem_tocar_no_repositorio(tmp_path):
    pasta = tmp_path / "Meu Drive" / "JobFit — dados"
    acrescentar_empresa(pasta, nome="Empresa Ção", ats="lever", quadro="empresa-cao")
    acrescentar_portal(pasta, nome="Portal Só Meu", url="https://exemplo.com.br", frequencia_dias=7)
    catalogo = carregar_catalogo(pasta)
    assert any(e.quadro == "empresa-cao" and e.local for e in catalogo.empresas)
    portal = catalogo.portal("portal-so-meu")
    assert portal.modo_leitura == "lembrete" and portal.adicionado_por == "local"
    texto = (pasta / "catalogo_local.yaml").read_text(encoding="utf-8")
    assert "Empresa Ção" in texto and "Portal Só Meu" in texto
    assert len(carregar_catalogo().empresas) < len(catalogo.empresas)


def test_empresa_repetida_nao_duplica(tmp_path):
    acrescentar_empresa(tmp_path, nome="Nubank", ats="ashby", quadro="nubank")
    catalogo = carregar_catalogo(tmp_path)
    assert sum(1 for e in catalogo.empresas if e.quadro == "nubank") == 1


def test_catalogo_local_quebrado_avisa(tmp_path):
    (tmp_path / "catalogo_local.yaml").write_text("empresas: [{nome: X}]", encoding="utf-8")
    with pytest.raises(ErroCatalogo, match=r"catalogo_local\.yaml"):
        carregar_catalogo(tmp_path)


def test_identificador_de_quadro_invalido(tmp_path):
    with pytest.raises(ErroCatalogo):
        acrescentar_empresa(tmp_path, nome="X", ats="greenhouse", quadro="https://boards/x y")
