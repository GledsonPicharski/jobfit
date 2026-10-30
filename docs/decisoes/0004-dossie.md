# 0004 — Dossiê (Fase 1)

**Data:** 30/10/2026 · **Status:** aceita

## Contexto

A Fase 1 transforma o formato da seção 4 do `PLANO.md` em código. O dossiê é editado por duas mãos, a do app e a da pessoa (no editor ou pelo Drive no celular), e precisa sobreviver às duas sem perda. Alguns pontos do plano ficaram mais precisos na implementação.

## Decisões

| Tema | Decisão | Por quê |
| --- | --- | --- |
| Ida e volta | Blocos `fatos` não alterados são gravados byte a byte como foram lidos; só o bloco com fato alterado é reserializado (PyYAML, ordem fixa de campos) | Comentários e formatação feitos à mão não somem quando o app grava. O custo: comentários dentro de um bloco alterado se perdem. |
| Windows | BOM e CRLF são normalizados na leitura; a gravação é UTF-8 com LF | O Bloco de Notas grava BOM e CRLF. |
| Campos novos | `cargo` e `periodo: {inicio, fim}` com datas ISO parciais (`2023`, `2023-03`); `fim` vazio ou `atual` quer dizer atual | A checagem de fatos do CV (Fase 4) compara cargo e datas; texto livre não dá para checar. |
| Campos desconhecidos | Preservados (`extra="allow"`) | Quem edita à mão pode anotar o que quiser. |
| Tipos novos | Além dos 10 do plano: `contato`, `docencia`, `mentoria`, `premio`, `publicacao` e `lacuna`, cada um com sua seção (contato fica na seção 0, junto das instruções) | Vieram da migração do dossiê real: sem eles, contato, docência, publicações e lacunas não teriam onde morar. Lacunas alimentam a avaliação de vagas (Fase 3). |
| `tipo` | Gravado sem acento (`competencia`); na leitura, aceita acento e maiúscula | Quem edita à mão escreve "Competência". |
| Erros | Sempre com a linha do arquivo; com o dossiê quebrado o app não grava nada | O arquivo é da pessoa; o app não pode "consertar" apagando. |
| Propostas | `proposto` e `rejeitado` das importações ficam no banco do perfil, não no `dossie.md` | O arquivo fica limpo e legível no celular. |
| `proposto` escrito à mão | Continua válido no arquivo; a tela do Dossiê lista esses fatos e oferece Confirmar e Rejeitar (o rejeitado fica no arquivo, com `status: rejeitado`, e pode ser confirmado depois) | Regra 4: quem migra um dossiê marca o que ainda precisa conferir, e a confirmação acontece no app. |
| Rejeitado e a IA | `fatos_para_ia` também exclui `rejeitado` | Fato rejeitado não é fato; não pode orientar a avaliação. |
| LinkedIn em PDF | Experiências, formação, competências, idiomas e certificações lidas em código; a IA só lê as descrições | Princípio 1: a estrutura do PDF do LinkedIn é previsível. |
| Anti-invenção na extração | O `trecho` citado pela IA precisa existir na fonte, e todo número do fato precisa estar no trecho; se não, a proposta vem com alerta e começa rejeitada | Regra 3, checada em código desde a entrada. |
| Erros do Pydantic | Tradução única em `app/validacao.py`, usada pelo modo manual e pelo dossiê | Uma mensagem em português para o mesmo erro, em qualquer tela. |

## Consequências

- `app/dossie/filtros.py` concentra a regra 5; nenhum outro módulo filtra `privado` ou `nao_enviar_ia` por conta própria.
- A edição livre de texto continua no `.md`; no app, a pessoa só alterna 🔒 e "não enviar à IA" e decide propostas.
