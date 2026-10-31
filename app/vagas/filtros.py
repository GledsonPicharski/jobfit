"""Filtros duros: barram ou alertam antes de gastar IA (etapa 1 da seção 6 do plano).

Bloqueiam: modalidade ou cidade fora do aceito, salário abaixo do mínimo, empresa ou
palavra evitada. Só alertam: senioridade e nível de inglês. Dado ausente nunca bloqueia.
O salário mínimo da pessoa não aparece em nenhuma mensagem: ele é privado.
"""

import re
from dataclasses import dataclass, field

from app.dossie.modelos import sem_acento
from app.perfis.modelos import Criterios
from app.vagas.metadados import MODALIDADES, NIVEIS_INGLES, SENIORIDADES, Metadados


@dataclass
class ResultadoFiltros:
    bloqueios: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)

    @property
    def bloqueada(self) -> bool:
        return bool(self.bloqueios)


def _palavras(texto: str) -> str:
    return " ".join(re.findall(r"\w+", sem_acento(texto).casefold()))


def _contem(todo: str, parte: str) -> bool:
    parte = _palavras(parte)
    return bool(parte) and f" {parte} " in f" {_palavras(todo)} "


def _milhar(valor) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _rotulos(valores, rotulos: dict[str, str]) -> str:
    return ", ".join(rotulos[v].lower() for v in valores)


def aplicar_filtros(
    meta: Metadados, texto: str, criterios: Criterios, ingles_declarado: int | None
) -> ResultadoFiltros:
    r = ResultadoFiltros()

    if meta.modalidade and meta.modalidade not in criterios.modalidades:
        aceitas = _rotulos(criterios.modalidades, MODALIDADES)
        r.bloqueios.append(
            f"Modalidade {MODALIDADES[meta.modalidade].lower()}; você aceita: {aceitas}."
        )
    elif meta.modalidade in ("hibrido", "presencial") and criterios.cidades:
        if meta.local is None:
            nome = MODALIDADES[meta.modalidade].lower()
            r.alertas.append(f"Vaga {nome} sem cidade identificada: confira o local.")
        elif not any(_contem(meta.local, cidade) for cidade in criterios.cidades):
            r.bloqueios.append(
                f"Vaga em {meta.local}; você aceita híbrido ou presencial só em "
                f"{', '.join(criterios.cidades)}."
            )

    if meta.salario and criterios.salario_minimo:
        teto = _milhar(meta.salario.maximo)
        if meta.salario.moeda != "BRL":
            r.alertas.append(f"Salário em dólar (até {teto} por mês): compare com o seu mínimo.")
        elif meta.salario.maximo < criterios.salario_minimo:
            r.bloqueios.append(f"Salário informado (até {teto} por mês) abaixo do seu mínimo.")

    if meta.empresa:
        for empresa in criterios.empresas_evitar:
            if _contem(meta.empresa, empresa):
                r.bloqueios.append(f"Empresa na sua lista de evitar: {empresa}.")
    for palavra in criterios.palavras_evitar:
        if _contem(texto, palavra):
            r.bloqueios.append(f"A vaga menciona algo que você evita: {palavra}.")

    if (
        meta.senioridade
        and criterios.senioridades
        and meta.senioridade not in criterios.senioridades
    ):
        buscadas = _rotulos(criterios.senioridades, SENIORIDADES)
        r.alertas.append(
            f"Senioridade {SENIORIDADES[meta.senioridade].lower()}; você busca: {buscadas}."
        )
    if meta.ingles and (ingles_declarado is None or meta.ingles > ingles_declarado):
        pedido = NIVEIS_INGLES[meta.ingles]
        if ingles_declarado is None:
            r.alertas.append(
                f"A vaga pede inglês {pedido}; o seu dossiê não diz o seu nível de inglês."
            )
        else:
            declarado = NIVEIS_INGLES[ingles_declarado]
            r.alertas.append(f"A vaga pede inglês {pedido}; o seu dossiê diz {declarado}.")
    return r
