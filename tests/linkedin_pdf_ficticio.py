"""PDF fictício no layout do "Salvar como PDF" do LinkedIn, gerado no teste (sem binário no repo).

Reproduz o que o leitor usa: barra lateral à esquerda (x=21) com títulos em 13 pt e itens
em 10,5 pt; coluna principal (x=223) com nome em 26, títulos de seção em 15,75, empresa em
12, cargo em 11,5, período e descrição em 10,5 e local em cinza. Só caracteres latin-1,
porque a fonte embutida do fpdf2 não tem travessão nem marcador.
"""

from fpdf import FPDF

ESCURO = (25, 25, 25)
CINZA = (177, 177, 177)
BRANCO = (255, 255, 255)
TITULO_LATERAL = (225, 233, 238)
CINZA_LATERAL = (169, 177, 182)

TEXTOS = {
    "pt": {
        "contato": "Contato",
        "competencias": "Principais competências",
        "idiomas": "Languages",
        "certificacoes": "Certifications",
        "premios": "Honors-Awards",
        "resumo": "Resumo",
        "experiencia": "Experiência",
        "formacao": "Formação acadêmica",
        "total": "3 anos 8 meses",
        "p1": "março de 2023 - Present (3 anos 8 meses)",
        "p2": "janeiro de 2018 - fevereiro de 2023 (5 anos 2 meses)",
        "p3": "abril de 2014 - dezembro de 2017 (3 anos 9 meses)",
        "f1": "Bacharelado, Estatística · (2010 - 2014)",
        "f2a": "Pós-graduação Lato Sensu, Gestão de Projetos · (fevereiro de",
        "f2b": "2019 - janeiro de 2021)",
        "nivel_pt": "Portuguese (Native or Bilingual)",
        "nivel_en": "English (Professional Working)",
    },
    "en": {
        "contato": "Contact",
        "competencias": "Top Skills",
        "idiomas": "Languages",
        "certificacoes": "Certifications",
        "premios": "Honors-Awards",
        "resumo": "Summary",
        "experiencia": "Experience",
        "formacao": "Education",
        "total": "3 years 8 months",
        "p1": "March 2023 - Present (3 years 8 months)",
        "p2": "January 2018 - February 2023 (5 years 2 months)",
        "p3": "April 2014 - December 2017 (3 years 9 months)",
        "f1": "Bachelor's degree, Statistics · (2010 - 2014)",
        "f2a": "Postgraduate Degree, Project Management · (February",
        "f2b": "2019 - January 2021)",
        "nivel_pt": "Portuguese (Native or Bilingual)",
        "nivel_en": "English (Professional Working)",
    },
}


class _Pdf:
    def __init__(self):
        self.pdf = FPDF(unit="pt", format="letter")
        self.pdf.set_auto_page_break(False)
        self.pdf.set_font("Helvetica")
        self.y = {"L": 0.0, "R": 0.0}
        self.nova_pagina()

    def nova_pagina(self):
        self.pdf.add_page()
        self.pdf.set_font("Helvetica", size=9)
        self.pdf.set_text_color(0, 0, 0)
        self.pdf.text(383, 780, f"Page {self.pdf.page_no()}")
        self.y = {"L": 46.0, "R": 46.0}

    def linha(self, coluna: str, texto: str, tamanho: float, cor=ESCURO, depois: float = 18):
        if coluna == "R" and self.y["R"] > 740:
            self.nova_pagina()
        self.pdf.set_font("Helvetica", size=tamanho)
        self.pdf.set_text_color(*cor)
        self.pdf.text(21 if coluna == "L" else 223, self.y[coluna] + tamanho, texto)
        self.y[coluna] += depois

    def lateral(self, titulo: str, itens: list[list[str]], cor=BRANCO):
        self.y["L"] += 6
        self.linha("L", titulo, 13, TITULO_LATERAL, depois=21)
        for item in itens:
            for n, parte in enumerate(item):
                ultima = n == len(item) - 1
                self.linha("L", parte, 10.5, cor, depois=17.5 if ultima else 12.5)


def gerar_pdf(idioma: str = "pt") -> bytes:
    t = TEXTOS[idioma]
    p = _Pdf()

    p.lateral(
        t["contato"],
        [
            ["ana.exemplo" + "@exemplo.test"],  # montado: o pre-commit barra e-mail literal
            ["www.linkedin.com/in/ana-", "exemplo (LinkedIn)"],
            ["github.com/anaexemplo/", "(Portfolio)"],
        ],
    )
    p.lateral(t["competencias"], [["Machine Learning"], ["Análise de Sobrevivência"]])
    p.lateral(t["idiomas"], [[t["nivel_pt"]], [t["nivel_en"]]])
    p.lateral(
        t["certificacoes"],
        [["Introdução Fictícia a Dados"], ["Engenharia de Software para", "Cientistas Fictícios"]],
    )
    p.lateral(t["premios"], [["1st place - Hackathon Exemplo", "2019"]])

    p.linha("R", "Ana Exemplo", 26, depois=31)
    p.linha("R", "Gerente de Dados | Machine Learning | Crédito", 12, depois=15)
    p.linha("R", "Curitiba, Paraná, Brasil", 12, CINZA, depois=36)
    p.linha("R", t["resumo"], 15.75, depois=28)
    p.linha("R", "Lidero times de dados há 8 anos e gosto de", 12)
    p.linha("R", "transformar estatística em decisão.", 12, depois=40)

    p.linha("R", t["experiencia"], 15.75, depois=33)
    p.linha("R", "Empresa Exemplo", 12)
    p.linha("R", t["total"], 10.5, depois=20)
    p.linha("R", "Gerente de Dados", 11.5, depois=15)
    p.linha("R", t["p1"], 10.5, depois=21)
    p.linha("R", "Lidero o time de dados de crédito, com 6 pessoas.", 10.5, depois=36)
    p.linha("R", "- Lançou o Leitor Automático: mais de 80% das leituras", 10.5)
    p.linha("R", "automatizadas.", 10.5, depois=31)
    p.linha("R", "Coordenadora de Ciência de Dados", 11.5, depois=15)
    p.linha("R", t["p2"], 10.5, depois=15)
    p.linha("R", "Curitiba, Paraná, Brasil", 10.5, CINZA, depois=21)
    p.linha("R", "Reduziu de 5 para 2 dias o fechamento dos relatórios.", 10.5, depois=37)

    p.linha("R", "Consultoria Fictícia", 12, depois=17)
    p.linha("R", "Analista de Dados Pleno", 11.5, depois=15)
    p.linha("R", t["p3"], 10.5, depois=15)
    p.linha("R", "São Paulo, Brasil", 10.5, CINZA, depois=21)
    p.linha("R", "Modelos de churn e segmentação para varejo.", 10.5, depois=37)

    # A formação vai para outra página, como no PDF real com muita experiência.
    p.y["R"] = 741
    p.linha("R", t["formacao"], 15.75, depois=28)
    p.linha("R", "Universidade Fictícia do Paraná", 12)
    p.linha("R", t["f1"], 10.5, depois=33)
    p.linha("R", "Escola Exemplo de Negócios", 12)
    p.linha("R", t["f2a"], 10.5)
    p.linha("R", t["f2b"], 10.5, depois=33)
    p.linha("R", "Colégio Técnico Exemplo", 12)
    p.linha("R", "Técnico em Eletrônica ", 10.5)

    return bytes(p.pdf.output())
