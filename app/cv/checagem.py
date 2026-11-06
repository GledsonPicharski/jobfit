"""Checagem do CV em código (regra 3): nada sem fato de origem.

Vale para o que a IA redigiu e para o que a pessoa editou no rascunho. Cada frase é
conferida contra os fatos que ela cita: números, anos e empresas precisam estar neles, e
o cargo de cada experiência precisa ser o do dossiê (ou a tradução confirmada). Um
bloqueio impede o PDF; um alerta só avisa.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

from app.cv.modelos import SECOES_DE_FRASES, Frase, Rascunho
from app.cv.selecao import ConfigCV, carregar_config
from app.dossie.modelos import Fato
from app.textos import contem, digitos, numeros, palavras

_ANO = re.compile(r"^(19|20)\d{2}$")
_ANOS_DE = re.compile(r"(\d+)\s*\+?\s*(?:anos|ano|years|year)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Problema:
    nivel: str  # bloqueio | alerta
    mensagem: str


@dataclass
class Checagem:
    problemas: dict[str, list[Problema]] = field(default_factory=dict)

    def _contar(self, nivel: str) -> int:
        return sum(p.nivel == nivel for lista in self.problemas.values() for p in lista)

    @property
    def bloqueios(self) -> int:
        return self._contar("bloqueio")

    @property
    def alertas(self) -> int:
        return self._contar("alerta")

    def anotar(self, caminho: str, nivel: str, mensagem: str) -> None:
        self.problemas.setdefault(caminho, []).append(Problema(nivel, mensagem))


def frases(rascunho: Rascunho) -> Iterator[tuple[str, Frase]]:
    """Cada frase do CV com o seu caminho, na ordem do PDF."""
    yield "titulo", rascunho.titulo
    for i, frase in enumerate(rascunho.resumo):
        yield f"resumo.{i}", frase
    for i, exp in enumerate(rascunho.experiencias):
        for j, frase in enumerate(exp.bullets):
            yield f"experiencias.{i}.bullets.{j}", frase
    for secao in SECOES_DE_FRASES[1:]:
        for i, frase in enumerate(getattr(rascunho, secao)):
            yield f"{secao}.{i}", frase


def limpar_ids(rascunho: Rascunho, permitidos: set[str]) -> tuple[Rascunho, list[str]]:
    """Tira os IDs que não foram enviados à IA (inventados ou 🔒); devolve os removidos."""
    limpo = rascunho.model_copy(deep=True)
    removidos: list[str] = []
    for _, frase in frases(limpo):
        removidos += [f for f in frase.fatos if f not in permitidos and f not in removidos]
        frase.fatos = [f for f in dict.fromkeys(frase.fatos) if f in permitidos]
    return limpo, removidos


def _extra(fato: Fato, campo: str) -> str | None:
    valor = (fato.model_extra or {}).get(campo)
    return str(valor) if valor else None


def _textos(fato: Fato) -> list[str]:
    return [t for t in (fato.texto, _extra(fato, "texto_en"), fato.cargo) if t]


def _anos_do_periodo(fato: Fato, hoje: date) -> tuple[int, int] | None:
    if fato.periodo is None or fato.periodo.inicio is None:
        return None
    fim = int(fato.periodo.fim[:4]) if fato.periodo.fim else hoje.year
    return int(fato.periodo.inicio[:4]), fim


def _checar_frase(
    checagem: Checagem,
    caminho: str,
    frase: Frase,
    fatos: dict[str, Fato],
    empresa_vaga: str | None,
    hoje: date,
    config: ConfigCV,
) -> None:
    citados = [fatos[f] for f in frase.fatos if f in fatos]
    if not citados:
        checagem.anotar(caminho, "bloqueio", "Frase sem fato do dossiê.")
        return

    textos = [t for f in citados for t in _textos(f)]
    textos += [str(v) for f in citados for v in f.metricas.values()]
    no_dossie = {digitos(n) for t in textos for n in numeros(t)}
    periodos = [p for f in citados if (p := _anos_do_periodo(f, hoje))]
    anos = {str(a) for p in periodos for a in p} | {n for t in textos for n in numeros(t)}
    span = max(p[1] for p in periodos) - min(p[0] for p in periodos) if periodos else 0
    de_experiencia = {m.group(1) for m in _ANOS_DE.finditer(frase.texto)}

    sem_ano, sem_numero = [], []
    for numero in dict.fromkeys(numeros(frase.texto)):
        if _ANO.match(numero):
            if numero not in anos:
                sem_ano.append(numero)
        elif digitos(numero) not in no_dossie and not (
            numero in de_experiencia and periodos and int(numero) <= span
        ):
            sem_numero.append(numero)
    if sem_ano:
        checagem.anotar(caminho, "bloqueio", f"Ano sem fato de origem: {', '.join(sem_ano)}.")
    if sem_numero:
        lista = ", ".join(sem_numero)
        checagem.anotar(caminho, "bloqueio", f"Número sem fato de origem: {lista}.")

    empresas_dossie = {f.empresa for f in fatos.values() if f.empresa}
    empresas_citadas = {f.empresa for f in citados if f.empresa}
    for empresa in sorted(empresas_dossie):
        if contem(frase.texto, empresa) and not any(
            contem(c, empresa) or contem(empresa, c) for c in empresas_citadas
        ):
            checagem.anotar(
                caminho, "bloqueio", f"Cita {empresa}, que não está nos fatos desta frase."
            )
    if (
        empresa_vaga
        and contem(frase.texto, empresa_vaga)
        and not any(contem(e, empresa_vaga) for e in empresas_dossie)
    ):
        checagem.anotar(
            caminho, "bloqueio", f"Cita {empresa_vaga}, a empresa da vaga, como se fosse sua."
        )

    if len(frase.texto) > config.caracteres_por_frase:
        checagem.anotar(
            caminho,
            "alerta",
            f"Frase longa: {len(frase.texto)} caracteres (o ideal é até "
            f"{config.caracteres_por_frase}).",
        )


def _checar_cargo(
    checagem: Checagem, caminho: str, cargo_id: str, titulo: str, idioma: str, fatos
) -> None:
    fato = fatos.get(cargo_id)
    if fato is None or fato.tipo != "cargo":
        checagem.anotar(caminho, "bloqueio", f"O cargo {cargo_id} não está no dossiê.")
        return
    original = fato.cargo or fato.texto
    aceitos = {palavras(t) for t in (original, _extra(fato, "cargo_en")) if t}
    if palavras(titulo) in aceitos:
        return
    if idioma == "en":
        mensagem = f"Tradução do cargo pela IA: confirme ou use o do dossiê ({original})."
    else:
        mensagem = f"Cargo diferente do dossiê ({original})."
    checagem.anotar(caminho, "bloqueio", mensagem)


def checar(
    rascunho: Rascunho,
    fatos: dict[str, Fato],
    *,
    empresa_vaga: str | None = None,
    hoje: date | None = None,
    config: ConfigCV | None = None,
) -> Checagem:
    hoje = hoje or date.today()
    config = config or carregar_config()
    checagem = Checagem()
    for caminho, frase in frases(rascunho):
        _checar_frase(checagem, caminho, frase, fatos, empresa_vaga, hoje, config)
    for i, exp in enumerate(rascunho.experiencias):
        caminho = f"experiencias.{i}.titulo"
        _checar_cargo(checagem, caminho, exp.cargo_id, exp.titulo, rascunho.idioma, fatos)
    vistas: set[str] = set()
    for i, frase in enumerate(rascunho.competencias):
        chave = palavras(frase.texto)
        if chave in vistas:
            checagem.anotar(f"competencias.{i}", "alerta", "Competência repetida.")
        vistas.add(chave)
    return checagem
