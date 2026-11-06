# 0007 — CV por vaga: o código monta a estrutura, a IA redige, o código confere

Data: 2026-11-05 · Status: aceita

## Contexto

Depois de avaliar uma vaga, o próximo passo é se candidatar com um CV montado para ela, em português ou inglês. A regra 3 exige que nada do CV seja inventado: todo número, data, empresa e cargo precisa de um fato de origem no dossiê. Um CV também precisa ser lido por sistemas de recrutamento (ATS) e caber em 1 a 2 páginas.

## Decisões

| Tema | Decisão | Por quê |
| --- | --- | --- |
| O que é do código | Cabeçalho (nome e contato), cargo, empresa e datas de cada experiência, ordem das seções e formato das datas no idioma | São fatos exatos: a IA não tem o que acrescentar, e o contato nunca precisa ir para o provedor. |
| O que é da IA | Título profissional, resumo, bullets de cada experiência, competências, formação, idiomas e certificações, cada frase com os IDs dos fatos | É redação: escolher, encurtar, traduzir e ordenar pela vaga. |
| Seleção | Em código (`app/cv/selecao.py`, limites em `config/cv.yaml`): só publicáveis; os fatos citados na avaliação da vaga primeiro, depois os com palavras em comum com ela; cargos antigos sem bullets | Princípio 1, e o CV cabe em 1 a 2 páginas sem depender da IA. |
| Uma chamada por CV | `redigir_cv` escreve o CV inteiro de uma vez | Um copiar e colar no modo manual. |
| Checagem que bloqueia | Número, ano ou empresa sem fato citado, ID inexistente e cargo diferente do dossiê bloqueiam o PDF. A checagem vale também para o que a pessoa edita no rascunho | Regra 3: o PDF que sai do app é sempre fiel ao dossiê. |
| Cargo em inglês | Vem de `cargo_en` do fato. Sem ele, a IA propõe a tradução, e a pessoa confirma; a tradução confirmada é gravada como `cargo_en` no fato, direto, com desfazer | Tradução de cargo não dá para checar em código; a confirmação da pessoa vale como fato (0005). |
| PDF | Template HTML de uma coluna, sem tabelas nem imagens, com títulos padrão, gerado pelo Playwright (Chromium). Depois de gerado, o código relê o texto do PDF com `pdfplumber` e confere páginas e ordem | O mesmo resultado em qualquer Windows, e texto que os ATS leem na ordem certa. |
