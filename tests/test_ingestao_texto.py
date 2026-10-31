import pytest

from app.ingestao.texto import decodificar, secoes, texto_das_secoes

DOSSIE = """---
versao: 3
---
# Parte A — Carreira

Resumo da carreira com ação e coração.

## Experiências

- Liderou a migração — 40% mais rápido.

```python
# isto é código, não título
```

## Formação

Bacharel em Estatística.

# Parte B — Família

Nada daqui vai para a IA.

## Saúde

Privado.
"""


def test_lista_os_titulos_com_nivel_e_ignora_codigo():
    lista = secoes(DOSSIE)
    assert [(s.nivel, s.titulo) for s in lista] == [
        (0, "Antes do primeiro título"),
        (1, "Parte A — Carreira"),
        (2, "Experiências"),
        (2, "Formação"),
        (1, "Parte B — Família"),
        (2, "Saúde"),
    ]
    assert [s.indice for s in lista] == list(range(6))


def test_cada_secao_leva_so_o_proprio_conteudo():
    lista = secoes(DOSSIE)
    experiencias = texto_das_secoes(DOSSIE, [2])
    assert "40% mais rápido" in experiencias
    assert "# isto é código" in experiencias  # o comentário vai junto do bloco
    assert "Bacharel" not in experiencias
    assert lista[2].caracteres == len(experiencias)


def test_parte_a_sem_a_parte_b():
    lista = secoes(DOSSIE)
    parte_a = [s.indice for s in lista if 1 <= s.indice <= 3]
    texto = texto_das_secoes(DOSSIE, parte_a)
    assert texto.startswith("# Parte A — Carreira")
    assert "Bacharel em Estatística." in texto
    assert "Família" not in texto and "Privado" not in texto
    assert "versao: 3" not in texto


def test_ordem_do_arquivo_e_indice_invalido_ignorado():
    texto = texto_das_secoes(DOSSIE, [3, 1, 99])
    assert texto.index("Parte A") < texto.index("Formação")


def test_texto_sem_titulos_e_uma_secao_so():
    assert [s.nivel for s in secoes("Só um parágrafo.\nOutro.")] == [0]
    assert secoes("") == []


def test_cerca_de_til_e_titulo_com_cerquilhas_no_fim():
    texto = "## Título ##\n~~~\n# dentro\n~~~\n### Outro"
    assert [s.titulo for s in secoes(texto)] == ["Título", "Outro"]


@pytest.mark.parametrize(
    ("conteudo", "esperado"),
    [
        ("ação — ok\r\n".encode(), "ação — ok\n"),
        (b"\xef\xbb\xbfcom BOM", "com BOM"),
        ("Bloco de Notas antigo: ação".encode("cp1252"), "Bloco de Notas antigo: ação"),
    ],
)
def test_decodificar(conteudo, esperado):
    assert decodificar(conteudo) == esperado
