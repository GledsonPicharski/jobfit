"""Catálogo de portais e empresas-alvo (decisão 0009).

O catálogo do repositório (`catalogo/`) é público e igual para todos. O que a pessoa
acrescenta fica em `catalogo_local.yaml`, na pasta de dados, e nunca vai para o repositório.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.arquivos import gravar_texto, ler_texto
from app.perfis.servico import slug_de_nome
from app.validacao import descrever_erro

PASTA_CATALOGO = Path(__file__).resolve().parents[2] / "catalogo"
ARQUIVO_LOCAL = "catalogo_local.yaml"

Categoria = Literal[
    "vagas",
    "freela",
    "treinamento_ia",
    "expert_network",
    "docencia",
    "mentoria",
    "headhunter",
    "relocacao",
]
ModoLeitura = Literal[
    "api", "feed", "pagina_publica", "alerta_email", "lembrete", "contato", "manual"
]
Ats = Literal["greenhouse", "lever", "ashby"]

CATEGORIAS: dict[str, str] = {
    "vagas": "Vagas",
    "freela": "Freela e alocação",
    "treinamento_ia": "Treinamento de IA",
    "expert_network": "Expert network",
    "docencia": "Docência",
    "mentoria": "Mentoria",
    "headhunter": "Headhunter",
    "relocacao": "Relocação",
}
MODOS: dict[str, str] = {
    "api": "API pública",
    "feed": "Feed",
    "pagina_publica": "Página pública",
    "alerta_email": "Alerta por e-mail",
    "lembrete": "Lembrete (exige login)",
    "contato": "Contato",
    "manual": "Manual",
}
_AUTOMATICOS = ("api", "feed", "pagina_publica")


class ErroCatalogo(ValueError):
    pass


class Portal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    nome: str = Field(min_length=1)
    categoria: Categoria
    regiao: list[str] = Field(default_factory=list)
    url: str | None = None
    modo_leitura: ModoLeitura
    leitor: str | None = None
    por_empresa: bool = False
    precisa_login: bool = False
    status: Literal["ativo", "em_validacao", "descartado"] = "ativo"
    motivo_descarte: str | None = None
    foco: str | None = None
    adicionado_por: str = "sistema"
    frequencia_dias: int | None = Field(default=None, ge=1)  # sugestão para o lembrete

    @property
    def automatico(self) -> bool:
        """Lido em código pelo scan (os outros viram lembrete)."""
        return self.modo_leitura in _AUTOMATICOS and self.leitor is not None


class Empresa(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    nome: str = Field(min_length=1)
    ats: Ats
    quadro: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$", max_length=80)
    regiao: list[str] = Field(default_factory=list)
    local: bool = False  # acrescentada pela pessoa


class _Local(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portais: list[Portal] = Field(default_factory=list)
    empresas: list[Empresa] = Field(default_factory=list)


@dataclass(frozen=True)
class Catalogo:
    portais: list[Portal]
    empresas: list[Empresa]

    def portal(self, portal_id: str) -> Portal:
        for portal in self.portais:
            if portal.id == portal_id:
                return portal
        raise KeyError(portal_id)

    def ativos(self) -> list[Portal]:
        """Os portais que o scan lê."""
        return [p for p in self.portais if p.status == "ativo" and p.automatico]

    def lembretes(self) -> list[Portal]:
        """Os que a pessoa checa à mão: login, alerta por e-mail, contato, manual."""
        return [p for p in self.portais if p.status == "ativo" and not p.automatico]

    def empresas_do(self, ats: str) -> list[Empresa]:
        return [e for e in self.empresas if e.ats == ats]


def _ler_yaml(caminho: Path):
    try:
        return yaml.safe_load(ler_texto(caminho))
    except yaml.YAMLError as erro:
        raise ErroCatalogo(f"{caminho.name} não é um YAML válido: {erro}") from erro


def _validar(modelo, dados, nome: str):
    try:
        return modelo.model_validate(dados)
    except ValidationError as erro:
        detalhes = "; ".join(descrever_erro(e, nome) for e in erro.errors())
        raise ErroCatalogo(f"{nome} inválido: {detalhes}") from erro


def _ler_local(pasta_dados: Path | None) -> _Local:
    if pasta_dados is None or not (pasta_dados / ARQUIVO_LOCAL).is_file():
        return _Local()
    dados = _ler_yaml(pasta_dados / ARQUIVO_LOCAL) or {}
    return _validar(_Local, dados, ARQUIVO_LOCAL)


def carregar_catalogo(pasta_dados: Path | None = None) -> Catalogo:
    portais = [
        _validar(Portal, p, "portais.yaml") for p in _ler_yaml(PASTA_CATALOGO / "portais.yaml")
    ]
    empresas = [
        _validar(Empresa, e, "empresas.yaml") for e in _ler_yaml(PASTA_CATALOGO / "empresas.yaml")
    ]
    local = _ler_local(pasta_dados)
    ids = {p.id for p in portais}
    portais += [p for p in local.portais if p.id not in ids]
    quadros = {(e.ats, e.quadro.lower()) for e in empresas}
    empresas += [
        e.model_copy(update={"local": True})
        for e in local.empresas
        if (e.ats, e.quadro.lower()) not in quadros
    ]
    repetidos = {p.id for p in portais if sum(q.id == p.id for q in portais) > 1}
    if repetidos:
        raise ErroCatalogo(f"Portais repetidos no catálogo: {', '.join(sorted(repetidos))}.")
    return Catalogo(portais, empresas)


def _gravar_local(pasta_dados: Path, local: _Local) -> None:
    dados = local.model_dump(mode="json", exclude_defaults=True)
    gravar_texto(
        pasta_dados / ARQUIVO_LOCAL,
        "# Portais e empresas que você acrescentou ao catálogo do JobFit.\n"
        + yaml.safe_dump(dados, allow_unicode=True, sort_keys=False),
    )


def acrescentar_empresa(pasta_dados: Path, *, nome: str, ats: str, quadro: str) -> Empresa:
    empresa = _validar(
        Empresa, {"nome": nome.strip(), "ats": ats, "quadro": quadro.strip()}, "empresa"
    )
    local = _ler_local(pasta_dados)
    if all((e.ats, e.quadro.lower()) != (ats, empresa.quadro.lower()) for e in local.empresas):
        local.empresas.append(empresa)
        _gravar_local(pasta_dados, local)
    return empresa


def acrescentar_portal(
    pasta_dados: Path,
    *,
    nome: str,
    url: str | None = None,
    categoria: str = "vagas",
    frequencia_dias: int | None = 7,
) -> Portal:
    """Um portal para checar à mão (lembrete); portais com leitor entram pelo repositório."""
    portal_id = slug_de_nome(nome)
    if not portal_id:
        raise ErroCatalogo("Dê um nome ao portal.")
    catalogo = carregar_catalogo(pasta_dados)
    if any(p.id == portal_id for p in catalogo.portais):
        raise ErroCatalogo(f"Já existe um portal chamado {nome!r} no catálogo.")
    portal = _validar(
        Portal,
        {
            "id": portal_id,
            "nome": nome.strip(),
            "categoria": categoria,
            "url": (url or "").strip() or None,
            "modo_leitura": "lembrete",
            "adicionado_por": "local",
            "frequencia_dias": frequencia_dias,
        },
        "portal",
    )
    local = _ler_local(pasta_dados)
    local.portais.append(portal)
    _gravar_local(pasta_dados, local)
    return portal
