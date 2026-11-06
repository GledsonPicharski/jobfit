from datetime import date
from pathlib import Path

from app.cv.checagem import checar, limpar_ids
from app.cv.modelos import Experiencia, Frase, Rascunho
from app.dossie.formato import ler_dossie
from app.dossie.modelos import Fato

RAIZ = Path(__file__).resolve().parents[1]
DOC = ler_dossie((RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8"))
FATOS = {f.id: f for f in DOC.fatos}
HOJE = date(2026, 11, 5)


def _rascunho(**campos) -> Rascunho:
    base = {
        "idioma": "pt",
        "titulo": Frase(texto="Gerente de Dados e IA", fatos=["F-010"]),
        "experiencias": [
            Experiencia(
                cargo_id="F-010",
                titulo="Gerente de Dados e IA",
                bullets=[
                    Frase(
                        texto="Lançou o Leitor Automático: mais de 80% das leituras.",
                        fatos=["F-014"],
                    )
                ],
            ),
            Experiencia(
                cargo_id="F-020",
                titulo="Analista de Dados Sênior",
                bullets=[
                    Frase(
                        texto="Reduziu de 5 para 2 dias o fechamento dos relatórios.",
                        fatos=["F-021"],
                    )
                ],
            ),
        ],
        "formacao": [Frase(texto="Bacharelado em Estatística (2010–2014)", fatos=["F-030"])],
    }
    return Rascunho.model_validate({**base, **campos})


def _checar(rascunho, empresa_vaga=None, fatos=FATOS):
    return checar(rascunho, fatos, empresa_vaga=empresa_vaga, hoje=HOJE)


def _mensagens(checagem, caminho):
    return [p.mensagem for p in checagem.problemas.get(caminho, [])]


def test_rascunho_fiel_nao_tem_bloqueio():
    checagem = _checar(_rascunho())
    assert checagem.bloqueios == 0
    assert checagem.problemas == {}


def test_numero_falso_colado_a_mao_bloqueia():
    rascunho = _rascunho()
    rascunho.experiencias[0].bullets[0].texto = "Automatizou 95% das leituras de documentos."
    checagem = _checar(rascunho)
    assert checagem.bloqueios == 1
    assert _mensagens(checagem, "experiencias.0.bullets.0") == ["Número sem fato de origem: 95%."]


def test_numero_com_outro_formato_passa():
    rascunho = _rascunho()
    rascunho.experiencias[1].bullets[0].texto = "Cut report closing from 5 to 2 days."
    assert _checar(rascunho).bloqueios == 0


def test_ano_sem_fato_bloqueia():
    rascunho = _rascunho(
        formacao=[Frase(texto="Bacharelado em Estatística (2009–2014)", fatos=["F-030"])]
    )
    assert _mensagens(_checar(rascunho), "formacao.0") == ["Ano sem fato de origem: 2009."]


def test_anos_de_experiencia_calculados_dos_cargos_passam():
    # cargos de 2018 a hoje: 8 anos; "mais de 8" é verdade, "15" não é
    ok = _rascunho(resumo=[Frase(texto="Mais de 8 anos com dados.", fatos=["F-010", "F-020"])])
    assert _checar(ok).bloqueios == 0
    exagero = _rascunho(resumo=[Frase(texto="15 anos com dados.", fatos=["F-010", "F-020"])])
    assert _mensagens(_checar(exagero), "resumo.0") == ["Número sem fato de origem: 15."]


def test_frase_sem_fato_bloqueia():
    rascunho = _rascunho(resumo=[Frase(texto="Profissional apaixonada por dados.", fatos=[])])
    assert _mensagens(_checar(rascunho), "resumo.0") == ["Frase sem fato do dossiê."]


def test_empresa_de_outro_fato_bloqueia():
    rascunho = _rascunho()
    rascunho.experiencias[0].bullets[
        0
    ].texto = "Lançou na Consultoria Fictícia o Leitor Automático, com mais de 80% das leituras."
    assert _mensagens(_checar(rascunho), "experiencias.0.bullets.0") == [
        "Cita Consultoria Fictícia, que não está nos fatos desta frase."
    ]


def test_empresa_da_vaga_citada_como_sua_bloqueia():
    rascunho = _rascunho(resumo=[Frase(texto="Gerente de dados na Banco Alvo.", fatos=["F-010"])])
    assert _mensagens(_checar(rascunho, empresa_vaga="Banco Alvo"), "resumo.0") == [
        "Cita Banco Alvo, a empresa da vaga, como se fosse sua."
    ]


def test_cargo_trocado_a_mao_bloqueia():
    rascunho = _rascunho()
    rascunho.experiencias[0].titulo = "Head de Dados e IA"
    assert _mensagens(_checar(rascunho), "experiencias.0.titulo") == [
        "Cargo diferente do dossiê (Gerente de Dados e IA)."
    ]


def test_cargo_em_ingles_precisa_de_cargo_en_ou_confirmacao():
    rascunho = _rascunho(idioma="en")
    rascunho.experiencias[0].titulo = "Data & AI Manager"
    assert _mensagens(_checar(rascunho), "experiencias.0.titulo") == [
        "Tradução do cargo pela IA: confirme ou use o do dossiê (Gerente de Dados e IA)."
    ]
    com_traducao = dict(FATOS)
    f010 = FATOS["F-010"].model_dump()
    com_traducao["F-010"] = Fato.model_validate({**f010, "cargo_en": "Data & AI Manager"})
    assert _checar(rascunho, fatos=com_traducao).problemas == {}
    rascunho.experiencias[0].titulo = "Gerente de Dados e IA"  # o original também vale
    assert _checar(rascunho).problemas == {}


def test_cargo_que_nao_existe_bloqueia():
    rascunho = _rascunho()
    rascunho.experiencias[0].cargo_id = "F-014"  # é um resultado, não um cargo
    assert _mensagens(_checar(rascunho), "experiencias.0.titulo") == [
        "O cargo F-014 não está no dossiê."
    ]


def test_frase_longa_e_competencia_repetida_so_alertam():
    longa = "Lançou o Leitor Automático " + "com ganhos claros " * 20
    rascunho = _rascunho(
        resumo=[Frase(texto=longa, fatos=["F-014"])],
        competencias=[
            Frase(texto="Python", fatos=["F-041"]),
            Frase(texto="python", fatos=["F-041"]),
        ],
    )
    checagem = _checar(rascunho)
    assert checagem.bloqueios == 0
    assert checagem.alertas == 2
    assert _mensagens(checagem, "competencias.1") == ["Competência repetida."]


def test_limpar_ids_tira_os_inventados_e_conta():
    rascunho = _rascunho(resumo=[Frase(texto="Lidera dados.", fatos=["F-010", "F-999", "F-002"])])
    limpo, removidos = limpar_ids(rascunho, {"F-010", "F-014", "F-020", "F-021", "F-030"})
    assert limpo.resumo[0].fatos == ["F-010"]
    assert removidos == ["F-999", "F-002"]  # F-002 existe, mas é 🔒: não foi enviado
