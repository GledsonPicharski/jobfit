# 0005 — Dossiê de referência que evolui com o uso

Data: 2026-10-30 · Status: aceita · Revê parte da 0004

## Contexto

A primeira versão da Fase 1 tratava toda entrada da mesma forma: cada item virava um cartão, com aprovar, editar e rejeitar. No uso real, isso ficou verboso. Para montar o dossiê a partir do LinkedIn, eram dezenas de cliques. Além disso, o menu pendurava os custos de IA no nome do perfil e dava o mesmo peso a trocar de perfil e a abrir o dossiê.

O dossiê é a referência da pessoa. Ele nasce de uma vez e depois melhora aos poucos, principalmente pelas avaliações de vagas.

## Decisões

| Tema | Decisão | Por quê |
| --- | --- | --- |
| Regra 4, nova leitura | Nada é gravado em silêncio. A aprovação pode valer para um lote inteiro, e o que a própria pessoa afirma já vale como aprovação | A regra existe para a IA não pôr palavras na boca de ninguém, não para obrigar um clique por fato. |
| Dossiê inicial | Três caminhos na tela do dossiê vazio: o PDF do LinkedIn vira um rascunho aprovado de uma vez ("Usar como meu dossiê"); um dossiê pronto no formato do JobFit é adotado direto; à mão, com "+ Adicionar" em cada seção | Cada pessoa chega com um material diferente. |
| Um campo para qualquer arquivo | O tipo sai do conteúdo: PDF do LinkedIn (pelo layout), outro PDF ou DOCX (CV), `.md` com blocos `fatos` (dossiê), outro texto (IA) | A pessoa não precisa saber qual botão usar. |
| Atualizar depois | Uma lista compacta só com o que muda, agrupada por tipo. Os itens vêm marcados, menos os que têm alerta da checagem anti-invenção. Os conflitos ficam no topo, com a sugestão marcada, e um botão aplica tudo. O desmarcado conta como rejeitado e não volta | Revisar vira conferir uma lista, não decidir item a item. |
| Desfazer | Depois de aplicar, o aviso oferece "Desfazer": a versão anterior volta como versão nova (motivo `restauracao`) | As versões já existiam, então errar fica barato. |
| Edição no app | "+ Adicionar" e "Remover" gravam direto, com origem `manual`. As ações de cada fato ficam num menu "⋯" | O que a pessoa escreve é dela. Remover deixa o fato no histórico, e os comentários vizinhos são preservados. |
| Avaliação de vagas (Fase 3) | "Eu tenho isso" e "isso está errado" entram direto, com "desfazer". Vira pergunta só quando a IA reescreve o que a pessoa disse | É a principal fonte de evolução do dossiê. |
| Menu | JobFit · Início · Dossiê (Vagas e Candidaturas quando existirem). No nome do perfil, um menu com Configurar IA, Custos e chamadas, Trocar de perfil, Novo perfil e Excluir perfil. Abrir o app leva ao último perfil usado | A pessoa olha para o próprio perfil; trocar de perfil é raro. |
| Início | Mostra o estado do dossiê e o próximo passo. Os custos vão para "Custos e chamadas" | O que mais importa fica na primeira tela. |

## Consequências

- Saem as telas de cartão por proposta (HTMX), "aprovar pendentes" e "gravar". Entra `POST /importacoes/{id}/aplicar`.
- `rejeitados_anteriores` continua valendo: o desmarcado num lote aplicado não é proposto de novo. Descartar não conta como rejeitar.
