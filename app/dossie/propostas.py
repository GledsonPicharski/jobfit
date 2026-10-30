"""Propostas de alteração: nada entra no dossiê sem a pessoa aprovar (regra 4).

A montagem é toda em código: compara os candidatos com os fatos do dossiê, descarta
duplicados e o que já foi rejeitado, e marca conflitos com a sugestão da hierarquia
de fontes (dossiê confirmado > LinkedIn > CV antigo).
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.dossie.estrutura import inserir_fatos, proximo_id
from app.dossie.formato import Documento
from app.dossie.modelos import Fato, Periodo, TipoFato, normalizar_tipo, sem_acento
from app.dossie.tabelas import Importacao, Proposta, VersaoDossie
from app.dossie.versoes import alterar_dossie
from app.perfis.modelos import Perfil
from app.validacao import descrever_erro

CAMPOS_DO_FATO = (
    "tipo",
    "texto",
    "empresa",
    "cargo",
    "periodo",
    "metricas",
    "privado",
    "nao_enviar_ia",
)
DECISOES = ("pendente", "aprovada", "editada", "rejeitada")
SEMELHANCA_DUPLICADO = 0.9
SEMELHANCA_TITULO = 0.8  # palavras em comum entre dois títulos de cargo (Jaccard)

# Quanto maior, mais confiável. O que não está aqui (manual, áudio, resposta de lacuna)
# foi confirmado pela própria pessoa e fica no topo.
_PESO_FONTE = {"cv": 1, "linkedin_pdf": 2, "texto": 2}
_NOME_FONTE = {"cv": "CV antigo", "linkedin_pdf": "LinkedIn", "texto": "texto importado"}
_PESO_CONFIRMADO = 3


# Tipos que descrevem uma passagem por uma empresa ou instituição.
_TIPOS_COM_EMPRESA = ("cargo", "docencia", "mentoria")
_TIPOS_IRMAOS = {"competencia": "ferramenta", "ferramenta": "competencia"}
_PALAVRAS_VAZIAS = {"a", "o", "e", "de", "da", "do", "das", "dos", "em", "no", "na"}
_PALAVRAS_VAZIAS |= {"of", "and", "the", "at", "in", "for"}
_IDIOMAS_EN = {
    "portuguese": "portugues",
    "english": "ingles",
    "spanish": "espanhol",
    "french": "frances",
    "german": "alemao",
    "italian": "italiano",
}


class ErroProposta(ValueError):
    pass


def _normalizar(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", sem_acento(texto).casefold()).strip()


class Candidato(BaseModel):
    """Um fato que uma entrada sugere, ainda sem ID e sem aprovação."""

    tipo: TipoFato
    texto: str = Field(min_length=1)
    empresa: str | None = None
    cargo: str | None = None
    periodo: Periodo | None = None
    metricas: dict[str, str | int | float] = Field(default_factory=dict)
    privado: bool = False
    nao_enviar_ia: bool = False  # e-mail e telefone já chegam fora da IA
    fonte: str  # linkedin_pdf | cv | texto
    trecho: str | None = None
    alertas: list[str] = Field(default_factory=list)

    _tipo = field_validator("tipo", mode="before")(normalizar_tipo)

    @property
    def chave(self) -> str:
        return f"{self.tipo}:{_normalizar(self.texto)}"


@dataclass
class PropostaNova:
    acao: str  # novo | alterar | conflito
    candidato: Candidato
    sugestao: str  # aprovar | rejeitar | manter_atual | usar_nova
    fato_alvo: str | None = None
    motivo: str = ""


@dataclass
class Montagem:
    propostas: list[PropostaNova] = field(default_factory=list)
    duplicados: int = 0
    ja_rejeitados: int = 0


def _fonte_do_fato(fato: Fato) -> str:
    return (fato.origem or "manual").split()[0]


def _nome_fonte(fonte: str) -> str:
    return _NOME_FONTE.get(fonte, "dossiê confirmado por você")


def _parecidos(a: str, b: str) -> bool:
    a, b = _normalizar(a), _normalizar(b)
    return a == b or SequenceMatcher(None, a, b).ratio() >= SEMELHANCA_DUPLICADO


def _contido(parte: str | None, todo: str | None) -> bool:
    """Palavra por palavra: "R" não está contido em "Git"."""
    parte, todo = _normalizar(parte or ""), _normalizar(todo or "")
    return bool(parte) and f" {parte} " in f" {todo} "


def _mesma_empresa(a: str | None, b: str | None) -> bool:
    return _contido(a, b) or _contido(b, a)  # "QuintoAndar" e "Grupo QuintoAndar"


def _titulo(fato: Fato) -> str:
    """O cargo do fato: o campo ou, num fato escrito à mão, o começo do texto."""
    if fato.cargo:
        return fato.cargo
    return re.split(r"\s+(?:no|na|em|at)\s+|\s+[—–-]\s+|[,:(]", fato.texto, maxsplit=1)[0]


def _semelhanca_titulo(a: str, b: str) -> float:
    pa = set(_normalizar(a).split()) - _PALAVRAS_VAZIAS
    pb = set(_normalizar(b).split()) - _PALAVRAS_VAZIAS
    return len(pa & pb) / len(pa | pb) if pa and pb else 0.0


def _cargo_existente(fatos: list[Fato], cand: Candidato) -> Fato | None:
    """O mesmo cargo no dossiê: mesma empresa e mesmo início, ou mesma empresa e mesmo título."""
    if cand.tipo not in _TIPOS_COM_EMPRESA or not cand.empresa:
        return None
    da_empresa = [
        f
        for f in fatos
        if f.tipo in _TIPOS_COM_EMPRESA
        and (_mesma_empresa(f.empresa, cand.empresa) or _contido(cand.empresa, f.texto))
    ]
    da_empresa.sort(key=lambda f: f.tipo != cand.tipo)  # um cargo antes de uma docência
    inicio = cand.periodo.inicio if cand.periodo else None
    for fato in da_empresa:
        if inicio and fato.periodo and fato.periodo.inicio == inicio:
            return fato
    if not cand.cargo:
        return None
    notas = [(_semelhanca_titulo(_titulo(f), cand.cargo), f) for f in da_empresa]
    nota, fato = max(notas, key=lambda par: par[0], default=(0.0, None))
    return fato if nota >= SEMELHANCA_TITULO else None


def _idioma(texto: str) -> str:
    nome = (_normalizar(texto).split() or [""])[0]
    return _IDIOMAS_EN.get(nome, nome)


def _mesmo_ano(a: Periodo | None, b: Periodo | None) -> bool:
    if a is None or b is None or not a.inicio or not b.inicio:
        return True
    return a.inicio[:4] == b.inicio[:4]


def _ja_registrado(fato: Fato, cand: Candidato) -> bool:
    """O dossiê já diz isto, talvez com outras palavras (o dossiê costuma ser mais rico)."""
    if fato.tipo != cand.tipo and _TIPOS_IRMAOS.get(fato.tipo) != cand.tipo:
        return False
    if _parecidos(fato.texto, cand.texto) or _contido(cand.texto, fato.texto):
        return True
    sigla = re.fullmatch(r".+\(([^()]+)\)\s*", cand.texto)  # "Cascading Style Sheets (CSS)"
    if sigla and _contido(sigla.group(1), fato.texto):
        return True
    if cand.tipo == "idioma":
        return _idioma(fato.texto) == _idioma(cand.texto)
    if cand.tipo == "formacao" and cand.empresa:
        instituicao = _contido(cand.empresa, fato.texto) or _mesma_empresa(
            fato.empresa, cand.empresa
        )
        return instituicao and _mesmo_ano(fato.periodo, cand.periodo)
    return False


def _conflito(atual: Fato, cand: Candidato) -> PropostaNova:
    fonte_atual = _fonte_do_fato(atual)
    peso_atual = _PESO_FONTE.get(fonte_atual, _PESO_CONFIRMADO)
    peso_novo = _PESO_FONTE.get(cand.fonte, _PESO_CONFIRMADO)
    nome_atual, nome_novo = _nome_fonte(fonte_atual), _nome_fonte(cand.fonte)
    if peso_novo > peso_atual:
        sugestao, motivo = "usar_nova", f"O {nome_novo} prevalece sobre o {nome_atual}."
    elif peso_atual > peso_novo:
        sugestao = "manter_atual"
        motivo = f"O fato atual veio do {nome_atual}, que prevalece sobre o {nome_novo}."
    else:
        sugestao = "manter_atual"
        motivo = "As duas fontes têm o mesmo peso; na dúvida, fica o fato atual."
    return PropostaNova("conflito", cand, sugestao, atual.id, motivo)


def _comparar(fatos: list[Fato], cand: Candidato) -> PropostaNova | None:
    """None quando o candidato já está no dossiê."""
    if atual := _cargo_existente(fatos, cand):
        if cand.periodo is None or cand.periodo == atual.periodo:
            return None
        if atual.periodo is None:
            return PropostaNova(
                "alterar", cand, "aprovar", atual.id, "Completa o período do cargo."
            )
        return _conflito(atual, cand)
    if any(_ja_registrado(f, cand) for f in fatos):
        return None
    sugestao = "rejeitar" if cand.alertas else "aprovar"
    return PropostaNova("novo", cand, sugestao)


def montar_propostas(
    fatos: list[Fato], candidatos: list[Candidato], rejeitados: set[str] | None = None
) -> Montagem:
    rejeitados = rejeitados or set()
    montagem = Montagem()
    vistos: list[Candidato] = []
    for cand in candidatos:
        if cand.chave in rejeitados:
            montagem.ja_rejeitados += 1
            continue
        if any(v.tipo == cand.tipo and _parecidos(v.texto, cand.texto) for v in vistos):
            montagem.duplicados += 1
            continue
        vistos.append(cand)
        proposta = _comparar(fatos, cand)
        if proposta is None:
            montagem.duplicados += 1
        else:
            montagem.propostas.append(proposta)
    return montagem


# --- banco ----------------------------------------------------------------------


def criar_importacao(
    engine: Engine, fonte: str, nome: str, arquivo: str | None = None, status: str = "revisao"
) -> Importacao:
    importacao = Importacao(fonte=fonte, nome=nome, arquivo=arquivo, status=status)
    with Session(engine) as sessao:
        sessao.add(importacao)
        sessao.commit()
        sessao.refresh(importacao)
    return importacao


def obter_importacao(engine: Engine, importacao_id: int) -> Importacao | None:
    with Session(engine) as sessao:
        return sessao.get(Importacao, importacao_id)


def listar_importacoes(engine: Engine) -> list[Importacao]:
    with Session(engine) as sessao:
        consulta = select(Importacao).order_by(Importacao.criado_em.desc(), Importacao.id.desc())
        return list(sessao.exec(consulta))


def importacoes_em_revisao(engine: Engine) -> list[Importacao]:
    with Session(engine) as sessao:
        consulta = select(Importacao).where(Importacao.status == "revisao")
        return list(sessao.exec(consulta.order_by(Importacao.criado_em.desc())))


def registrar_propostas(engine: Engine, importacao_id: int, montagem: Montagem) -> None:
    with Session(engine) as sessao:
        importacao = sessao.get(Importacao, importacao_id)
        if importacao is None:
            raise ErroProposta("Importação não encontrada.")
        for ordem, nova in enumerate(montagem.propostas):
            cand = nova.candidato
            sessao.add(
                Proposta(
                    importacao_id=importacao_id,
                    ordem=ordem,
                    acao=nova.acao,
                    fato_alvo=nova.fato_alvo,
                    dados=cand.model_dump_json(include=set(CAMPOS_DO_FATO)),
                    chave=cand.chave,
                    trecho=cand.trecho,
                    alertas=json.dumps(cand.alertas, ensure_ascii=False),
                    sugestao=nova.sugestao,
                    motivo=nova.motivo,
                    decisao="rejeitada" if nova.sugestao == "rejeitar" else "pendente",
                )
            )
        importacao.duplicados = montagem.duplicados
        importacao.ja_rejeitados = montagem.ja_rejeitados
        importacao.status = "revisao"
        sessao.add(importacao)
        sessao.commit()


def propostas_da_importacao(engine: Engine, importacao_id: int) -> list[Proposta]:
    with Session(engine) as sessao:
        consulta = select(Proposta).where(Proposta.importacao_id == importacao_id)
        return list(sessao.exec(consulta.order_by(Proposta.ordem)))


def rejeitados_anteriores(engine: Engine) -> set[str]:
    with Session(engine) as sessao:
        consulta = select(Proposta.chave).where(
            Proposta.decisao == "rejeitada", Proposta.acao == "novo"
        )
        return set(sessao.exec(consulta))


def dados_efetivos(proposta: Proposta) -> dict[str, Any]:
    """O candidato com as edições da pessoa por cima."""
    dados = json.loads(proposta.dados)
    if proposta.decisao == "editada" and proposta.dados_editados:
        dados.update(json.loads(proposta.dados_editados))
    return {k: v for k, v in dados.items() if k in CAMPOS_DO_FATO}


def _validar(dados: dict[str, Any]) -> None:
    try:
        Fato.model_validate({**dados, "id": "F-001"})
    except ValidationError as erro:
        raise ErroProposta(
            "; ".join(descrever_erro(e, raiz="fato") for e in erro.errors())
        ) from erro


def _em_revisao(sessao: Session, importacao_id: int) -> Importacao:
    importacao = sessao.get(Importacao, importacao_id)
    if importacao is None:
        raise ErroProposta("Importação não encontrada.")
    if importacao.status != "revisao":
        raise ErroProposta("Esta importação já foi gravada ou descartada.")
    return importacao


def decidir(
    engine: Engine, proposta_id: int, decisao: str, dados_editados: dict[str, Any] | None = None
) -> Proposta:
    if decisao not in DECISOES:
        raise ErroProposta(f"Decisão desconhecida: {decisao}.")
    with Session(engine) as sessao:
        proposta = sessao.get(Proposta, proposta_id)
        if proposta is None:
            raise ErroProposta("Proposta não encontrada.")
        _em_revisao(sessao, proposta.importacao_id)
        proposta.decisao = decisao
        proposta.dados_editados = None
        if decisao == "editada":
            editados = {k: v for k, v in (dados_editados or {}).items() if k in CAMPOS_DO_FATO}
            _validar({**json.loads(proposta.dados), **editados})
            proposta.dados_editados = json.dumps(editados, ensure_ascii=False)
        sessao.add(proposta)
        sessao.commit()
        sessao.refresh(proposta)
        return proposta


def _aplicar(doc: Documento, aceitas: list[Proposta], origem: str) -> None:
    for proposta in aceitas:
        dados = dados_efetivos(proposta)
        if proposta.acao == "novo":
            fato = Fato.model_validate({**dados, "id": proximo_id(doc), "origem": origem})
            inserir_fatos(doc, [fato])
            continue
        try:
            alvo = doc.fato(proposta.fato_alvo or "")
        except KeyError as erro:
            raise ErroProposta(
                f"O fato {proposta.fato_alvo} não existe mais no dossiê; descarte esta proposta."
            ) from erro
        periodo = Periodo.model_validate(dados["periodo"]) if dados.get("periodo") else None
        doc.substituir_fato(alvo.model_copy(update={"periodo": periodo, "origem": origem}))


def aplicar_importacao(
    pasta_dados: Path, engine: Engine, perfil: Perfil, importacao_id: int
) -> VersaoDossie | None:
    """Grava as propostas aprovadas e editadas numa versão nova; None se nada foi aceito."""
    with Session(engine) as sessao:
        importacao = _em_revisao(sessao, importacao_id)
        fonte = importacao.fonte
    propostas = propostas_da_importacao(engine, importacao_id)
    pendentes = [p for p in propostas if p.decisao == "pendente"]
    if pendentes:
        raise ErroProposta(
            f"{len(pendentes)} proposta(s) pendente(s): aprove, edite ou rejeite antes de gravar."
        )
    aceitas = [p for p in propostas if p.decisao in ("aprovada", "editada")]
    versao = None
    if aceitas:
        origem = f"{fonte} {date.today().isoformat()}"
        versao = alterar_dossie(
            pasta_dados,
            engine,
            perfil,
            "importacao",
            lambda doc: _aplicar(doc, aceitas, origem),
            importacao_id=importacao_id,
        )
    with Session(engine) as sessao:
        importacao = _em_revisao(sessao, importacao_id)
        importacao.status = "aplicada"
        importacao.versao_aplicada = versao.versao if versao else None
        sessao.add(importacao)
        sessao.commit()
    return versao
