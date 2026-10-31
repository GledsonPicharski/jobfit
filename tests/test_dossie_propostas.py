from pathlib import Path

import pytest

from app.db import banco_do_perfil
from app.dossie.formato import ler_dossie
from app.dossie.modelos import Fato, Periodo
from app.dossie.propostas import (
    Candidato,
    ErroProposta,
    aplicar_importacao,
    candidatos_propostos,
    criar_importacao,
    decidir,
    descartar_importacao,
    montar_propostas,
    obter_importacao,
    propostas_da_importacao,
    registrar_propostas,
    rejeitados_anteriores,
)
from app.dossie.versoes import caminho_dossie, versoes
from app.perfis.servico import criar_perfil

RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = (RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8")
FATOS = ler_dossie(EXEMPLO).fatos


def _cand(tipo="resultado", texto="Criou um painel novo.", fonte="cv", **campos) -> Candidato:
    return Candidato(tipo=tipo, texto=texto, fonte=fonte, **campos)


# --- montagem (código puro) -----------------------------------------------------


def test_fato_novo_vira_proposta_novo():
    montagem = montar_propostas(FATOS, [_cand()])
    [p] = montagem.propostas
    assert (p.acao, p.sugestao, p.fato_alvo) == ("novo", "aprovar", None)


def test_duplicado_e_ignorado_mesmo_com_caixa_acento_e_pontuacao():
    repetido = _cand(
        tipo="ferramenta", texto="python, sql e DBT", fonte="linkedin_pdf"
    )  # F-041: "Python, SQL e dbt."
    montagem = montar_propostas(FATOS, [repetido])
    assert montagem.propostas == []
    assert montagem.duplicados == 1


def test_duplicado_dentro_da_mesma_importacao():
    montagem = montar_propostas(FATOS, [_cand(), _cand(texto="Criou um painel novo")])
    assert len(montagem.propostas) == 1
    assert montagem.duplicados == 1


def test_mesmo_texto_com_tipo_diferente_nao_e_duplicado():
    montagem = montar_propostas(FATOS, [_cand(tipo="preferencia", texto="Python, SQL e dbt.")])
    assert len(montagem.propostas) == 1


def test_competencia_e_ferramenta_sao_o_mesmo_assunto():
    # O LinkedIn chama de competência o que o dossiê guarda como ferramenta (F-041).
    montagem = montar_propostas(FATOS, [_cand(tipo="competencia", texto="Python, SQL e dbt.")])
    assert montagem.propostas == []


def test_ja_rejeitado_nao_volta():
    cand = _cand()
    montagem = montar_propostas(FATOS, [cand], rejeitados={cand.chave})
    assert montagem.propostas == []
    assert montagem.ja_rejeitados == 1


def _cargo(fonte: str, inicio: str, fim: str | None, empresa="Empresa Exemplo") -> Candidato:
    return _cand(
        tipo="cargo",
        texto=f"Gerente de Dados e IA na {empresa}.",
        empresa=empresa,
        cargo="Gerente de Dados e IA",
        periodo=Periodo(inicio=inicio, fim=fim),
        fonte=fonte,
    )


def test_mesmo_cargo_e_periodo_e_duplicado():
    montagem = montar_propostas(FATOS, [_cargo("cv", "2023-03", None)])
    assert montagem.propostas == []
    assert montagem.duplicados == 1


def test_cv_com_data_diferente_do_linkedin_gera_conflito_e_sugere_o_linkedin():
    # F-010 veio do LinkedIn; o CV antigo diz outra data de início.
    montagem = montar_propostas(FATOS, [_cargo("cv", "2022-11", None)])
    [p] = montagem.propostas
    assert (p.acao, p.fato_alvo, p.sugestao) == ("conflito", "F-010", "manter_atual")
    assert "LinkedIn" in p.motivo


def test_linkedin_com_data_diferente_de_fato_vindo_de_cv_sugere_o_linkedin():
    fatos = [
        f.model_copy(update={"origem": "cv 2026-01-01"}) if f.id == "F-010" else f for f in FATOS
    ]
    [p] = montar_propostas(fatos, [_cargo("linkedin_pdf", "2022-11", None)]).propostas
    assert (p.acao, p.sugestao) == ("conflito", "usar_nova")


def test_fato_confirmado_a_mao_prevalece_sobre_o_linkedin():
    fatos = [
        f.model_copy(update={"origem": "manual 2026-01-01"}) if f.id == "F-010" else f
        for f in FATOS
    ]
    [p] = montar_propostas(fatos, [_cargo("linkedin_pdf", "2022-11", None)]).propostas
    assert p.sugestao == "manter_atual"


def test_cargo_existente_sem_periodo_recebe_proposta_de_completar():
    fatos = [f.model_copy(update={"periodo": None}) if f.id == "F-010" else f for f in FATOS]
    [p] = montar_propostas(fatos, [_cargo("linkedin_pdf", "2023-03", None)]).propostas
    assert (p.acao, p.fato_alvo, p.sugestao) == ("alterar", "F-010", "aprovar")


# Fatos escritos à mão, como num dossiê migrado: cargo só no texto, empresa abreviada.
def _fato(n, tipo, texto, empresa=None, inicio=None, fim=None, origem="manual 2026-10-25"):
    periodo = Periodo(inicio=inicio, fim=fim) if inicio else None
    return Fato(
        id=f"F-{n:03d}", tipo=tipo, texto=texto, empresa=empresa, periodo=periodo, origem=origem
    )


A_MAO = [
    _fato(
        100,
        "cargo",
        "Gerente Sênior de Dados & IA no Grupo Exemplo (fintech)",
        "Exemplo",
        "2024-08",
    ),
    _fato(
        101,
        "cargo",
        "Gerente de Dados & IA no Grupo Exemplo (fintech)",
        "Exemplo",
        "2022-06",
        "2024-07",
    ),
    _fato(
        600,
        "docencia",
        "Professor convidado no ISAE-Exemplo, Big Data",
        "ISAE-Exemplo",
        "2018-11",
        "2019-06",
    ),
    _fato(400, "idioma", "Português: nativo"),
    _fato(
        202,
        "formacao",
        "Bacharelado em Estatística — Universidade Fictícia do Paraná (UFP)",
        "UFP",
        "2010",
        "2014",
    ),
    _fato(201, "formacao", "Mestrado em Biotecnologia — Faculdades Exemplo", "Faculdades Exemplo"),
    _fato(502, "certificacao", "Software Engineering for Data Scientists in Python — DataCamp"),
    _fato(310, "ferramenta", "Engenharia de software: Git, HTML, CSS e JavaScript"),
    _fato(2, "contato", "E-mail: ana" + "@exemplo.test"),
]


def _do_linkedin(tipo, texto, **campos):
    return _cand(tipo=tipo, texto=texto, fonte="linkedin_pdf", **campos)


def _cargo_linkedin(cargo, empresa, inicio, fim=None, tipo="cargo"):
    return _do_linkedin(
        tipo,
        f"{cargo} — {empresa}",
        empresa=empresa,
        cargo=cargo,
        periodo=Periodo(inicio=inicio, fim=fim),
    )


def test_cargo_reconhecido_por_empresa_e_inicio_mesmo_sem_campo_cargo():
    cand = _cargo_linkedin("Gerente Sênior de Dados & IA - Fintech", "Grupo Exemplo", "2024-08")
    assert montar_propostas(A_MAO, [cand]).propostas == []


def test_mesmo_inicio_com_fim_diferente_e_conflito():
    cand = _cargo_linkedin("Gerente de Dados & IA - Fintech", "Grupo Exemplo", "2022-06", "2024-08")
    [p] = montar_propostas(A_MAO, [cand]).propostas
    assert (p.acao, p.fato_alvo) == ("conflito", "F-101")


def test_datas_diferentes_casam_pelo_titulo_sem_confundir_senioridade():
    cand = _cargo_linkedin("Gerente de Dados & IA", "Grupo Exemplo", "2022-01", "2024-07")
    [p] = montar_propostas(A_MAO, [cand]).propostas
    assert (p.acao, p.fato_alvo) == ("conflito", "F-101")


def test_cargo_de_outra_empresa_com_mesma_data_e_novo():
    cand = _cargo_linkedin("Gerente de Dados & IA", "Outra Empresa", "2022-06", "2024-07")
    [p] = montar_propostas(A_MAO, [cand]).propostas
    assert p.acao == "novo"


def test_cargo_do_linkedin_reconhece_docencia_ja_registrada():
    cand = _cargo_linkedin("Professor convidado, Big Data", "ISAE", "2018-11", "2019-06")
    assert montar_propostas(A_MAO, [cand]).propostas == []


@pytest.mark.parametrize(
    ("tipo", "texto", "campos"),
    [
        ("idioma", "Português: nativo ou bilíngue", {}),
        (
            "formacao",
            "Graduação, Statistics — Universidade Fictícia do Paraná",
            {"empresa": "Universidade Fictícia do Paraná"},
        ),
        (
            "formacao",
            "Master's degree, Biotecnologia — FPP - Faculdades Exemplo",
            {"empresa": "FPP - Faculdades Exemplo"},
        ),
        ("certificacao", "Software Engineering for Data Scientists in Python", {}),
        ("competencia", "HTML", {}),
        ("competencia", "Cascading Style Sheets (CSS)", {}),  # a sigla está no dossiê
        ("contato", "E-mail: ana" + "@exemplo.test", {}),
    ],
)
def test_ja_registrado_com_outras_palavras_nao_vira_proposta(tipo, texto, campos):
    montagem = montar_propostas(A_MAO, [_do_linkedin(tipo, texto, **campos)])
    assert montagem.propostas == []
    assert montagem.duplicados == 1


@pytest.mark.parametrize(
    ("tipo", "texto", "campos"),
    [
        ("idioma", "Francês: básico", {}),
        ("formacao", "MBA — Escola Nova", {"empresa": "Escola Nova"}),
        ("certificacao", "Data Science in Real Life", {}),
        ("competencia", "R", {}),  # palavra inteira: o "r" de "Git" não conta
    ],
)
def test_o_que_falta_no_dossie_vira_proposta(tipo, texto, campos):
    [p] = montar_propostas(A_MAO, [_do_linkedin(tipo, texto, **campos)]).propostas
    assert p.acao == "novo"


def test_candidato_com_alerta_comeca_sugerindo_rejeitar():
    cand = _cand(alertas=["o trecho citado não está no texto de origem"])
    [p] = montar_propostas(FATOS, [cand]).propostas
    assert p.sugestao == "rejeitar"


# --- importação no banco e aplicação no dossiê ----------------------------------


@pytest.fixture
def ana(pasta_dados):
    perfil = criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    caminho_dossie(pasta_dados, "ana").write_text(EXEMPLO, encoding="utf-8")
    return perfil


@pytest.fixture
def engine(ana):
    return banco_do_perfil("ana")


def _importar(engine, candidatos, fonte="cv"):
    importacao = criar_importacao(engine, fonte, "cv-antigo.pdf")
    registrar_propostas(engine, importacao.id, montar_propostas(FATOS, candidatos))
    return importacao.id, propostas_da_importacao(engine, importacao.id)


def test_propostas_comecam_pendentes_e_com_alerta_rejeitadas(engine):
    _, props = _importar(engine, [_cand(), _cand(texto="Outro.", alertas=["sem trecho"])])
    assert [p.decisao for p in props] == ["pendente", "rejeitada"]


def test_nao_aplica_com_proposta_pendente(pasta_dados, ana, engine):
    imp, _ = _importar(engine, [_cand()])
    with pytest.raises(ErroProposta, match="pendente"):
        aplicar_importacao(pasta_dados, engine, ana, imp)


def test_rejeitar_uma_editar_outra_aprovar_o_resto(pasta_dados, ana, engine):
    imp, props = _importar(
        engine,
        [
            _cand(texto="Fato rejeitado pela Ana."),
            _cand(texto="Fato com erro de digitaçao.", empresa="Empresa Exemplo"),
            _cand(tipo="idioma", texto="Espanhol intermediário."),
            _cand(tipo="certificacao", texto="Certificação Fictícia em Nuvem."),
        ],
    )
    decidir(engine, props[0].id, "rejeitada")
    decidir(
        engine,
        props[1].id,
        "editada",
        {"tipo": "resultado", "texto": "Fato com erro de digitação corrigido.", "privado": True},
    )
    decidir(engine, props[2].id, "aprovada")
    decidir(engine, props[3].id, "aprovada")

    versao = aplicar_importacao(pasta_dados, engine, ana, imp)

    doc = ler_dossie(caminho_dossie(pasta_dados, "ana").read_text(encoding="utf-8"))
    novos = {f.texto: f for f in doc.fatos if f.id not in {g.id for g in FATOS}}
    assert set(novos) == {
        "Fato com erro de digitação corrigido.",
        "Espanhol intermediário.",
        "Certificação Fictícia em Nuvem.",
    }
    editado = novos["Fato com erro de digitação corrigido."]
    assert editado.privado is True
    assert editado.empresa == "Empresa Exemplo"  # campo não editado continua
    assert [f.id for f in novos.values()] == ["F-051", "F-052", "F-053"]
    assert all(f.origem.startswith("cv ") for f in novos.values())
    assert versao.versao == 4
    assert versao.importacao_id == imp
    assert [v.motivo for v in versoes(engine)][:2] == ["importacao", "edicao_manual"]


def test_aprovar_conflito_troca_o_periodo_do_fato_alvo(pasta_dados, ana, engine):
    imp, [p] = _importar(engine, [_cargo("cv", "2022-11", None)])
    decidir(engine, p.id, "aprovada")
    aplicar_importacao(pasta_dados, engine, ana, imp)

    doc = ler_dossie(caminho_dossie(pasta_dados, "ana").read_text(encoding="utf-8"))
    alvo = doc.fato("F-010")
    assert alvo.periodo == Periodo(inicio="2022-11", fim=None)
    assert alvo.texto == "Gerente de Dados e IA na Empresa Exemplo."
    assert len(doc.fatos) == len(FATOS)


def test_rejeitar_conflito_mantem_o_fato_atual(pasta_dados, ana, engine):
    imp, [p] = _importar(engine, [_cargo("cv", "2022-11", None)])
    decidir(engine, p.id, "rejeitada")
    assert aplicar_importacao(pasta_dados, engine, ana, imp) is None  # nada a gravar

    doc = ler_dossie(caminho_dossie(pasta_dados, "ana").read_text(encoding="utf-8"))
    assert doc.fato("F-010").periodo == Periodo(inicio="2023-03", fim=None)


def test_rejeitados_entram_na_lista_para_nao_voltar(pasta_dados, ana, engine):
    imp, props = _importar(engine, [_cand()])
    decidir(engine, props[0].id, "rejeitada")
    assert rejeitados_anteriores(engine) == set()  # ainda em revisão
    aplicar_importacao(pasta_dados, engine, ana, imp)
    assert _cand().chave in rejeitados_anteriores(engine)


def test_descartar_nao_conta_como_rejeitar(engine):
    imp, props = _importar(engine, [_cand()])
    decidir(engine, props[0].id, "rejeitada")
    descartar_importacao(engine, imp)
    assert obter_importacao(engine, imp).status == "descartada"
    assert rejeitados_anteriores(engine) == set()


def test_descartar_importacao_gravada_e_recusado(pasta_dados, ana, engine):
    imp, props = _importar(engine, [_cand()])
    decidir(engine, props[0].id, "aprovada")
    aplicar_importacao(pasta_dados, engine, ana, imp)
    with pytest.raises(ErroProposta, match="já foi gravada"):
        descartar_importacao(engine, imp)


def test_segunda_rodada_acrescenta_sem_repetir_o_ja_proposto(engine):
    """A IA lê as descrições depois que o código leu os cargos do PDF."""
    cargo = _cargo("linkedin_pdf", "2018-01", "2023-02", empresa="Outra Empresa")
    imp, primeiras = _importar(engine, [cargo], fonte="linkedin_pdf")
    importacao = obter_importacao(engine, imp)
    ja = candidatos_propostos(engine, importacao)
    assert [c.texto for c in ja] == [cargo.texto]

    da_ia = [
        _cargo("linkedin_pdf", "2018", "2023", empresa="Outra Empresa"),  # mesmo cargo
        _cand(texto="Reduziu o custo em 30%.", fonte="linkedin_pdf"),
    ]
    montagem = montar_propostas(FATOS, da_ia, ja_propostos=ja)
    assert [p.candidato.texto for p in montagem.propostas] == ["Reduziu o custo em 30%."]
    registrar_propostas(engine, imp, montagem, extracao_feita=True)

    todas = propostas_da_importacao(engine, imp)
    assert [p.ordem for p in todas] == [0, 1]
    assert todas[0].id == primeiras[0].id
    importacao = obter_importacao(engine, imp)
    assert importacao.extracao == "feita"
    assert importacao.duplicados == 1


def test_edicao_invalida_e_recusada(engine):
    _, [p] = _importar(engine, [_cand()])
    with pytest.raises(ErroProposta, match="tipo"):
        decidir(engine, p.id, "editada", {"tipo": "inventado", "texto": "x"})
    with pytest.raises(ErroProposta, match="texto"):
        decidir(engine, p.id, "editada", {"tipo": "resultado", "texto": "  "})


def test_importacao_aplicada_nao_aceita_mais_decisoes(pasta_dados, ana, engine):
    imp, [p] = _importar(engine, [_cand()])
    decidir(engine, p.id, "aprovada")
    aplicar_importacao(pasta_dados, engine, ana, imp)
    with pytest.raises(ErroProposta):
        decidir(engine, p.id, "rejeitada")
    with pytest.raises(ErroProposta):
        aplicar_importacao(pasta_dados, engine, ana, imp)
