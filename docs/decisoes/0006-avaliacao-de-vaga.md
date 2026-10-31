# 0006 — Avaliação de vaga antes do áudio, numa chamada só

Data: 2026-10-31 · Status: aceita

## Contexto

Pela decisão 0005, o dossiê evolui principalmente pelas avaliações de vagas. O dossiê do autor já tem 117 fatos, então áudio e perguntas de lacuna rendem menos agora do que avaliar vagas reais. O plano previa ainda duas chamadas de IA por vaga, uma para extrair os requisitos e outra para julgá-los, o que no modo manual dá dois copiar e colar por vaga.

## Decisões

| Tema | Decisão | Por quê |
| --- | --- | --- |
| Ordem das fases | A avaliação de vaga (antiga Fase 3) vem antes de áudio e lacunas (antiga Fase 2). Os números das fases ficam como estão no plano | Avaliar vagas reais começa semanas antes, e o feedback das avaliações já completa o dossiê. O áudio volta depois, útil sobretudo para quem começa do zero. |
| Uma tarefa de IA por vaga | `avaliar_vaga` extrai os requisitos e já os julga contra os fatos, com saída validada | Um copiar e colar por vaga no modo manual; em API, uma chamada só, com cache. |
| Checagem depois da IA | O trecho de cada requisito precisa estar na vaga; o ID de fato precisa existir entre os enviados; "atende" ou "parcial" sem fato válido vira "não sei" | Regra 8: o texto da vaga pode tentar manipular a IA, e a nota não pode subir sem fato do dossiê. |
| Nota | Calculada em código (`app/vagas/nota.py`), com pesos, valores, faixas, corte e teto por obrigatório faltando em `config/avaliacao.yaml` | Regra 10: reproduzível, explicável e calibrável pelos evals. |
| Critérios estruturados | Modalidade, cidades, senioridade, salário mínimo e empresas ou palavras a evitar ficam no perfil (`perfil.json`), numa tela própria. O salário mínimo nunca vai para a IA | Os filtros duros rodam em código antes de qualquer token. As preferências do dossiê são texto livre e servem para a IA, não para o filtro. |
| Pré-nota por palavras-chave | Fica para a Fase 6 (scanner) | Na vaga colada, quem escolhe a vaga é a pessoa; barrar por palavra-chave só atrapalharia. |
| Feedback | "Eu tenho isso" vira fato no dossiê (origem `resposta_lacuna`) e muda o julgamento em código; "não tenho", "não se aplica" e "não é bem assim" ajustam só a avaliação daquela vaga. Nenhum deles chama a IA de novo | O que a pessoa afirma já vale como aprovação (0005), e recalcular a nota é aritmética. |
| Concordância | A pessoa marca a faixa que daria a cada vaga; o app mostra quantas batem. `jobfit eval` refaz as avaliações em modo API para comparar prompts e modelos | O critério de pronto pode ser medido sem custo, inclusive no modo manual. |
