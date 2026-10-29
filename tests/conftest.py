import os

os.environ["PYDANTIC_AI_NO_BANNER"] = "1"

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError
from pydantic_ai import models

from app import config

# Nenhum teste chama provedor de IA de verdade; só TestModel/FunctionModel.
models.ALLOW_MODEL_REQUESTS = False


class ChaveiroMemoria(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.segredos: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.segredos.get((service, username))

    def set_password(self, service, username, password):
        self.segredos[(service, username)] = password

    def delete_password(self, service, username):
        if self.segredos.pop((service, username), None) is None:
            raise PasswordDeleteError("não existe")


@pytest.fixture(autouse=True)
def ambiente_isolado(tmp_path, monkeypatch):
    """Pasta do app e cofre de chaves temporários em todo teste."""
    monkeypatch.setenv("JOBFIT_HOME", str(tmp_path / "AppData Local" / "JobFit"))
    original = keyring.get_keyring()
    chaveiro = ChaveiroMemoria()
    keyring.set_keyring(chaveiro)
    yield chaveiro
    keyring.set_keyring(original)


@pytest.fixture
def chaveiro(ambiente_isolado) -> ChaveiroMemoria:
    return ambiente_isolado


@pytest.fixture
def pasta_dados(tmp_path):
    """Pasta de dados com espaço e acento, como `G:\\Meu Drive\\Currículo`."""
    pasta = tmp_path / "Meu Drive" / "Currículo – teste"
    pasta.mkdir(parents=True)
    config.salvar_config(config.AppConfig(pasta_dados=pasta))
    return pasta
