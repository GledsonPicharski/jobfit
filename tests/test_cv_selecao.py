from datetime import date
from pathlib import Path

from app.cv.selecao import carregar_config, periodo_legivel, selecionar
from app.dossie.formato import ler_dossie
from app.dossie.modelos import Fato, Periodo

RAIZ = Path(__file__).resolve().parents[1]
DOC = ler_dossie((RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8"))
CONFIG = carregar_config()
HOJE = date(2026, 11, 5)


def _fato(id_, tipo, texto, **campos) -> Fato:
    return Fato(id=id_, tipo=tipo, texto=texto, **campos)


def _ids(fatos) -> list[str]:
    return [f.id for f in fatos]


def test_cargos_em_ordem_decrescente_com_os_resultados_da_empresa():
    selecao = selecionar(DOC.fatos, None, set(), CONFIG, HOJE)
    assert [c.cargo.id for c in selecao.cargos] == ["F-010", "F-020"]
    assert _ids(selecao.cargos[0].fatos) == ["F-014"]
    assert _ids(selecao.cargos[1].fatos) == ["F-021"]
    assert all(c.detalhado for c in selecao.cargos)


def test_privado_nao_enviar_ia_e_preferencia_ficam_de_fora():
    selecao = selecionar(DOC.fatos, None, set(), CONFIG, HOJE)
    todos = _ids(selecao.todos)
    assert "F-002" not in todos  # 🔒
    assert "F-001" not in todos  # preferência não vai para CV
    assert {"F-030", "F-040", "F-041", "F-050"} <= set(todos)


def test_proposto_e_rejeitado_nao_entram():
    fatos = [
        *DOC.fatos,
        _fato("F-900", "competencia", "Kubernetes", status="proposto"),
        _fato("F-901", "competencia", "Docker", status="rejeitado"),
    ]
    todos = _ids(selecionar(fatos, None, set(), CONFIG, HOJE).todos)
    assert "F-900" not in todos and "F-901" not in todos


def test_contato_vai_para_o_cabecalho_e_nao_para_a_ia():
    fatos = [
        *DOC.fatos,
        _fato("F-800", "contato", "LinkedIn: linkedin.com/in/ana-exemplo"),
        _fato("F-801", "contato", "CPF: 000", privado=True),
    ]
    selecao = selecionar(fatos, None, set(), CONFIG, HOJE)
    assert _ids(selecao.contato) == ["F-800"]
    assert "F-800" not in _ids(selecao.para_ia)


def test_cargo_antigo_entra_sem_bullets():
    fatos = [
        *DOC.fatos,
        _fato(
            "F-090",
            "cargo",
            "Estagiária na Indústria Antiga.",
            empresa="Indústria Antiga",
            cargo="Estagiária",
            periodo=Periodo(inicio="2008-01", fim="2010-06"),
        ),
        _fato("F-091", "resultado", "Organizou o arquivo.", empresa="Indústria Antiga"),
    ]
    selecao = selecionar(fatos, None, set(), CONFIG, HOJE)
    antigo = selecao.cargos[-1]
    assert antigo.cargo.id == "F-090"
    assert not antigo.detalhado and antigo.fatos == []
    assert "F-091" not in _ids(selecao.para_ia)


def test_relevancia_pela_avaliacao_e_pela_vaga():
    fatos = [
        *DOC.fatos,
        _fato("F-015", "resultado", "Criou o painel de vendas.", empresa="Empresa Exemplo"),
        _fato("F-016", "resultado", "Implantou modelos de crédito.", empresa="Empresa Exemplo"),
    ]
    vaga = "Buscamos experiência com modelos de crédito e painéis."
    selecao = selecionar(fatos, vaga, {"F-015"}, CONFIG, HOJE)
    # citado pela avaliação primeiro, depois o que fala a língua da vaga, depois o resto
    assert _ids(selecao.cargos[0].fatos) == ["F-015", "F-016", "F-014"]


def test_limite_de_bullets_por_cargo():
    extras = [
        _fato(f"F-1{n:02d}", "resultado", f"Resultado {n}.", empresa="Empresa Exemplo")
        for n in range(10)
    ]
    selecao = selecionar([*DOC.fatos, *extras], None, set(), CONFIG, HOJE)
    assert len(selecao.cargos[0].fatos) == CONFIG.bullets_por_cargo


def test_secoes_curtas():
    selecao = selecionar(DOC.fatos, None, set(), CONFIG, HOJE)
    assert _ids(selecao.competencias) == ["F-040", "F-041"]
    assert _ids(selecao.formacao) == ["F-030"]
    assert _ids(selecao.idiomas) == ["F-050"]
    assert selecao.certificacoes == []


def test_periodo_no_formato_do_idioma():
    atual = DOC.fato("F-010")
    assert periodo_legivel(atual, "pt") == "mar 2023 – atual"
    assert periodo_legivel(atual, "en") == "Mar 2023 – Present"
    assert periodo_legivel(DOC.fato("F-030"), "pt") == "2010 – 2014"
    assert periodo_legivel(DOC.fato("F-040"), "pt") == ""
