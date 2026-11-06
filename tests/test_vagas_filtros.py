from decimal import Decimal

from app.perfis.modelos import Criterios
from app.vagas.filtros import aplicar_filtros
from app.vagas.metadados import Metadados, Salario

TEXTO = "Cientista de Dados Sênior para o time de crédito — ação contínua."


def _filtrar(meta=None, criterios=None, texto=TEXTO, ingles_declarado=3):
    return aplicar_filtros(meta or Metadados(), texto, criterios or Criterios(), ingles_declarado)


def test_sem_criterios_nada_bloqueia():
    resultado = _filtrar(Metadados(modalidade="presencial", local="Manaus"))
    assert not resultado.bloqueada and resultado.bloqueios == []


def test_modalidade_fora_do_aceito_bloqueia():
    resultado = _filtrar(Metadados(modalidade="presencial"), Criterios(modalidades=["remoto"]))
    assert resultado.bloqueada
    assert resultado.bloqueios == ["Modalidade presencial; você aceita: remoto."]


def test_presencial_em_outra_cidade_bloqueia_e_na_sua_passa():
    criterios = Criterios(cidades=["Curitiba", "São José dos Pinhais"])
    fora = _filtrar(Metadados(modalidade="presencial", local="São Paulo - SP"), criterios)
    assert fora.bloqueios == [
        "Vaga em São Paulo - SP; você aceita híbrido ou presencial só em "
        "Curitiba, São José dos Pinhais."
    ]
    dentro = _filtrar(Metadados(modalidade="hibrido", local="Curitiba, PR"), criterios)
    assert not dentro.bloqueada


def test_remoto_nao_olha_cidade():
    criterios = Criterios(cidades=["Curitiba"])
    assert not _filtrar(Metadados(modalidade="remoto", local="São Paulo"), criterios).bloqueada


def test_cidade_desconhecida_so_alerta():
    criterios = Criterios(cidades=["Curitiba"])
    resultado = _filtrar(Metadados(modalidade="presencial"), criterios)
    assert not resultado.bloqueada
    assert resultado.alertas == ["Vaga presencial sem cidade identificada: confira o local."]


def test_modalidade_desconhecida_nao_bloqueia():
    assert not _filtrar(Metadados(), Criterios(modalidades=["remoto"])).bloqueada


def test_salario_abaixo_do_minimo_bloqueia_sem_mostrar_o_minimo_em_outro_lugar():
    criterios = Criterios(salario_minimo=Decimal(15000))
    meta = Metadados(salario=Salario("BRL", Decimal(9000), Decimal(12000)))
    resultado = _filtrar(meta, criterios)
    assert resultado.bloqueada
    assert resultado.bloqueios == ["Salário informado (até 12.000 por mês) abaixo do seu mínimo."]


def test_salario_dentro_da_faixa_e_em_dolar():
    criterios = Criterios(salario_minimo=Decimal(15000))
    na_faixa = Metadados(salario=Salario("BRL", Decimal(12000), Decimal(16000)))
    assert not _filtrar(na_faixa, criterios).bloqueada
    dolar = _filtrar(Metadados(salario=Salario("USD", Decimal(3000), Decimal(3000))), criterios)
    assert not dolar.bloqueada
    assert dolar.alertas == ["Salário em dólar (até 3.000 por mês): compare com o seu mínimo."]


def test_empresa_e_palavra_evitadas_bloqueiam():
    criterios = Criterios(
        empresas_evitar=["Imobiliária Exemplo"], palavras_evitar=["mercado imobiliário"]
    )
    empresa = _filtrar(Metadados(empresa="Imobiliária Exemplo S.A."), criterios)
    assert empresa.bloqueios == ["Empresa na sua lista de evitar: Imobiliária Exemplo."]
    palavra = _filtrar(texto="Fintech do Mercado Imobiliario em expansão", criterios=criterios)
    assert palavra.bloqueios == ["A vaga menciona algo que você evita: mercado imobiliário."]


def test_palavra_evitada_so_inteira():
    criterios = Criterios(palavras_evitar=["cripto"])
    assert not _filtrar(texto="Criptografia de dados", criterios=criterios).bloqueada


def test_senioridade_e_ingles_so_alertam():
    criterios = Criterios(senioridades=["senior", "gestao"])
    resultado = _filtrar(Metadados(senioridade="junior", ingles=4), criterios, ingles_declarado=3)
    assert not resultado.bloqueada
    assert resultado.alertas == [
        "Senioridade júnior; você busca: sênior, gestão (coordenação, gerência, head).",
        "A vaga pede inglês fluente; o seu dossiê diz avançado.",
    ]


def test_ingles_sem_nivel_no_dossie():
    resultado = _filtrar(Metadados(ingles=3), ingles_declarado=None)
    assert resultado.alertas == [
        "A vaga pede inglês avançado; o seu dossiê não diz o seu nível de inglês."
    ]
