from app.dossie.modelos import Periodo
from app.ia.tarefas import FatoExtraido, FatosExtraidos
from app.ingestao.extracao import candidatos_da_ia, checar, mascarar

# Montados em tempo de execução: escritos literais, o pre-commit barra o teste.
EMAIL = "ana.exemplo" + "@exemplo.test"
CELULAR = "(41) 9" + "8765-4321"
CPF = "123.456" + ".789-09"

FONTE = """### Empresa Exemplo (2019 – 2023)

- Liderou a migração do data lake para a nuvem, reduzindo o custo em 30% em 2022.
- Coordenou uma equipe de 8 pessoas — ação contínua com o “time de produto”.
"""


def _fato(**campos) -> FatoExtraido:
    base = {
        "tipo": "resultado",
        "texto": "Reduziu o custo do data lake em 30%",
        "empresa": "Empresa Exemplo",
        "trecho": "reduzindo o custo em 30% em 2022",
    }
    return FatoExtraido.model_validate({**base, **campos})


def _alertas(**campos) -> list[str]:
    return checar(_fato(**campos), FONTE)


def test_fato_fiel_nao_tem_alerta():
    assert _alertas() == []


def test_trecho_ignora_caixa_acentos_espacos_e_pontuacao():
    assert _alertas(trecho="REDUZINDO  o custo em 30%\nem 2022.") == []
    assert _alertas(trecho="Acao continua com o time de produto", texto="Ação contínua") == []


def test_trecho_que_nao_esta_na_fonte():
    alertas = _alertas(trecho="reduzindo o custo em 30% em 2021")
    assert alertas == ["O trecho de origem não está no texto importado."]


def test_trecho_tem_de_ser_palavras_inteiras():
    assert _alertas(trecho="duzindo o cust", texto="Reduziu o custo") != []


def test_numero_do_texto_sem_origem_no_trecho():
    alertas = _alertas(texto="Reduziu o custo em 35% para 200 clientes")
    assert alertas == ["Número sem origem no trecho: 35%, 200."]


def test_numero_com_separador_diferente_e_metricas():
    trecho = "custo em 30% em 2022"
    assert _alertas(trecho=trecho, texto="Reduziu 30,0% do custo") != []
    assert _alertas(trecho=trecho, metricas={"reducao": "30%"}) == []
    assert _alertas(trecho=trecho, metricas={"clientes": 120}) == [
        "Número sem origem no trecho: 120."
    ]


def test_empresa_cargo_e_ano_tem_de_estar_no_texto():
    alertas = _alertas(
        tipo="cargo",
        texto="Gerente — Empresa Inventada",
        empresa="Empresa Inventada",
        cargo="Gerente",
        periodo=Periodo(inicio="2018-01", fim="2023"),
        trecho="Coordenou uma equipe de 8 pessoas",
    )
    assert "Empresa não aparece no texto: Empresa Inventada." in alertas
    assert "Cargo não aparece no texto: Gerente." in alertas
    assert "Ano sem origem no texto: 2018." in alertas
    assert not any("2023" in a for a in alertas)  # está no título da seção


def test_mascarar_tira_contato_e_cpf_e_propoe_contato_fora_da_ia():
    texto = f"Ana — {EMAIL} — {CELULAR}\nCPF {CPF}\nLiderou a migração."
    enviado, contatos = mascarar(texto, "texto")

    assert EMAIL not in enviado and CELULAR not in enviado and CPF not in enviado
    assert "[e-mail omitido]" in enviado and "[CPF omitido]" in enviado
    assert "Liderou a migração." in enviado
    assert [c.texto for c in contatos] == [f"E-mail: {EMAIL}", f"Telefone: {CELULAR}"]
    assert all(c.tipo == "contato" and c.nao_enviar_ia for c in contatos)
    assert all(c.fonte == "texto" for c in contatos)


def test_candidatos_da_ia_levam_fonte_trecho_e_alertas():
    saida = FatosExtraidos(
        fatos=[_fato(), _fato(texto="Reduziu o custo em 90%", trecho="inventado")]
    )
    fiel, inventado = candidatos_da_ia(saida, FONTE, "texto")

    assert fiel.fonte == "texto"
    assert fiel.trecho == "reduzindo o custo em 30% em 2022"
    assert fiel.alertas == []
    assert inventado.alertas  # vai começar rejeitado na revisão
    assert fiel.empresa == "Empresa Exemplo"
