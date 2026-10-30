"""Perfis na pasta de dados: `perfis/<slug>/perfil.json` mais as subpastas do perfil."""

import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from app.arquivos import gravar_texto, ler_texto
from app.perfis.modelos import Perfil

log = logging.getLogger(__name__)

# O slug vira nome de pasta e de arquivo; a regra também impede "..", barras e afins.
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_RESERVADOS_WINDOWS = {"con", "prn", "aux", "nul"} | {
    f"{base}{n}" for base in ("com", "lpt") for n in range(1, 10)
}
_SUBPASTAS = ("historico", "fontes", "cvs")


class ErroPerfil(ValueError):
    pass


def validar_slug(slug: str) -> str:
    if not _SLUG.fullmatch(slug) or slug in _RESERVADOS_WINDOWS:
        raise ErroPerfil(
            f"Identificador de perfil inválido: {slug!r}. "
            "Use até 40 letras minúsculas sem acento, números e hífens."
        )
    return slug


def slug_de_nome(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")[:40].rstrip("-")


def pasta_perfil(pasta_dados: Path, slug: str) -> Path:
    return pasta_dados / "perfis" / validar_slug(slug)


def _arquivo_perfil(pasta_dados: Path, slug: str) -> Path:
    return pasta_perfil(pasta_dados, slug) / "perfil.json"


def salvar_perfil(pasta_dados: Path, perfil: Perfil) -> None:
    gravar_texto(_arquivo_perfil(pasta_dados, perfil.slug), perfil.model_dump_json(indent=2) + "\n")


def criar_perfil(pasta_dados: Path, nome: str, slug: str | None = None) -> Perfil:
    nome = nome.strip()
    if not nome:
        raise ErroPerfil("Informe o nome do perfil.")
    slug = validar_slug(slug or slug_de_nome(nome))
    if _arquivo_perfil(pasta_dados, slug).exists():
        raise ErroPerfil(f"O perfil {slug!r} já existe.")

    perfil = Perfil(slug=slug, nome=nome, criado_em=datetime.now().astimezone())
    for sub in _SUBPASTAS:
        (pasta_perfil(pasta_dados, slug) / sub).mkdir(parents=True, exist_ok=True)
    salvar_perfil(pasta_dados, perfil)
    return perfil


def carregar_perfil(pasta_dados: Path, slug: str) -> Perfil:
    arquivo = _arquivo_perfil(pasta_dados, slug)
    if not arquivo.exists():
        raise ErroPerfil(f"Perfil {slug!r} não encontrado em {arquivo.parent}.")
    return Perfil.model_validate_json(ler_texto(arquivo))


def listar_perfis(pasta_dados: Path) -> list[Perfil]:
    raiz = pasta_dados / "perfis"
    if not raiz.is_dir():
        return []
    perfis = []
    for pasta in sorted(raiz.iterdir()):
        if not (pasta / "perfil.json").is_file():
            continue
        try:
            perfis.append(carregar_perfil(pasta_dados, pasta.name))
        except (ErroPerfil, ValidationError) as erro:
            log.warning("Perfil ignorado em %s: %s", pasta, type(erro).__name__)
    return sorted(perfis, key=lambda p: p.nome.casefold())
