"""Regra 5 do CLAUDE.md: 🔒 nunca vai para CV; `nao_enviar_ia` nunca vai para a IA."""

from app.dossie.filtros import fatos_para_ia, fatos_publicaveis
from app.dossie.modelos import Fato


def _fato(n: int, **campos) -> Fato:
    return Fato(id=f"F-{n:03d}", tipo="resultado", texto=f"fato {n}", **campos)


FATOS = [
    _fato(1),
    _fato(2, privado=True),
    _fato(3, nao_enviar_ia=True),
    _fato(4, privado=True, nao_enviar_ia=True),
    _fato(5, status="proposto"),
    _fato(6, status="rejeitado"),
]


def test_privado_nunca_e_publicavel():
    ids = [f.id for f in fatos_publicaveis(FATOS)]
    assert ids == ["F-001", "F-003"]


def test_so_confirmado_e_publicavel():
    assert all(f.status == "confirmado" for f in fatos_publicaveis(FATOS))


def test_nao_enviar_ia_nunca_vai_para_a_ia():
    ids = [f.id for f in fatos_para_ia(FATOS)]
    assert "F-003" not in ids
    assert "F-004" not in ids
    assert ids == ["F-001", "F-002", "F-005", "F-006"]


def test_filtros_aceitam_qualquer_iteravel():
    assert fatos_para_ia(iter(FATOS[:1])) == FATOS[:1]
    assert fatos_publicaveis(f for f in FATOS[:2]) == FATOS[:1]
