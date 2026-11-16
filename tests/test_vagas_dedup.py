"""Deduplicação em código: a mesma vaga em dois portais (ou colada antes) é uma vaga só."""

from app.vagas.dedup import Candidata, Indice, mesma_empresa, titulo_parecido


def _c(**campos) -> Candidata:
    base = {"url": None, "empresa": None, "titulo": None, "local": None, "hash": None}
    return Candidata(**(base | campos))


def test_mesma_url_normalizada():
    indice = Indice()
    indice.adicionar(1, _c(url="https://jobs.lever.co/yuno/abc"))
    assert indice.procurar(_c(url="https://jobs.lever.co/yuno/abc/?utm_source=x#topo")) == 1
    assert indice.procurar(_c(url="https://jobs.lever.co/yuno/outra")) is None


def test_mesmo_texto():
    indice = Indice()
    indice.adicionar(7, _c(hash="abc"))
    assert indice.procurar(_c(hash="abc", url="https://outro.portal/vaga")) == 7


def test_mesma_empresa_e_titulo_em_portais_diferentes():
    indice = Indice()
    indice.adicionar(
        3,
        _c(
            url="https://boards.greenhouse.io/clara/jobs/1",
            empresa="Clara",
            titulo="Senior Data Engineer",
            local="Remote - LATAM",
        ),
    )
    repetida = _c(
        url="https://himalayas.app/companies/clara/jobs/senior-data-engineer",
        empresa="Clara Inc.",
        titulo="Senior Data Engineer (Remote)",
        local="Brazil",
    )
    assert indice.procurar(repetida) == 3


def test_titulo_de_outro_nivel_nao_e_a_mesma_vaga():
    indice = Indice()
    indice.adicionar(3, _c(empresa="Clara", titulo="Senior Data Engineer"))
    assert indice.procurar(_c(empresa="Clara", titulo="Data Engineer")) is None
    assert indice.procurar(_c(empresa="Clara", titulo="Staff Data Engineer")) is None
    assert indice.procurar(_c(empresa="Stone", titulo="Senior Data Engineer")) is None


def test_mesmo_titulo_em_cidades_diferentes_sao_vagas_diferentes():
    indice = Indice()
    indice.adicionar(1, _c(empresa="Stone", titulo="Gerente de Dados", local="São Paulo, SP"))
    assert (
        indice.procurar(_c(empresa="Stone", titulo="Gerente de Dados", local="Recife - PE")) is None
    )
    # local ausente ou remoto não separa
    assert indice.procurar(_c(empresa="Stone", titulo="Gerente de Dados")) == 1
    assert indice.procurar(_c(empresa="Stone", titulo="Gerente de Dados", local="Remoto")) == 1
    assert indice.procurar(_c(empresa="Stone", titulo="Gerente de Dados", local="Sao Paulo")) == 1


def test_sem_empresa_nao_compara_por_titulo():
    indice = Indice()
    indice.adicionar(1, _c(titulo="Gerente de Dados"))
    assert indice.procurar(_c(titulo="Gerente de Dados")) is None


def test_mesma_empresa_ignora_sufixos_e_acentos():
    assert mesma_empresa("Nubank", "nubank")
    assert mesma_empresa("Clara Inc.", "Clara")
    assert mesma_empresa("Stone Pagamentos S.A.", "Stone Pagamentos")
    assert mesma_empresa("Itaú Unibanco", "Itau Unibanco Ltda")
    assert not mesma_empresa("Stone", "Stonex")
    assert not mesma_empresa("", "")


def test_titulo_parecido():
    assert titulo_parecido("Gerente de Dados Sênior", "Gerente Senior de Dados")
    assert titulo_parecido("Head of Data — LATAM", "Head of Data")
    assert titulo_parecido("Data Manager (m/f/d)", "Data Manager")
    assert not titulo_parecido("Gerente de Dados", "Gerente de Produto")
    assert not titulo_parecido("Analytics Engineer", "Analytics Engineering Manager")
