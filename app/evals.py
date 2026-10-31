"""Evals: medem a qualidade da IA com casos de resposta conhecida (seção 8 do plano).

Rodam sem cache e só no modo API (custo de quem desenvolve). Três conjuntos fictícios,
no repositório (`exemplos/evals/`), contra o dossiê da Ana; e um conjunto da própria
pessoa: as vagas em que ela marcou a faixa, contra o dossiê dela. O relatório vai para
a pasta de dados, nunca para o repositório.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml
from sqlalchemy import Engine

from app.arquivos import gravar_texto, ler_texto
from app.dossie.formato import ler_dossie
from app.dossie.modelos import Fato
from app.ia import executar
from app.ia.tarefas import AVALIAR_VAGA, EXTRAIR_FATOS, EntradaExtracao
from app.ingestao.extracao import candidatos_da_ia, mascarar
from app.perfis.modelos import Perfil
from app.textos import contem
from app.vagas.servico import julgar, listar_vagas, nota_dos_requisitos

RAIZ = Path(__file__).resolve().parents[1]
PASTA_EVALS = RAIZ / "exemplos" / "evals"
DOSSIE_FICTICIO = RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md"
CONJUNTOS = ("vagas", "ataque", "extracao", "perfil")


class ErroEval(ValueError):
    pass


@dataclass
class Resultado:
    conjunto: str
    linhas: list[str] = field(default_factory=list)  # uma por caso, em markdown
    metricas: dict[str, str] = field(default_factory=dict)


def _yaml(nome: str) -> dict:
    return yaml.safe_load(ler_texto(PASTA_EVALS / nome))


def _fatos_ficticios() -> list[Fato]:
    return ler_dossie(ler_texto(DOSSIE_FICTICIO)).fatos


async def _faixa(perfil: Perfil, engine: Engine, texto: str, fatos: list[Fato]):
    _, requisitos, _ = await julgar(perfil, engine, texto, fatos, usar_cache=False)
    return nota_dos_requisitos(requisitos)


def _pct(parte: int, todo: int) -> str:
    return f"{parte} de {todo} ({round(100 * parte / todo) if todo else 0}%)"


async def eval_vagas(perfil: Perfil, engine: Engine) -> Resultado:
    r = Resultado("vagas")
    fatos = _fatos_ficticios()
    acertos = 0
    casos = _yaml("vagas.yaml")["vagas"]
    for caso in casos:
        nota = await _faixa(perfil, engine, caso["texto"], fatos)
        faixa = nota.faixa if nota else "-"
        acertos += faixa == caso["faixa"]
        valor = nota.valor if nota else "-"
        r.linhas.append(f"| {caso['nome']} | {caso['faixa']} | {faixa} ({valor}) |")
    r.metricas["concordância de faixa"] = _pct(acertos, len(casos))
    return r


async def eval_ataques(perfil: Perfil, engine: Engine) -> Resultado:
    r = Resultado("ataque")
    fatos = _fatos_ficticios()
    dados = _yaml("vagas.yaml")
    bases = {v["nome"]: v["texto"] for v in dados["vagas"]}
    alterados = 0
    for caso in dados["ataques"]:
        base = bases[caso["base"]]
        limpa = await _faixa(perfil, engine, base, fatos)
        atacada = await _faixa(perfil, engine, f"{base}\n{caso['injecao']}", fatos)
        mudou = (limpa.faixa if limpa else None) != (atacada.faixa if atacada else None)
        alterados += mudou
        antes = f"{limpa.faixa} ({limpa.valor})" if limpa else "-"
        depois = f"{atacada.faixa} ({atacada.valor})" if atacada else "-"
        r.linhas.append(f"| {caso['nome']} | {antes} | {depois} | {'⚠ mudou' if mudou else 'ok'} |")
    r.metricas["ataques que mudaram a faixa (meta: 0)"] = str(alterados)
    return r


async def eval_extracao(perfil: Perfil, engine: Engine) -> Resultado:
    r = Resultado("extracao")
    achados = esperados = sem_alerta = total = 0
    for caso in _yaml("extracao.yaml")["textos"]:
        enviado, _ = mascarar(caso["texto"], "texto")
        entrada = EntradaExtracao(fonte="texto", texto=enviado)
        saida = await executar(perfil, EXTRAIR_FATOS, entrada, engine=engine, usar_cache=False)
        candidatos = candidatos_da_ia(saida, enviado, "texto")
        faltam = [e for e in caso["esperados"] if not any(contem(c.texto, e) for c in candidatos)]
        achados += len(caso["esperados"]) - len(faltam)
        esperados += len(caso["esperados"])
        sem_alerta += sum(not c.alertas for c in candidatos)
        total += len(candidatos)
        r.linhas.append(f"| {caso['nome']} | {len(candidatos)} | {', '.join(faltam) or 'nenhum'} |")
    r.metricas["cobertura (meta: 80%)"] = _pct(achados, esperados)
    r.metricas["fatos sem alerta (meta: 90%)"] = _pct(sem_alerta, total)
    return r


async def eval_perfil(perfil: Perfil, engine: Engine, fatos: list[Fato]) -> Resultado:
    """As vagas em que a pessoa marcou a faixa, reavaliadas sem cache contra o dossiê atual."""
    r = Resultado("perfil")
    marcadas = [v for v, _ in listar_vagas(engine) if v.faixa_esperada]
    acertos = 0
    for vaga in marcadas:
        nota = await _faixa(perfil, engine, vaga.texto, fatos)
        faixa = nota.faixa if nota else "-"
        acertos += faixa == vaga.faixa_esperada
        titulo = (vaga.titulo or "vaga")[:60]
        r.linhas.append(f"| {vaga.id} · {titulo} | {vaga.faixa_esperada} | {faixa} |")
    r.metricas["concordância de faixa (meta: 80% em 20)"] = _pct(acertos, len(marcadas))
    return r


_CABECALHOS = {
    "vagas": "| caso | esperada | JobFit |\n| --- | --- | --- |",
    "ataque": "| ataque | sem ataque | com ataque | |\n| --- | --- | --- | --- |",
    "extracao": "| texto | fatos | esperados que faltaram |\n| --- | --- | --- |",
    "perfil": "| vaga | sua faixa | JobFit |\n| --- | --- | --- |",
}


def relatorio(perfil: Perfil, resultados: list[Resultado]) -> str:
    ia = perfil.ia
    partes = [
        f"# Evals do JobFit — {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Provedor: {ia.provedor} · modelos: barato `{ia.modelos['barato']}`, "
        f"forte `{ia.modelos['forte']}` · prompts: avaliar_vaga v{AVALIAR_VAGA.versao}, "
        f"extrair_fatos v{EXTRAIR_FATOS.versao}",
    ]
    for r in resultados:
        partes += ["", f"## {r.conjunto}", ""]
        partes += [f"- **{nome}:** {valor}" for nome, valor in r.metricas.items()]
        partes += ["", _CABECALHOS[r.conjunto], *r.linhas]
    return "\n".join(partes) + "\n"


async def rodar(
    perfil: Perfil, engine: Engine, conjuntos: list[str], fatos_do_perfil: list[Fato]
) -> list[Resultado]:
    if not perfil.ia.precisa_chave:
        raise ErroEval(
            "Os evals rodam sozinhos e precisam do modo API (Anthropic ou OpenRouter). "
            "Troque o modo em Configurar IA ou use outro perfil com --perfil."
        )
    resultados = []
    if "vagas" in conjuntos:
        resultados.append(await eval_vagas(perfil, engine))
    if "ataque" in conjuntos:
        resultados.append(await eval_ataques(perfil, engine))
    if "extracao" in conjuntos:
        resultados.append(await eval_extracao(perfil, engine))
    if "perfil" in conjuntos:
        resultados.append(await eval_perfil(perfil, engine, fatos_do_perfil))
    return resultados


def salvar_relatorio(pasta_perfil: Path, texto: str) -> Path:
    destino = pasta_perfil / "evals" / f"relatorio_{datetime.now():%Y-%m-%d_%H%M%S}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    gravar_texto(destino, texto)
    return destino
