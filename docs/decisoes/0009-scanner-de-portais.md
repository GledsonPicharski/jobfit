# 0009 — Scanner de portais: código lê, filtra e ordena; a IA só quando a pessoa pede

Data: 2026-11-15 · Status: aceita

## Contexto

Até a Fase 4b, toda vaga entrava no JobFit porque a pessoa a achou e colou. A Fase 6 traz as vagas até ela: o JobFit lê portais, junta repetidas, aplica filtros e ordena as novas. A regra 1 manda fazer isso em código, e a regra 7 continua valendo (LinkedIn só por link ou texto colado).

## Decisões

| Tema | Decisão | Por quê |
| --- | --- | --- |
| IA no scan | O scan nunca chama a IA. As vagas novas aparecem ordenadas por uma pré-nota em código; a pessoa avalia as que quiser, na tela ou pelo Claude Desktop. | No modo manual, avaliar sozinho geraria dezenas de pedidos de copiar e colar. No modo API, gastaria sem a pessoa escolher. Assim, o scan custa zero em qualquer modo. |
| Pré-nota | De 0 a 100: a parte dos termos relevantes da vaga que aparece nos fatos confirmados do dossiê. O mínimo fica em `config/scanner.yaml`. Abaixo dele, a vaga é guardada, mas escondida por padrão. | Ordenar sem token. A tela diz que é uma estimativa por palavras; a nota de verdade vem da avaliação. |
| Fontes desta fase | ATS por empresa (Greenhouse, Lever, Ashby), boards remotos (Remotive, We Work Remotely, Himalayas, Get on Board) e Gupy. Portais com login viram lembretes. | São as fontes com acesso público e termos que permitem leitura (tabela abaixo). O resto do catálogo fica "em validação". |
| Empresas-alvo | `catalogo/empresas.yaml`, semeado com empresas conferidas ao vivo em 15/11/2026 (quadro público com vagas remotas, LatAm ou Brasil), a partir da lista do career-ops. A pessoa acrescenta as suas em `catalogo_local.yaml`, na pasta de dados. | Os ATS só listam por empresa. A lista local nunca vai para o repositório. |
| Deduplicação | Mesma URL normalizada; depois empresa e título parecidos com local compatível; depois o mesmo texto. A mesma vaga em dois portais vira uma vaga com duas origens (`vaga_origens`). | Vale também contra as vagas coladas: uma vaga colada e depois achada pelo scan não se repete. |
| Filtros | Os da busca salva e, por cima, os critérios do perfil (`aplicar_filtros`). A vaga barrada não vira vaga nova; só conta nas métricas do portal. | Os filtros duros rodam antes de qualquer token (seção 6 do plano). |
| Ritmo | Uma requisição por vez por portal, com pausa entre elas, e intervalo mínimo entre consultas iguais por portal (Remotive: 6 horas). Erro num portal é registrado e não para os outros. | Respeitar quem oferece o acesso. |
| Vaga encerrada | O scan reconfere um número limitado de vagas por rodada e marca as encerradas. A cópia continua no app. | Métrica de "vagas fantasma" por portal e aviso ao abrir a vaga. |
| Agendamento | `jobfit agendar` cria a tarefa no Agendador de Tarefas do Windows com o mesmo Python do ambiente, sem `uv run`. | Como no MCP (0008): o `jobfit.exe` e o `uv run` travam com o app aberto. |

## Fontes conferidas em 15/11/2026

| Fonte | Endpoint | O que os termos e o `robots.txt` dizem | Como o JobFit usa |
| --- | --- | --- | --- |
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{empresa}/jobs` | API pública documentada para quadros de vagas. | Lista por empresa; texto completo só das vagas cujo título passa. |
| Lever | `api.lever.co/v0/postings/{empresa}?mode=json` | API pública documentada. | Lista por empresa, com o texto. |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{empresa}` | API pública documentada. | Lista por empresa, com o texto. |
| Remotive | `remotive.com/api/remote-jobs?search=` | API pública para divulgar as vagas: exige link para a vaga na Remotive e citar a Remotive como fonte; no máximo 4 consultas por dia; vagas com 24 h de atraso. | Link e origem "Remotive" em cada vaga; intervalo mínimo de 6 horas por consulta. |
| We Work Remotely | `weworkremotely.com/categories/{categoria}.rss` | `robots.txt` permite; RSS público. | Feed por categoria. |
| Himalayas | `himalayas.app/jobs/api` | `robots.txt` permite a API e declara `ai-input=yes`. | Lista paginada, filtrada por título em código. |
| Get on Board | `getonbrd.com/api/v0/search/jobs?query=` | API pública documentada; `robots.txt` declara `ai-train=no`, `use=reference` e nada sobre `ai-input`. | Busca por termo. O texto só vai para a IA quando a pessoa escolhe avaliar a vaga, como uma vaga colada. |
| Gupy | `portal.gupy.io/api/job-search/jobs?jobName=` | Endpoint usado pela própria página de busca, não documentado; `robots.txt` libera tudo; os termos de uso para candidatos não proíbem acesso automatizado. | Busca por título, poucas requisições por rodada. Se o endpoint mudar, o leitor registra o erro e as vagas da Gupy continuam entrando por link. |

## Alternativas descartadas

- **Avaliar sozinho no modo API:** gasto sem escolha da pessoa; ficou para quando houver "vagas parecidas" (v1.1), que ordenam melhor.
- **Raspar páginas de portais sem API:** frágil e, em vários casos, contra os termos. Esses portais ficam como lembrete ou "em validação".
- **Busca por site (`site:boards.greenhouse.io`):** exige chave de buscador; fica opcional para depois.

## Consequências

- O scan não registra nenhuma chamada de IA; um teste garante.
- O salário mínimo e o dossiê não saem da máquina: a pré-nota e os filtros rodam localmente.
- As métricas de resultado por portal contam "quero aplicar" até a Fase 5 trazer candidaturas e entrevistas.
