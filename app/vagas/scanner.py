"""Scanner de portais (decisão 0009): lê, deduplica, filtra e ordena vagas, sem IA.

    buscas salvas → portais (um por vez; erro num não para os outros)
      → deduplicação → filtros da busca e do perfil → pré-nota → vaga "nova" com origens

Também reconfere, a cada rodada, um punhado de vagas que podem ter fechado.
"""

import hashlib
import importlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session, or_, select

from app.arquivos import ler_texto
from app.dossie.versoes import carregar_dossie
from app.ia.modelos import agora_utc
from app.perfis.modelos import Perfil
from app.vagas.buscas import FiltrosBusca, aplicar_busca, filtros_de, listar_buscas, titulo_casa
from app.vagas.catalogo import carregar_catalogo
from app.vagas.dedup import Candidata, Indice
from app.vagas.filtros import aplicar_filtros
from app.vagas.leitura import VagaBruta, novo_cliente
from app.vagas.metadados import extrair_metadados
from app.vagas.portais import Consulta, ErroPortal
from app.vagas.prenota import calcular_prenota, carregar_vocabulario, termos_do_dossie
from app.vagas.servico import hash_texto, nova_vaga
from app.vagas.tabelas import Busca, ConsultaPortal, PortalPerfil, Vaga, VagaOrigem, Varredura

log = logging.getLogger(__name__)

CONFIG_PADRAO = Path(__file__).resolve().parents[2] / "config" / "scanner.yaml"
_RECONFERIR = ("nova", "avaliada", "quero_aplicar")


class ErroScanner(ValueError):
    pass


class ConfigScanner(BaseModel):
    prenota_minima: int
    pausa_segundos: float
    intervalo_horas: float
    intervalo_por_portal: dict[str, float] = {}
    reconferir_por_rodada: int
    reconferir_apos_dias: int
    idade_maxima_dias: int

    def intervalo(self, portal: str) -> timedelta:
        return timedelta(hours=self.intervalo_por_portal.get(portal, self.intervalo_horas))


def carregar_config(caminho: Path = CONFIG_PADRAO) -> ConfigScanner:
    return ConfigScanner.model_validate(yaml.safe_load(ler_texto(caminho)))


@dataclass
class ResultadoPortal:
    trazidas: int = 0
    novas: int = 0
    repetidas: int = 0
    filtradas: int = 0
    antigas: int = 0
    erro: str | None = None
    pulado: str | None = None  # consultado há pouco: intervalo mínimo
    avisos: list[str] = field(default_factory=list)


def resumo_por_portal(varredura: Varredura) -> dict[str, ResultadoPortal]:
    dados = json.loads(varredura.portais)
    return {p: ResultadoPortal(**r) for p, r in dados.items() if not p.startswith("_")}


def linhas_do_resumo(varredura: Varredura, nomes: dict[str, str] | None = None) -> list[str]:
    """O resultado de uma rodada em linhas de texto (linha de comando e registro)."""
    nomes = nomes or {}
    linhas = []
    for portal, r in resumo_por_portal(varredura).items():
        nome = nomes.get(portal, portal)
        if r.pulado:
            linhas.append(f"{nome}: consultado há pouco; fica para a próxima rodada.")
        elif r.erro:
            linhas.append(f"{nome}: erro — {r.erro}.")
        else:
            linhas.append(
                f"{nome}: {r.trazidas} trazida(s), {r.novas} nova(s), {r.repetidas} repetida(s), "
                f"{r.filtradas} barrada(s) pelos filtros, {r.antigas} antiga(s)."
            )
        linhas += [f"  aviso: {a}" for a in r.avisos]
    encerradas = json.loads(varredura.portais).get("_encerradas", 0)
    linhas.append(f"Vagas novas: {varredura.novas}. Vagas que fecharam: {encerradas}.")
    return linhas


# --- portais do perfil ----------------------------------------------------------


def portais_do_perfil(engine: Engine) -> dict[str, PortalPerfil]:
    with Session(engine) as sessao:
        return {p.portal: p for p in sessao.exec(select(PortalPerfil))}


def ligar_portal(engine: Engine, portal: str, ligado: bool) -> None:
    with Session(engine) as sessao:
        registro = sessao.get(PortalPerfil, portal) or PortalPerfil(portal=portal)
        registro.desligado = not ligado
        sessao.add(registro)
        sessao.commit()


# --- uma rodada -----------------------------------------------------------------


def _carregar_leitor(nome: str):
    return importlib.import_module(f"app.vagas.portais.{nome}")


def _indice(sessao: Session) -> Indice:
    indice = Indice()
    for vaga in sessao.exec(select(Vaga)):
        indice.adicionar(
            vaga.id, Candidata(vaga.url, vaga.empresa, vaga.titulo, vaga.local, vaga.hash_texto)
        )
    for origem in sessao.exec(select(VagaOrigem).where(VagaOrigem.url.is_not(None))):
        indice.adicionar(origem.vaga_id, Candidata(origem.url, None, None, None, None))
    return indice


def _chave_consulta(portal: str, titulos: list[str]) -> str:
    resumo = hashlib.sha256("|".join(sorted(titulos)).encode("utf-8")).hexdigest()[:16]
    return f"{portal}|{resumo}"


def _data(texto: str | None) -> datetime | None:
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def _registrar_origem(
    sessao: Session, vaga_id: int, portal: str, url: str | None, busca_id, agora
) -> None:
    consulta = select(VagaOrigem).where(VagaOrigem.vaga_id == vaga_id, VagaOrigem.portal == portal)
    origem = sessao.exec(consulta).first()
    if origem is None:
        origem = VagaOrigem(vaga_id=vaga_id, portal=portal, primeira_vez=agora)
    origem.url = url or origem.url
    origem.busca_id = origem.busca_id or busca_id
    origem.ultima_vez = agora
    sessao.add(origem)


def _busca_que_aceita(
    bruta: VagaBruta, portal: str, buscas: list[tuple[Busca, FiltrosBusca]], perfil: Perfil
) -> int | None:
    """A primeira busca que aceita a vaga; None se nenhuma aceita (ou o perfil barra)."""
    meta = extrair_metadados(bruta.texto, bruta.estruturado)
    if aplicar_filtros(meta, bruta.texto, perfil.criterios, None).bloqueada:
        return None
    restricoes = bruta.estruturado.get("restricoes") or (
        [meta.local] if meta.modalidade == "remoto" and meta.local else []
    )
    for busca, filtros in buscas:
        if filtros.portais and portal not in filtros.portais:
            continue
        if not titulo_casa(meta.titulo, filtros.titulos):
            continue
        if not aplicar_busca(meta, bruta.texto, restricoes, filtros).bloqueada:
            return busca.id
    return None


def varrer(
    perfil: Perfil,
    engine: Engine,
    pasta_dados: Path,
    *,
    origem: str = "tela",
    busca_id: int | None = None,
    leitores: dict | None = None,
    config: ConfigScanner | None = None,
    agora: datetime | None = None,
    cliente=None,
) -> Varredura:
    """Uma rodada do scan. Não chama a IA em momento nenhum (regra 1, decisão 0009)."""
    config = config or carregar_config()
    agora = agora or agora_utc()
    buscas = [b for b in listar_buscas(engine, so_ativas=True) if busca_id in (None, b.id)]
    if not buscas:
        raise ErroScanner("Crie uma busca salva (e deixe-a ativa) antes de rodar o scan.")
    filtros = [(b, filtros_de(b)) for b in buscas]
    catalogo = carregar_catalogo(pasta_dados)
    desligados = {p for p, r in portais_do_perfil(engine).items() if r.desligado}
    pedidos = {p for _, f in filtros for p in f.portais} or {p.id for p in catalogo.ativos()}
    portais = [p for p in catalogo.ativos() if p.id in pedidos and p.id not in desligados]
    titulos = sorted({t for _, f in filtros for t in f.titulos})

    doc = carregar_dossie(pasta_dados, engine, perfil)
    termos, vocab = termos_do_dossie(doc.fatos, carregar_vocabulario())

    with Session(engine, expire_on_commit=False) as sessao:
        varredura = Varredura(inicio=agora, origem=origem)
        sessao.add(varredura)
        sessao.commit()

    resultados: dict[str, ResultadoPortal] = {}
    http = cliente or novo_cliente()
    try:
        for portal in portais:
            resultados[portal.id] = _rodar_portal(
                portal.id,
                (leitores or {}).get(portal.id) or _carregar_leitor(portal.leitor),
                titulos,
                catalogo.empresas,
                filtros,
                perfil,
                engine,
                http,
                config,
                agora,
                termos,
                vocab,
            )
        encerradas = _reconferir(engine, leitores or {}, catalogo, http, config, agora)
    finally:
        if cliente is None:
            http.close()

    with Session(engine, expire_on_commit=False) as sessao:
        varredura = sessao.get(Varredura, varredura.id)
        varredura.fim = max(agora_utc(), agora)
        varredura.portais = json.dumps(
            {p: asdict(r) for p, r in resultados.items()} | {"_encerradas": encerradas},
            ensure_ascii=False,
        )
        varredura.novas = sum(r.novas for r in resultados.values())
        varredura.erros = sum(1 for r in resultados.values() if r.erro)
        rodaram = [r for r in resultados.values() if not r.pulado]
        falhou = rodaram and all(r.erro for r in rodaram)
        varredura.estado = "falhou" if falhou else "concluida"
        sessao.add(varredura)
        sessao.commit()
        return varredura


def _rodar_portal(
    portal: str,
    leitor,
    titulos: list[str],
    empresas,
    filtros,
    perfil: Perfil,
    engine: Engine,
    http,
    config: ConfigScanner,
    agora: datetime,
    termos,
    vocab,
) -> ResultadoPortal:
    resultado = ResultadoPortal()
    chave = _chave_consulta(portal, titulos)
    with Session(engine) as sessao:
        ultima = sessao.get(ConsultaPortal, chave)
    if ultima and ultima.feita_em + config.intervalo(portal) > agora:
        resultado.pulado = ultima.feita_em.isoformat()
        return resultado

    consulta = Consulta(titulos=titulos, empresas=empresas, pausa=config.pausa_segundos)
    try:
        brutas = leitor.buscar(consulta, http)
    except ErroPortal as erro:
        resultado.erro = str(erro)
        return resultado
    except Exception as erro:  # um leitor quebrado não derruba a rodada
        log.exception("leitor %s falhou", portal)
        resultado.erro = f"erro inesperado no leitor ({type(erro).__name__})"
        return resultado
    resultado.avisos = consulta.avisos

    limite = agora - timedelta(days=config.idade_maxima_dias)
    with Session(engine) as sessao:
        indice = _indice(sessao)
        for bruta in brutas:
            resultado.trazidas += 1
            dados = bruta.estruturado
            candidata = Candidata(
                bruta.url, dados.get("empresa"), dados.get("titulo"), dados.get("local"),
                hash_texto(bruta.texto),
            )  # fmt: skip
            if (existente := indice.procurar(candidata)) is not None:
                resultado.repetidas += 1
                _registrar_origem(sessao, existente, portal, bruta.url, None, agora)
                continue
            publicada = _data(dados.get("publicada_em"))
            if publicada and publicada < limite:
                resultado.antigas += 1
                continue
            busca_id = _busca_que_aceita(bruta, portal, filtros, perfil)
            if busca_id is None:
                resultado.filtradas += 1
                continue
            vaga = nova_vaga(
                bruta,
                estado="nova",
                prenota=calcular_prenota(bruta.texto, termos, vocab).valor,
                publicada_em=publicada,
                aberta=True,
                checada_em=agora,
                criado_em=agora,
            )
            sessao.add(vaga)
            sessao.flush()
            _registrar_origem(sessao, vaga.id, portal, bruta.url, busca_id, agora)
            indice.adicionar(vaga.id, candidata)
            resultado.novas += 1
        sessao.merge(ConsultaPortal(chave=chave, feita_em=agora))
        sessao.commit()
    return resultado


def _reconferir(engine: Engine, leitores: dict, catalogo, http, config, agora) -> int:
    """Confere se algumas vagas ainda estão abertas; devolve quantas fecharam."""
    leitor_de = {p.id: p.leitor for p in catalogo.ativos()}
    corte = agora - timedelta(days=config.reconferir_apos_dias)
    with Session(engine) as sessao:
        consulta = (
            select(Vaga)
            .where(Vaga.url.is_not(None), Vaga.estado.in_(_RECONFERIR))
            .where(or_(Vaga.aberta.is_(None), Vaga.aberta))
            .where(or_(Vaga.checada_em.is_(None), Vaga.checada_em < corte))
            .where(Vaga.fonte.in_(list(leitor_de)))
            .order_by(Vaga.checada_em.is_not(None), Vaga.checada_em)
            .limit(config.reconferir_por_rodada)
        )
        encerradas = 0
        for vaga in sessao.exec(consulta).all():
            leitor = leitores.get(vaga.fonte) or _carregar_leitor(leitor_de[vaga.fonte])
            try:
                aberta = leitor.ainda_aberta(vaga.url, http)
            except Exception:  # sem resposta: confere na próxima rodada
                log.info("não deu para conferir a vaga %s", vaga.id, exc_info=True)
                continue
            vaga.aberta, vaga.checada_em = aberta, agora
            if not aberta:
                vaga.encerrada_em = agora
                encerradas += 1
            sessao.add(vaga)
        sessao.commit()
    return encerradas
