"""Os dados "sensíveis" deste teste são montados em tempo de execução: escritos
literalmente, o próprio hook barraria este arquivo."""

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "checar_dados_pessoais", RAIZ / "scripts" / "checar_dados_pessoais.py"
)
checar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checar)

ARROBA = "@"
REAIS = "R" + "$"


def cpf_valido(base: str = "529982247") -> str:
    digitos = [int(d) for d in base]
    for tamanho in (10, 11):
        soma = sum(d * peso for d, peso in zip(digitos, range(tamanho, 1, -1), strict=False))
        digitos.append(0 if soma % 11 < 2 else 11 - soma % 11)
    return "".join(map(str, digitos))


def tipos(texto: str, termos=()) -> list[str]:
    return [a.tipo for a in checar.verificar_texto(texto, list(termos))]


def formatar(cpf: str) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def test_cpf_valido_e_barrado_com_e_sem_pontuacao():
    cpf = cpf_valido()
    assert tipos(f"CPF: {formatar(cpf)}") == ["CPF"]
    assert tipos(f"cpf={cpf}") == ["CPF"]


def test_cpf_com_digito_errado_passa():
    cpf = cpf_valido()
    errado = cpf[:-1] + str((int(cpf[-1]) + 1) % 10)
    assert tipos(formatar(errado)) == []


def test_cpf_com_digitos_repetidos_passa():
    assert tipos("111.111.111-11") == []


def test_numero_dentro_de_hash_passa():
    assert tipos(f"sha256:ab{cpf_valido()}cd") == []


@pytest.mark.parametrize(
    "email",
    [
        f"ana{ARROBA}exemplo.com",
        f"ana.exemplo{ARROBA}mail.exemplo.com.br",
        f"noreply{ARROBA}anthropic.com",
        f"git{ARROBA}github.com",
        f"123+fulano{ARROBA}users.noreply.github.com",
    ],
)
def test_emails_permitidos_passam(email):
    assert tipos(f"contato: {email}") == []


def test_email_real_e_barrado():
    assert tipos(f"contato: ana.souza{ARROBA}gmail.com") == ["e-mail"]


def test_decorador_python_nao_e_email():
    assert tipos("@app.get('/')\n@router.post('/x')") == []
    assert tipos(r"codigo = 'linha\n@router.post'") == []  # "\n" literal no código-fonte


def test_valor_em_reais_e_barrado():
    assert tipos(f"pretensão: {REAIS} 15.000") == ["valor em R$"]
    assert tipos(f"{REAIS}12000") == ["valor em R$"]


def test_mencao_a_reais_sem_valor_passa():
    assert tipos(f"valores em {REAIS} ficam privados") == []


def test_telefone_celular_e_barrado():
    assert tipos("whatsapp (41) 9" + "8765-4321") == ["telefone"]


def test_termo_da_lista_local_ignora_caixa_e_acento():
    assert tipos("Camila Conceicao", ["conceição"]) == ["lista local"]
    assert tipos("CONCEIÇÃO", ["Conceicao"]) == ["lista local"]
    assert tipos("Camila", ["conceição"]) == []


def test_ler_lista_local_ignora_comentarios_e_linhas_curtas(tmp_path):
    lista = tmp_path / ".dados-sensiveis.txt"
    lista.write_text("# nomes reais\nSouza\n\nab\n  Conceição  \n", encoding="utf-8")
    assert checar.ler_lista_local(lista) == ["Souza", "Conceição"]


def test_lista_local_ausente_nao_quebra(tmp_path):
    assert checar.ler_lista_local(tmp_path / "nao-existe.txt") == []


def test_main_barra_e_mascara_o_valor(tmp_path, capsys):
    cpf = cpf_valido()
    arquivo = tmp_path / "nota.md"
    arquivo.write_text(f"linha 1\nCPF {formatar(cpf)}\n", encoding="utf-8")

    assert checar.main([str(arquivo)]) == 1
    saida = capsys.readouterr().out
    assert "nota.md:2: CPF" in saida
    assert cpf not in saida and formatar(cpf) not in saida  # o log da CI é público


def test_main_passa_arquivo_limpo_e_ignora_binario(tmp_path):
    limpo = tmp_path / "limpo.md"
    limpo.write_text("Gestão de dados — sem nada pessoal.\n", encoding="utf-8")
    binario = tmp_path / "foto.png"
    binario.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe" + cpf_valido().encode())
    assert checar.main([str(limpo), str(binario)]) == 0


def test_repositorio_atual_esta_limpo(monkeypatch):
    monkeypatch.setattr(checar, "LISTA_LOCAL", RAIZ / "nao-usar-lista-local-no-teste")
    monkeypatch.chdir(RAIZ)
    assert checar.main([]) == 0
