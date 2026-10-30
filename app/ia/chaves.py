"""Chaves de API no cofre do sistema (no Windows, o Gerenciador de Credenciais).

Nunca em arquivo, banco ou log. Uma chave por perfil e provedor.
"""

import contextlib

import keyring
from keyring.errors import PasswordDeleteError

from app.perfis.modelos import Provedor

SERVICO = "jobfit"


def _usuario(slug: str, provedor: Provedor) -> str:
    return f"{slug}:{provedor}"


def salvar_chave(slug: str, provedor: Provedor, chave: str) -> None:
    chave = chave.strip()
    if not chave:
        raise ValueError("A chave está vazia.")
    keyring.set_password(SERVICO, _usuario(slug, provedor), chave)


def ler_chave(slug: str, provedor: Provedor) -> str | None:
    return keyring.get_password(SERVICO, _usuario(slug, provedor))


def tem_chave(slug: str, provedor: Provedor) -> bool:
    return ler_chave(slug, provedor) is not None


def apagar_chave(slug: str, provedor: Provedor) -> None:
    with contextlib.suppress(PasswordDeleteError):
        keyring.delete_password(SERVICO, _usuario(slug, provedor))
