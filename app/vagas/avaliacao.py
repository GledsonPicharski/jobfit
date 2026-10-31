"""O que acontece em código em volta de `avaliar_vaga` (regras 3, 8 e 10).

Depois da IA, cada requisito é conferido contra a vaga e o dossiê enviado: o trecho
precisa estar na vaga, os IDs precisam existir, e "atende" ou "parcial" sem fato válido
vira "não sei". Assim, um texto de vaga que tente manipular a IA não sobe a nota sem um
fato real do dossiê. Depois, os ajustes da pessoa mudam a decisão sem chamar a IA.
"""

from typing import Any

from app.ia.tarefas import AvaliacaoVaga
from app.textos import contem

Requisito = dict[str, Any]

# O que cada ajuste da pessoa faz com o requisito.
ACOES = {
    "tenho": "Eu tenho isso",
    "nao_tenho": "Não tenho",
    "nao_se_aplica": "Não se aplica",
    "nao_e_bem_assim": "Não é bem assim",
}


def conferir(
    saida: AvaliacaoVaga, texto_vaga: str, ids_enviados: set[str]
) -> tuple[list[Requisito], list[str]]:
    requisitos: list[Requisito] = []
    sem_trecho = 0
    inventados: list[str] = []
    for item in saida.requisitos:
        if not contem(texto_vaga, item.trecho):
            sem_trecho += 1
            continue
        validos = [f for f in dict.fromkeys(item.fatos) if f in ids_enviados]
        inventados += [f for f in item.fatos if f not in ids_enviados and f not in inventados]
        dados = {**item.model_dump(), "fatos": validos, "alerta": None}
        if item.decisao in ("atende", "parcial") and not validos:
            dados["decisao"] = "nao_sei"
            rotulo = "atende" if item.decisao == "atende" else "atende em parte"
            dados["alerta"] = f"A IA disse que {rotulo}, mas sem citar fato do dossiê."
        requisitos.append(dados)

    alertas = []
    if sem_trecho:
        alertas.append(f"{sem_trecho} requisito(s) sem trecho na vaga foram descartados.")
    if inventados:
        lista = ", ".join(inventados)
        alertas.append(f"A IA citou fatos que não existem no dossiê enviado: {lista}.")
    return requisitos, alertas


def requisitos_efetivos(
    requisitos: list[Requisito], ajustes: list[tuple[int, str, str | None]]
) -> list[Requisito]:
    """Os requisitos com os ajustes da pessoa por cima; o último ajuste de cada um vale."""
    ultimo: dict[int, tuple[str, str | None]] = {}
    for posicao, acao, fato_id in ajustes:
        ultimo[posicao] = (acao, fato_id)
    efetivos = []
    for posicao, original in enumerate(requisitos):
        r = {**original, "aplica": True, "ajuste": None, "posicao": posicao}
        if posicao in ultimo:
            acao, fato_id = ultimo[posicao]
            r["ajuste"] = acao
            if acao == "tenho":
                r["decisao"], r["fatos"] = "atende", [fato_id] if fato_id else r["fatos"]
            elif acao in ("nao_tenho", "nao_e_bem_assim"):
                r["decisao"] = "nao_atende"
            elif acao == "nao_se_aplica":
                r["aplica"] = False
        efetivos.append(r)
    return efetivos
