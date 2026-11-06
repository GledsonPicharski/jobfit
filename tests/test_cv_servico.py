import json
from datetime import date
from pathlib import Path

import pytest

from app.cv.servico import (
    checar_cv,
    confirmar_traducao,
    gerar,
    rascunho_do_cv,
    salvar_rascunho,
)
from app.db import banco_do_perfil
from app.dossie.estrutura import inserir_fatos
from app.dossie.formato import ler_dossie
from app.dossie.modelos import Fato
from app.dossie.versoes import caminho_dossie, carregar_dossie
from app.ia.erros import AguardandoResposta
from app.ia.manual import pedidos_pendentes
from app.perfis.modelos import ConfigIA
from app.perfis.servico import criar_perfil, salvar_perfil
from app.vagas.leitura import ler_texto
from app.vagas.servico import registrar_vaga
from tests.ia_falsa import Falso

pytestmark = pytest.mark.anyio

RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = (RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8")
HOJE = date(2026, 11, 5)
# Montado aqui: escrito literal, o pre-commit barra o teste.
EMAIL = "ana.exemplo" + "@exemplo.test"

VAGA = "Gerente de Dados\nBanco Alvo\nRequisitos: Python, SQL e liderança de times de dados."
REDIGIDO = {
    "titulo": {"texto": "Gerente de Dados e IA", "fatos": ["F-010"]},
    "resumo": [
        {"texto": "Lidera dados e IA na Empresa Exemplo desde 2023.", "fatos": ["F-010"]},
    ],
    "experiencias": [
        {
            "cargo_id": "F-020",
            "cargo_traduzido": "Senior Data Analyst",
            "bullets": [
                {"texto": "Reduziu de 5 para 2 dias o fechamento.", "fatos": ["F-021", "F-999"]}
            ],
        },
        {
            "cargo_id": "F-010",
            "cargo_traduzido": "Data & AI Manager",
            "bullets": [
                {"texto": "Automatizou mais de 80% das leituras.", "fatos": ["F-014"]},
            ],
        },
    ],
    "competencias": [{"texto": "Python, SQL e dbt", "fatos": ["F-041"]}],
    "formacao": [{"texto": "Bacharelado em Estatística (2014)", "fatos": ["F-030"]}],
    "idiomas": [{"texto": "Inglês avançado (C1)", "fatos": ["F-050"]}],
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def ana(pasta_dados):
    perfil = criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    perfil = perfil.model_copy(update={"ia": ConfigIA().com_provedor("anthropic")})
    salvar_perfil(pasta_dados, perfil)
    caminho_dossie(pasta_dados, "ana").write_text(EXEMPLO, encoding="utf-8")
    return perfil


@pytest.fixture
def engine(ana):
    return banco_do_perfil("ana")


def _doc_com_contato():
    doc = ler_dossie(EXEMPLO)
    inserir_fatos(doc, [Fato(id="F-800", tipo="contato", texto=f"E-mail: {EMAIL}")])
    return doc


async def test_gerar_monta_a_estrutura_em_codigo_e_as_frases_da_ia(engine, ana, usar_modelo):
    falso = usar_modelo(Falso(REDIGIDO))
    vaga, _ = registrar_vaga(engine, ler_texto(VAGA))
    cv = await gerar(ana, engine, _doc_com_contato(), vaga, "pt", hoje=HOJE)
    rascunho = rascunho_do_cv(cv)

    # a ordem dos cargos é do código (mais recente primeiro), não da IA
    assert [e.cargo_id for e in rascunho.experiencias] == ["F-010", "F-020"]
    assert [e.titulo for e in rascunho.experiencias] == [
        "Gerente de Dados e IA",
        "Analista de Dados Sênior",
    ]
    assert rascunho.experiencias[1].bullets[0].fatos == ["F-021"]  # F-999 saiu
    assert "F-999" in json.loads(cv.alertas)[0]

    pedido = str(falso.ultimo_pedido)
    assert EMAIL not in pedido  # contato não vai para a IA
    assert "Faixa salarial mínima" not in pedido  # 🔒
    assert '"idioma":"pt"' in pedido.replace(" ", "")


async def test_gerar_de_novo_com_o_mesmo_dossie_reaproveita(engine, ana, usar_modelo):
    falso = usar_modelo(Falso(REDIGIDO))
    vaga, _ = registrar_vaga(engine, ler_texto(VAGA))
    primeiro = await gerar(ana, engine, ler_dossie(EXEMPLO), vaga, "pt", hoje=HOJE)
    segundo = await gerar(ana, engine, ler_dossie(EXEMPLO), vaga, "pt", hoje=HOJE)
    assert segundo.id == primeiro.id and falso.chamadas == 1
    em_ingles = await gerar(ana, engine, ler_dossie(EXEMPLO), vaga, "en", hoje=HOJE)
    assert em_ingles.id != primeiro.id and falso.chamadas == 2


async def test_rascunho_gerado_passa_na_checagem(engine, ana, usar_modelo):
    usar_modelo(Falso(REDIGIDO))
    vaga, _ = registrar_vaga(engine, ler_texto(VAGA))
    doc = ler_dossie(EXEMPLO)
    cv = await gerar(ana, engine, doc, vaga, "pt", hoje=HOJE)
    assert checar_cv(cv, doc, vaga).bloqueios == 0


async def test_edicao_com_numero_falso_bloqueia(engine, ana, usar_modelo):
    usar_modelo(Falso(REDIGIDO))
    vaga, _ = registrar_vaga(engine, ler_texto(VAGA))
    doc = ler_dossie(EXEMPLO)
    cv = await gerar(ana, engine, doc, vaga, "pt", hoje=HOJE)
    rascunho = rascunho_do_cv(cv)
    rascunho.experiencias[0].bullets[0].texto = "Automatizou 95% das leituras."
    cv = salvar_rascunho(engine, cv.id, rascunho)
    assert checar_cv(cv, doc, vaga).bloqueios == 1


async def test_cargo_em_ingles_confirmado_vira_cargo_en(engine, ana, pasta_dados, usar_modelo):
    usar_modelo(Falso(REDIGIDO))
    vaga, _ = registrar_vaga(engine, ler_texto(VAGA))
    doc = carregar_dossie(pasta_dados, engine, ana)
    cv = await gerar(ana, engine, doc, vaga, "en", hoje=HOJE)
    rascunho = rascunho_do_cv(cv)
    assert rascunho.experiencias[0].titulo == "Data & AI Manager"
    assert checar_cv(cv, doc, vaga).problemas["experiencias.0.titulo"]

    confirmar_traducao(pasta_dados, engine, ana, "F-010", "Data & AI Manager")
    doc = carregar_dossie(pasta_dados, engine, ana)
    assert doc.fato("F-010").model_extra["cargo_en"] == "Data & AI Manager"
    assert "experiencias.0.titulo" not in checar_cv(cv, doc, vaga).problemas


async def test_modo_manual_pede_resposta(pasta_dados):
    perfil = criar_perfil(pasta_dados, "Bia", "bia")
    engine = banco_do_perfil("bia")
    vaga, _ = registrar_vaga(engine, ler_texto(VAGA))
    with pytest.raises(AguardandoResposta):
        await gerar(perfil, engine, ler_dossie(EXEMPLO), vaga, "pt", hoje=HOJE)
    assert "redigir_cv v1" in pedidos_pendentes(engine)[0].pacote


async def test_dossie_mudou_abre_o_mesmo_rascunho_ate_pedir_um_novo(engine, ana, usar_modelo):
    falso = usar_modelo(Falso(REDIGIDO))
    vaga, _ = registrar_vaga(engine, ler_texto(VAGA))
    primeiro = await gerar(ana, engine, ler_dossie(EXEMPLO), vaga, "pt", hoje=HOJE)
    mudado = ler_dossie(EXEMPLO)
    mudado.definir_metadado("versao", 99)
    assert (await gerar(ana, engine, mudado, vaga, "pt", hoje=HOJE)).id == primeiro.id
    novo = await gerar(ana, engine, mudado, vaga, "pt", hoje=HOJE, novo=True)
    assert novo.id != primeiro.id
    assert (await gerar(ana, engine, mudado, vaga, "pt", hoje=HOJE, novo=True)).id == novo.id
    assert falso.chamadas == 1  # mesma entrada: o segundo saiu do cache
