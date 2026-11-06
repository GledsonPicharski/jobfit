"""O que acontece em código em volta de `extrair_fatos` (regras 1 e 3).

Antes da IA: e-mail, telefone e CPF saem do texto. E-mail e telefone viram propostas
de contato marcadas `nao_enviar_ia`, sem passar pelo provedor.

Depois da IA: cada fato é conferido contra o texto enviado. O trecho tem de existir
nele, os números do fato têm de estar no trecho, e empresa, cargo e anos têm de
aparecer no texto. O que falhar vira alerta, e a proposta começa rejeitada.
"""

import re

from app.dossie.propostas import Candidato
from app.ia.tarefas import FatoExtraido, FatosExtraidos
from app.textos import contem

_CPF = re.compile(r"(?<![\w.])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\w)")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
_TELEFONE = re.compile(r"(?<![\w+])(?:\+55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}(?!\w)")
_NUMERO = re.compile(r"\d+(?:[.,]\d+)*%?")


def _digitos(numero: str) -> str:
    return re.sub(r"\D", "", numero)


def mascarar(texto: str, fonte: str) -> tuple[str, list[Candidato]]:
    """O texto que vai para a IA, sem contato nem CPF, e os contatos achados em código."""
    contatos: list[Candidato] = []

    def guardar(rotulo: str, mascara: str):
        def trocar(m: re.Match) -> str:
            valor = m.group(0).strip()
            texto_fato = f"{rotulo}: {valor}"
            if all(c.texto != texto_fato for c in contatos):
                contatos.append(
                    Candidato(
                        tipo="contato",
                        texto=texto_fato,
                        fonte=fonte,
                        trecho=valor,
                        nao_enviar_ia=True,
                    )
                )
            return mascara

        return trocar

    texto = _CPF.sub("[CPF omitido]", texto)
    texto = _EMAIL.sub(guardar("E-mail", "[e-mail omitido]"), texto)
    texto = _TELEFONE.sub(guardar("Telefone", "[telefone omitido]"), texto)
    return texto, contatos


def checar(fato: FatoExtraido, fonte: str) -> list[str]:
    alertas = []
    if not contem(fonte, fato.trecho):
        alertas.append("O trecho de origem não está no texto importado.")

    no_trecho = {_digitos(n) for n in _NUMERO.findall(fato.trecho)}
    valores = [fato.texto, *(str(v) for v in fato.metricas.values())]
    sem_origem: list[str] = []
    for numero in (n for valor in valores for n in _NUMERO.findall(valor)):
        if _digitos(numero) not in no_trecho and numero not in sem_origem:
            sem_origem.append(numero)
    if sem_origem:
        alertas.append(f"Número sem origem no trecho: {', '.join(sem_origem)}.")

    if fato.empresa and not contem(fonte, fato.empresa):
        alertas.append(f"Empresa não aparece no texto: {fato.empresa}.")
    if fato.cargo and not contem(fonte, fato.cargo):
        alertas.append(f"Cargo não aparece no texto: {fato.cargo}.")
    if fato.periodo:
        anos = [d[:4] for d in (fato.periodo.inicio, fato.periodo.fim) if d]
        for ano in dict.fromkeys(anos):
            if not contem(fonte, ano):
                alertas.append(f"Ano sem origem no texto: {ano}.")
    return alertas


def candidatos_da_ia(saida: FatosExtraidos, enviado: str, fonte: str) -> list[Candidato]:
    """Os fatos da IA como candidatos, já conferidos contra o texto que foi enviado."""
    return [
        Candidato(
            tipo=fato.tipo,
            texto=fato.texto,
            empresa=fato.empresa,
            cargo=fato.cargo,
            periodo=fato.periodo,
            metricas=fato.metricas,
            fonte=fonte,
            trecho=fato.trecho,
            alertas=checar(fato, enviado),
        )
        for fato in saida.fatos
    ]
