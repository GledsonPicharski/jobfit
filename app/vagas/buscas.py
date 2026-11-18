"""Buscas salvas: o que o scan procura e os filtros de cada busca (decisão 0009).

Os filtros rodam em código, antes de qualquer IA. Dado ausente nunca bloqueia. O salário
mínimo da busca é privado: não aparece em mensagem nenhuma e nunca vai para a IA.
"""

import json
from dataclasses import dataclass, field

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.ia.modelos import agora_utc
from app.textos import contem, palavras
from app.vagas.filtros import ResultadoFiltros
from app.vagas.metadados import MODALIDADES, SENIORIDADES, Metadados
from app.vagas.tabelas import Busca

MAX_TITULOS = 5
_LISTAS = (
    "titulos",
    "paises",
    "senioridades",
    "empresas_excluidas",
    "setores_excluidos",
    "palavras_obrigatorias",
    "palavras_proibidas",
    "portais",
)
_CONECTIVOS = {"de", "da", "do", "das", "dos", "e", "em", "para", "of", "the", "and", "for", "in"}
_GLOBAL = ("worldwide", "anywhere", "global", "international", "qualquer lugar")
_SO_MODALIDADE = {"remote", "remoto", "remota", "fully", "100", "work", "from", "home"}
# Outros nomes que uma restrição de vaga remota pode usar para incluir o país.
_ALIASES_PAIS = {
    "brasil": [
        "brasil", "brazil", "latam", "latin america", "america latina", "south america",
        "america do sul", "americas",
    ],
    "portugal": ["portugal", "europe", "europa", "emea"],
}  # fmt: skip


class ErroBusca(ValueError):
    pass


@dataclass
class FiltrosBusca:
    titulos: list[str] = field(default_factory=list)
    so_remoto: bool = False
    paises: list[str] = field(default_factory=list)
    senioridades: list[str] = field(default_factory=list)
    salario_minimo: int | None = None
    empresas_excluidas: list[str] = field(default_factory=list)
    setores_excluidos: list[str] = field(default_factory=list)
    palavras_obrigatorias: list[str] = field(default_factory=list)
    palavras_proibidas: list[str] = field(default_factory=list)
    portais: list[str] = field(default_factory=list)


def filtros_de(busca: Busca) -> FiltrosBusca:
    listas = {nome: json.loads(getattr(busca, nome)) for nome in _LISTAS}
    return FiltrosBusca(so_remoto=busca.so_remoto, salario_minimo=busca.salario_minimo, **listas)


# --- regras ---------------------------------------------------------------------


def _significativas(texto: str) -> set[str]:
    return set(palavras(texto).split()) - _CONECTIVOS


def titulo_casa(titulo: str | None, titulos: list[str]) -> bool:
    """Todas as palavras de algum título da busca aparecem no título da vaga."""
    if not titulos:
        return True
    da_vaga = _significativas(titulo or "")
    return any((buscado := _significativas(t)) and buscado <= da_vaga for t in titulos)


def aceita_restricao(restricoes: list[str], paises: list[str]) -> bool:
    """Uma vaga remota restrita a certos lugares inclui algum dos países da busca?"""
    if not restricoes or not paises:
        return True
    for restricao in restricoes:
        if any(contem(restricao, g) for g in _GLOBAL):
            return True
        if not set(palavras(restricao).split()) - _SO_MODALIDADE:
            return True  # "Remote", sem lugar: não restringe

        for pais in paises:
            nomes = _ALIASES_PAIS.get(palavras(pais), [pais])
            if any(contem(restricao, nome) for nome in nomes):
                return True
    return False


def _milhar(valor) -> str:
    return f"{int(valor):,}".replace(",", ".")


def aplicar_busca(
    meta: Metadados, texto: str, restricoes: list[str], f: FiltrosBusca
) -> ResultadoFiltros:
    r = ResultadoFiltros()
    if f.so_remoto and meta.modalidade and meta.modalidade != "remoto":
        modalidade = MODALIDADES[meta.modalidade].lower()
        r.bloqueios.append(f"Vaga {modalidade}; esta busca é só de remotas.")
    if not aceita_restricao(restricoes, f.paises):
        r.bloqueios.append(f"Vaga remota só para {', '.join(restricoes)}.")
    if meta.senioridade and f.senioridades and meta.senioridade not in f.senioridades:
        nivel = SENIORIDADES[meta.senioridade].lower()
        buscadas = ", ".join(SENIORIDADES[s].lower() for s in f.senioridades)
        r.bloqueios.append(f"Senioridade {nivel}; esta busca é de: {buscadas}.")
    salario = meta.salario
    if (
        salario
        and f.salario_minimo
        and salario.moeda == "BRL"
        and salario.maximo < f.salario_minimo
    ):
        teto = _milhar(salario.maximo)
        r.bloqueios.append(f"Salário informado (até {teto} por mês) abaixo do mínimo desta busca.")
    if meta.empresa:
        r.bloqueios += [
            f"Empresa excluída nesta busca: {e}."
            for e in f.empresas_excluidas
            if contem(meta.empresa, e)
        ]
    r.bloqueios += [
        f"A vaga é de um setor que esta busca exclui: {s}."
        for s in f.setores_excluidos
        if contem(texto, s)
    ]
    r.bloqueios += [
        f"A vaga menciona algo que esta busca evita: {p}."
        for p in f.palavras_proibidas
        if contem(texto, p)
    ]
    r.bloqueios += [
        f"A descrição não menciona: {p}." for p in f.palavras_obrigatorias if not contem(texto, p)
    ]
    return r


# --- no banco -------------------------------------------------------------------


def _limpa(valores: list[str] | None) -> list[str]:
    vistos: list[str] = []
    for valor in valores or []:
        valor = valor.strip()
        if valor and valor.casefold() not in {v.casefold() for v in vistos}:
            vistos.append(valor)
    return vistos


def salvar_busca(engine: Engine, *, nome: str, busca_id: int | None = None, **campos) -> Busca:
    nome = nome.strip()
    if not nome:
        raise ErroBusca("Dê um nome à busca.")
    listas = {n: _limpa(campos.pop(n, None)) for n in _LISTAS}
    if not listas["titulos"]:
        raise ErroBusca("Informe pelo menos um título de vaga.")
    if len(listas["titulos"]) > MAX_TITULOS:
        raise ErroBusca(f"Use até {MAX_TITULOS} títulos por busca.")
    with Session(engine, expire_on_commit=False) as sessao:
        busca = sessao.get(Busca, busca_id) if busca_id else Busca(nome=nome)
        if busca is None:
            raise ErroBusca("Busca não encontrada.")
        busca.nome = nome
        for campo, valores in listas.items():
            setattr(busca, campo, json.dumps(valores, ensure_ascii=False))
        for campo, valor in campos.items():
            setattr(busca, campo, valor)
        busca.atualizado_em = agora_utc()
        sessao.add(busca)
        sessao.commit()
        return busca


def listar_buscas(engine: Engine, *, so_ativas: bool = False) -> list[Busca]:
    with Session(engine) as sessao:
        consulta = select(Busca).order_by(Busca.nome)
        if so_ativas:
            consulta = consulta.where(Busca.ativa)
        return list(sessao.exec(consulta))


def obter_busca(engine: Engine, busca_id: int) -> Busca | None:
    with Session(engine) as sessao:
        return sessao.get(Busca, busca_id)


def excluir_busca(engine: Engine, busca_id: int) -> None:
    """As origens que apontam para ela ficam sem busca; as vagas continuam."""
    from app.vagas.tabelas import VagaOrigem

    with Session(engine) as sessao:
        for origem in sessao.exec(select(VagaOrigem).where(VagaOrigem.busca_id == busca_id)):
            origem.busca_id = None
            sessao.add(origem)
        if busca := sessao.get(Busca, busca_id):
            sessao.delete(busca)
        sessao.commit()
