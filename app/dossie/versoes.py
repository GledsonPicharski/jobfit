"""Versões do dossiê: cada gravação sobe a versão e guarda uma cópia em `historico/`.

Toda alteração relê o arquivo do disco antes de mexer nele. Se a pessoa editou à mão
desde a última versão, essa edição vira uma versão própria, e a alteração do app é
aplicada por cima dela: nada do que foi escrito à mão se perde.
"""

import difflib
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.arquivos import gravar_texto, ler_texto
from app.dossie.estrutura import esqueleto
from app.dossie.formato import Documento, ErroDossie, escrever_dossie, ler_dossie, normalizar
from app.dossie.modelos import Fato
from app.dossie.tabelas import VersaoDossie
from app.perfis.modelos import Perfil
from app.perfis.servico import pasta_perfil


@dataclass
class Diferenca:
    adicionados: list[str] = field(default_factory=list)
    alterados: list[str] = field(default_factory=list)
    removidos: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.adicionados or self.alterados or self.removidos)


def diferenca(antes: list[Fato], depois: list[Fato]) -> Diferenca:
    """Comparação por ID: o que entrou, o que mudou e o que saiu."""
    velhos = {f.id: f.model_dump() for f in antes}
    novos = {f.id: f.model_dump() for f in depois}
    return Diferenca(
        adicionados=[i for i in novos if i not in velhos],
        alterados=[i for i in novos if i in velhos and novos[i] != velhos[i]],
        removidos=[i for i in velhos if i not in novos],
    )


def diff_texto(antes: str, depois: str) -> list[str]:
    linhas = difflib.unified_diff(
        antes.splitlines(), depois.splitlines(), "antes", "depois", lineterm="", n=2
    )
    return list(linhas)[2:]  # sem o cabeçalho "--- antes / +++ depois"


def caminho_dossie(pasta_dados: Path, slug: str) -> Path:
    return pasta_perfil(pasta_dados, slug) / "dossie.md"


def caminho_historico(pasta_dados: Path, slug: str, versao: int) -> Path:
    return pasta_perfil(pasta_dados, slug) / "historico" / f"dossie_v{versao}.md"


def _sha(texto: str) -> str:
    return hashlib.sha256(normalizar(texto).encode("utf-8")).hexdigest()


def versoes(engine: Engine) -> list[VersaoDossie]:
    """Da mais nova para a mais antiga."""
    with Session(engine) as sessao:
        return list(sessao.exec(select(VersaoDossie).order_by(VersaoDossie.versao.desc())))


def obter_versao(engine: Engine, versao: int) -> VersaoDossie | None:
    with Session(engine) as sessao:
        return sessao.exec(select(VersaoDossie).where(VersaoDossie.versao == versao)).first()


def _ultima(engine: Engine) -> VersaoDossie | None:
    with Session(engine) as sessao:
        return sessao.exec(select(VersaoDossie).order_by(VersaoDossie.versao.desc())).first()


def _fatos_da_versao(pasta_dados: Path, slug: str, versao: VersaoDossie | None) -> list[Fato]:
    if versao is None:
        return []
    arquivo = caminho_historico(pasta_dados, slug, versao.versao)
    try:
        return ler_dossie(ler_texto(arquivo)).fatos
    except (OSError, ErroDossie):
        return []


def _registrar(
    pasta_dados: Path,
    engine: Engine,
    slug: str,
    *,
    versao: int,
    texto: str,
    motivo: str,
    dif: Diferenca,
    importacao_id: int | None = None,
) -> VersaoDossie:
    gravar_texto(caminho_historico(pasta_dados, slug, versao), texto)
    registro = VersaoDossie(
        versao=versao,
        motivo=motivo,
        importacao_id=importacao_id,
        resumo=json.dumps(dif.__dict__, ensure_ascii=False),
        sha256=_sha(texto),
    )
    with Session(engine) as sessao:
        sessao.add(registro)
        sessao.commit()
        sessao.refresh(registro)
    return registro


def registrar_edicao_manual(
    pasta_dados: Path, engine: Engine, perfil: Perfil
) -> VersaoDossie | None:
    """Se o arquivo mudou fora do app desde a última versão, registra a mudança como versão."""
    arquivo = caminho_dossie(pasta_dados, perfil.slug)
    texto = normalizar(ler_texto(arquivo))
    ultima = _ultima(engine)
    if ultima is not None and ultima.sha256 == _sha(texto):
        return None
    doc = ler_dossie(texto)  # dossiê quebrado: ErroDossie, e nada é registrado
    do_arquivo = doc.metadados.get("versao")
    versao = max(
        (ultima.versao if ultima else 0) + 1, do_arquivo if isinstance(do_arquivo, int) else 0
    )
    dif = diferenca(_fatos_da_versao(pasta_dados, perfil.slug, ultima), doc.fatos)
    return _registrar(
        pasta_dados,
        engine,
        perfil.slug,
        versao=versao,
        texto=texto,
        motivo="edicao_manual",
        dif=dif,
    )


def carregar_dossie(pasta_dados: Path, engine: Engine, perfil: Perfil) -> Documento:
    """O dossiê atual do perfil; na primeira vez, cria o esqueleto como versão 1."""
    arquivo = caminho_dossie(pasta_dados, perfil.slug)
    if not arquivo.exists():
        texto = esqueleto(perfil.slug, perfil.nome)
        gravar_texto(arquivo, texto)
        _registrar(
            pasta_dados,
            engine,
            perfil.slug,
            versao=1,
            texto=texto,
            motivo="criacao",
            dif=Diferenca(),
        )
        return ler_dossie(texto)
    registrar_edicao_manual(pasta_dados, engine, perfil)
    return ler_dossie(ler_texto(arquivo))


def alterar_dossie(
    pasta_dados: Path,
    engine: Engine,
    perfil: Perfil,
    motivo: str,
    alteracao: Callable[[Documento], None],
    *,
    importacao_id: int | None = None,
) -> VersaoDossie:
    """Relê o arquivo, aplica `alteracao` e grava como versão nova (com cópia no histórico)."""
    carregar_dossie(pasta_dados, engine, perfil)  # cria, ou registra edição manual pendente
    arquivo = caminho_dossie(pasta_dados, perfil.slug)
    doc = ler_dossie(ler_texto(arquivo))
    antes = list(doc.fatos)
    alteracao(doc)  # se falhar, nada foi gravado

    ultima = _ultima(engine)
    versao = (ultima.versao if ultima else 0) + 1
    doc.definir_metadado("versao", versao)
    doc.definir_metadado("atualizado", date.today())
    texto = escrever_dossie(doc)
    ler_dossie(texto)  # o app nunca grava um dossiê que ele mesmo não consegue ler

    registro = _registrar(
        pasta_dados,
        engine,
        perfil.slug,
        versao=versao,
        texto=texto,
        motivo=motivo,
        dif=diferenca(antes, doc.fatos),
        importacao_id=importacao_id,
    )
    gravar_texto(arquivo, texto)
    return registro
