"""Excluir um perfil manda tudo para `<pasta_dados>/lixeira/`; nada é apagado de vez.

O perfil guarda o dossiê e o histórico da pessoa, então um clique errado precisa ter volta:
basta mover a pasta da lixeira de volta para `perfis/` (e `banco.db` para a pasta de bancos).
Só as chaves de API são apagadas, porque não podem ficar fora do cofre.
"""

import shutil
from datetime import datetime
from pathlib import Path

from app import config
from app.db import fechar_banco
from app.ia.chaves import apagar_chave
from app.perfis.modelos import PROVEDORES_COM_CHAVE
from app.perfis.servico import ErroPerfil, carregar_perfil, pasta_perfil

# Arquivos do SQLite em modo WAL; os dois últimos só existem com o banco aberto.
_SUFIXOS_BANCO = ("", "-wal", "-shm")


def _destino_livre(lixeira: Path, slug: str) -> Path:
    base = f"{slug}-{datetime.now():%Y%m%d-%H%M%S}"
    destino, n = lixeira / base, 2
    while destino.exists():
        destino, n = lixeira / f"{base}-{n}", n + 1
    return destino


def excluir_perfil(pasta_dados: Path, slug: str) -> Path:
    """Move o perfil e o banco para a lixeira, apaga as chaves e devolve a pasta na lixeira."""
    carregar_perfil(pasta_dados, slug)  # valida o slug e confirma que o perfil existe
    origem = pasta_perfil(pasta_dados, slug)
    lixeira = pasta_dados / "lixeira"
    lixeira.mkdir(exist_ok=True)
    destino = _destino_livre(lixeira, slug)

    # Primeiro a pasta: é um rename no mesmo disco e falha antes de mexer em qualquer outra coisa.
    try:
        origem.rename(destino)
    except OSError as erro:
        raise ErroPerfil(
            f"Não foi possível mover o perfil para a lixeira ({erro.strerror}). "
            "Feche arquivos dele que estejam abertos e tente de novo."
        ) from erro

    banco = config.caminho_banco(slug)
    fechar_banco(banco)  # no Windows, um SQLite aberto não pode ser movido
    movidos: list[tuple[Path, Path]] = []
    try:
        for sufixo in _SUFIXOS_BANCO:
            arquivo = banco.with_name(banco.name + sufixo)
            if arquivo.exists():
                shutil.move(arquivo, destino / f"banco.db{sufixo}")
                movidos.append((arquivo, destino / f"banco.db{sufixo}"))
    except OSError as erro:
        for original, na_lixeira in reversed(movidos):
            shutil.move(na_lixeira, original)
        destino.rename(origem)
        raise ErroPerfil(
            f"Não foi possível mover o banco do perfil ({erro.strerror}). Nada foi excluído."
        ) from erro

    for provedor in PROVEDORES_COM_CHAVE:
        apagar_chave(slug, provedor)

    cfg = config.carregar_config()
    if cfg.ultimo_perfil == slug:
        config.salvar_config(cfg.model_copy(update={"ultimo_perfil": None}))
    return destino
