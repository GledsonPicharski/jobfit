"""Pré-nota: a parte dos termos da vaga que aparece no dossiê, em código e local."""

from app.dossie.modelos import Fato
from app.vagas.prenota import calcular_prenota, carregar_vocabulario, termos_do_dossie

VOCAB = [
    ["python"],
    ["sql"],
    ["liderança", "leadership"],
    ["aprendizado de máquina", "machine learning", "ml"],
    ["kubernetes", "k8s"],
    ["power bi", "powerbi"],
]


def _fato(i, tipo, texto, **extra) -> Fato:
    return Fato(id=f"F-{i:03d}", tipo=tipo, texto=texto, **extra)


FATOS = [
    _fato(1, "ferramenta", "Python"),
    _fato(2, "resultado", "Liderança de time de 12 pessoas em projetos de machine learning"),
    _fato(3, "ferramenta", "Databricks"),
    _fato(4, "ferramenta", "SQL", status="proposto"),  # proposto não conta
    _fato(5, "contato", "Power BI no nome do e-mail"),  # contato não conta
]


def test_termos_do_dossie_incluem_glossario_e_ferramentas():
    termos, vocab = termos_do_dossie(FATOS, VOCAB)
    assert termos == {"python", "liderança", "aprendizado de máquina", "databricks"}
    assert ["databricks"] in vocab  # ferramenta do dossiê vira termo


def test_prenota_e_a_parte_dos_termos_da_vaga_que_o_dossie_tem():
    termos, vocab = termos_do_dossie(FATOS, VOCAB)
    vaga = (
        "We need strong leadership, Python, SQL and Kubernetes. "
        "Experience with ML and Databricks is a plus."
    )
    nota = calcular_prenota(vaga, termos, vocab)
    # na vaga: leadership, python, sql, kubernetes, ml, databricks (6); no dossiê: 4
    assert nota.valor == 67
    assert set(nota.encontrados) == {"liderança", "python", "aprendizado de máquina", "databricks"}
    assert set(nota.faltando) == {"sql", "kubernetes"}


def test_vaga_sem_termo_conhecido_fica_sem_prenota():
    termos, vocab = termos_do_dossie(FATOS, VOCAB)
    assert calcular_prenota("Vaga de motorista com CNH B.", termos, vocab).valor is None


def test_palavra_dentro_de_outra_nao_conta():
    termos, vocab = termos_do_dossie(FATOS, VOCAB)
    assert calcular_prenota("Experiência com html e xml.", termos, vocab).valor is None


def test_glossario_do_repositorio_carrega():
    vocab = carregar_vocabulario()
    assert len(vocab) > 100
    assert ["power bi", "powerbi"] in vocab
    assert all(grupo and all(isinstance(t, str) for t in grupo) for grupo in vocab)
