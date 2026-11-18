"""Scanner: portais → deduplicação → filtros → vagas novas, sem nenhuma chamada de IA."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db import banco_do_perfil
from app.dossie.versoes import caminho_dossie
from app.ia.modelos import ChamadaIA
from app.perfis.servico import criar_perfil
from app.vagas.buscas import salvar_busca
from app.vagas.leitura import VagaBruta
from app.vagas.portais import ErroPortal
from app.vagas.scanner import ConfigScanner, ErroScanner, varrer
from app.vagas.servico import registrar_vaga
from app.vagas.tabelas import Vaga, VagaOrigem, Varredura

RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = (RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8")
AGORA = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
CONFIG = ConfigScanner(
    prenota_minima=30,
    pausa_segundos=0,
    intervalo_horas=1,
    intervalo_por_portal={"remotive": 6},
    reconferir_por_rodada=20,
    reconferir_apos_dias=7,
    idade_maxima_dias=45,
)


def _bruta(portal, url, titulo, empresa, texto="", **extra) -> VagaBruta:
    estruturado = {"titulo": titulo, "empresa": empresa, "modalidade": "remoto"} | extra
    corpo = f"{titulo}\n\nVaga remota. Experiência com Python, SQL e liderança. {texto}"
    return VagaBruta(corpo, portal, url, estruturado)


class Falso:
    """Um leitor de mentira: devolve o que mandarem e conta as chamadas."""

    def __init__(self, vagas=None, erro=None, abertas=True):
        self.vagas, self.erro, self.abertas = vagas or [], erro, abertas
        self.chamadas = 0
        self.consultas = []

    def buscar(self, consulta, cliente):
        self.chamadas += 1
        self.consultas.append(consulta)
        if self.erro:
            raise self.erro
        return list(self.vagas)

    def ainda_aberta(self, url, cliente):
        return self.abertas


@pytest.fixture
def ana(pasta_dados):
    perfil = criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    caminho_dossie(pasta_dados, "ana").write_text(EXEMPLO, encoding="utf-8")
    return perfil


@pytest.fixture
def engine(ana):
    engine = banco_do_perfil("ana")
    salvar_busca(
        engine,
        nome="Dados",
        titulos=["Gerente de Dados", "Head of Data"],
        so_remoto=True,
        paises=["Brasil"],
        portais=["greenhouse", "remotive"],
    )
    return engine


def _varrer(ana, engine, pasta_dados, leitores, agora=AGORA):
    return varrer(
        ana, engine, pasta_dados, origem="cli", leitores=leitores, config=CONFIG, agora=agora
    )


def _vagas(engine) -> list[Vaga]:
    with Session(engine) as sessao:
        return list(sessao.exec(select(Vaga).order_by(Vaga.id)))


def _origens(engine, vaga_id) -> list[str]:
    with Session(engine) as sessao:
        consulta = select(VagaOrigem.portal).where(VagaOrigem.vaga_id == vaga_id)
        return sorted(sessao.exec(consulta))


def test_vagas_novas_sem_duplicar_entre_portais_e_rodadas(ana, engine, pasta_dados):
    gh = Falso(
        [
            _bruta("greenhouse", "https://job-boards.greenhouse.io/clara/jobs/1",
                   "Head of Data", "Clara"),
            _bruta("greenhouse", "https://job-boards.greenhouse.io/clara/jobs/2",
                   "Gerente de Dados", "Clara"),
        ]
    )  # fmt: skip
    remotive = Falso(
        [_bruta("remotive", "https://remotive.com/remote-jobs/data/head-of-data-1",
                "Head of Data (Remote)", "Clara Inc.")]
    )  # fmt: skip
    leitores = {"greenhouse": gh, "remotive": remotive}

    varredura = _varrer(ana, engine, pasta_dados, leitores)
    vagas = _vagas(engine)
    assert len(vagas) == 2 and varredura.novas == 2
    assert all(v.estado == "nova" for v in vagas)
    assert all(v.prenota is not None for v in vagas)
    head = next(v for v in vagas if v.titulo == "Head of Data")
    assert _origens(engine, head.id) == ["greenhouse", "remotive"]
    portais = json.loads(varredura.portais)
    assert portais["remotive"]["repetidas"] == 1 and portais["greenhouse"]["novas"] == 2
    assert gh.consultas[0].titulos == ["Gerente de Dados", "Head of Data"]

    # duas horas depois: o Greenhouse roda de novo, a Remotive ainda não (6 horas)
    _varrer(ana, engine, pasta_dados, leitores, agora=AGORA + timedelta(hours=2))
    assert len(_vagas(engine)) == 2
    assert (gh.chamadas, remotive.chamadas) == (2, 1)


def test_vaga_colada_antes_nao_se_repete(ana, engine, pasta_dados):
    colada, _ = registrar_vaga(
        engine,
        VagaBruta("Head of Data\n\nTexto colado.", "greenhouse",
                  "https://job-boards.greenhouse.io/clara/jobs/1", {}),
    )  # fmt: skip
    gh = Falso(
        [_bruta("greenhouse", "https://job-boards.greenhouse.io/clara/jobs/1?gh_src=x",
                "Head of Data", "Clara")]
    )  # fmt: skip
    _varrer(ana, engine, pasta_dados, {"greenhouse": gh, "remotive": Falso()})
    assert [v.id for v in _vagas(engine)] == [colada.id]
    assert _origens(engine, colada.id) == ["colada", "greenhouse"]
    assert _vagas(engine)[0].estado == "avaliada"  # a pessoa já tinha trazido: não vira "nova"


def test_erro_num_portal_nao_para_os_outros(ana, engine, pasta_dados):
    gh = Falso(erro=ErroPortal("respondeu com erro 503"))
    remotive = Falso(
        [_bruta("remotive", "https://remotive.com/remote-jobs/x/1", "Head of Data", "Stone")]
    )
    varredura = _varrer(ana, engine, pasta_dados, {"greenhouse": gh, "remotive": remotive})
    portais = json.loads(varredura.portais)
    assert portais["greenhouse"]["erro"] == "respondeu com erro 503"
    assert portais["remotive"]["novas"] == 1
    assert varredura.estado == "concluida" and varredura.erros == 1


def test_erro_inesperado_tambem_vira_erro_do_portal(ana, engine, pasta_dados):
    gh = Falso(erro=KeyError("title"))
    varredura = _varrer(ana, engine, pasta_dados, {"greenhouse": gh, "remotive": Falso()})
    assert "inesperado" in json.loads(varredura.portais)["greenhouse"]["erro"]


def test_filtros_da_busca_e_do_perfil_barram_sem_gravar(ana, engine, pasta_dados):
    salvar_busca(
        engine, busca_id=1, nome="Dados", titulos=["Head of Data"], so_remoto=True,
        paises=["Brasil"], empresas_excluidas=["Evitada"], portais=["greenhouse"],
    )  # fmt: skip
    gh = Falso(
        [
            _bruta("greenhouse", "https://g/1", "Head of Data", "Evitada"),
            _bruta("greenhouse", "https://g/2", "Head of Data", "Só EUA",
                   restricoes=["United States"]),
            _bruta("greenhouse", "https://g/3", "Head of Data", "Híbrida", modalidade="hibrido"),
            _bruta("greenhouse", "https://g/4", "Head of Data", "Boa"),
        ]
    )  # fmt: skip
    varredura = _varrer(ana, engine, pasta_dados, {"greenhouse": gh})
    assert [v.empresa for v in _vagas(engine)] == ["Boa"]
    assert json.loads(varredura.portais)["greenhouse"]["filtradas"] == 3


def test_vaga_antiga_nao_entra(ana, engine, pasta_dados):
    antiga = (AGORA - timedelta(days=90)).isoformat()
    gh = Falso([_bruta("greenhouse", "https://g/1", "Head of Data", "Clara", publicada_em=antiga)])
    varredura = _varrer(ana, engine, pasta_dados, {"greenhouse": gh, "remotive": Falso()})
    assert _vagas(engine) == []
    assert json.loads(varredura.portais)["greenhouse"]["antigas"] == 1


def test_scan_nao_chama_a_ia(ana, engine, pasta_dados):
    gh = Falso([_bruta("greenhouse", "https://g/1", "Head of Data", "Clara")])
    _varrer(ana, engine, pasta_dados, {"greenhouse": gh, "remotive": Falso()})
    with Session(engine) as sessao:
        assert sessao.exec(select(ChamadaIA)).all() == []


def test_reconfere_e_marca_vaga_encerrada(ana, engine, pasta_dados):
    gh = Falso([_bruta("greenhouse", "https://g/1", "Head of Data", "Clara")])
    _varrer(ana, engine, pasta_dados, {"greenhouse": gh, "remotive": Falso()})
    [vaga] = _vagas(engine)
    assert vaga.aberta is True

    fechou = Falso(abertas=False)
    depois = AGORA + timedelta(days=8)
    _varrer(ana, engine, pasta_dados, {"greenhouse": fechou, "remotive": Falso()}, agora=depois)
    [vaga] = _vagas(engine)
    assert vaga.aberta is False
    assert vaga.encerrada_em.date() == depois.date()


def test_sem_busca_ativa_avisa(ana, pasta_dados):
    with pytest.raises(ErroScanner, match="busca"):
        varrer(ana, banco_do_perfil("ana"), pasta_dados, leitores={}, config=CONFIG)


def test_varredura_registrada(ana, engine, pasta_dados):
    _varrer(ana, engine, pasta_dados, {"greenhouse": Falso(), "remotive": Falso()})
    with Session(engine) as sessao:
        [varredura] = sessao.exec(select(Varredura)).all()
    assert varredura.origem == "cli" and varredura.fim is not None


def test_resumo_em_texto(ana, engine, pasta_dados):
    from app.vagas.scanner import linhas_do_resumo

    gh = Falso([_bruta("greenhouse", "https://g/1", "Head of Data", "Clara")])
    remotive = Falso(erro=ErroPortal("sem resposta (ConnectError)"))
    varredura = _varrer(ana, engine, pasta_dados, {"greenhouse": gh, "remotive": remotive})
    linhas = linhas_do_resumo(varredura, {"greenhouse": "Greenhouse", "remotive": "Remotive"})
    assert linhas[0].startswith("Greenhouse: 1 trazida(s), 1 nova(s)")
    assert linhas[1] == "Remotive: erro — sem resposta (ConnectError)."
    assert linhas[-1] == "Vagas novas: 1. Vagas que fecharam: 0."


def test_cli_scan(ana, engine, pasta_dados, monkeypatch):
    from typer.testing import CliRunner

    from app import config
    from app.cli import cli
    from app.vagas import scanner

    config.salvar_config(config.carregar_config().model_copy(update={"ultimo_perfil": "ana"}))
    gh = Falso([_bruta("greenhouse", "https://g/1", "Head of Data", "Clara")])
    original = scanner.varrer

    def varrer_falso(*args, **kwargs):
        return original(*args, **kwargs, leitores={"greenhouse": gh, "remotive": Falso()})

    monkeypatch.setattr(scanner, "varrer", varrer_falso)
    saida = CliRunner().invoke(cli, ["scan"])
    assert saida.exit_code == 0, saida.output
    assert "Greenhouse: 1 trazida(s), 1 nova(s)" in saida.output
    assert "Vagas novas: 1." in saida.output


def test_portal_desligado_pelo_perfil_nao_roda(ana, engine, pasta_dados):
    from app.vagas.scanner import ligar_portal

    ligar_portal(engine, "remotive", False)
    remotive = Falso()
    _varrer(ana, engine, pasta_dados, {"greenhouse": Falso(), "remotive": remotive})
    assert remotive.chamadas == 0
