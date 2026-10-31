# 0004 — Dossiê (Fase 1)

**Data:** 30/10/2026 · **Status:** aceita

## Contexto

A Fase 1 transforma o formato da seção 4 do `PLANO.md` em código. O dossiê é editado por duas mãos, a do app e a da pessoa (no editor ou pelo Drive no celular), e precisa sobreviver às duas sem perda. Alguns pontos do plano ficaram mais precisos na implementação.

## Decisões

| Tema | Decisão | Por quê |
| --- | --- | --- |
| Ida e volta | O que não foi alterado é gravado byte a byte como foi lido; num bloco alterado, só o fato que mudou é reserializado (PyYAML, ordem fixa de campos), e os vizinhos e os comentários entre fatos ficam como estavam | Comentários, aspas e formatação feitos à mão não somem quando o app grava, e o diff da versão mostra só o fato mudado. O custo: um comentário na mesma linha de um campo do fato alterado se perde. |
| Windows | BOM e CRLF são normalizados na leitura; a gravação é UTF-8 com LF | O Bloco de Notas grava BOM e CRLF. |
| Campos novos | `cargo` e `periodo: {inicio, fim}` com datas ISO parciais (`2023`, `2023-03`); `fim` vazio ou `atual` quer dizer atual | A checagem de fatos do CV (Fase 4) compara cargo e datas; texto livre não dá para checar. |
| Campos desconhecidos | Preservados (`extra="allow"`) | Quem edita à mão pode anotar o que quiser. |
| Tipos novos | Além dos 10 do plano: `contato`, `docencia`, `mentoria`, `premio`, `publicacao` e `lacuna`, cada um com sua seção (contato fica na seção 0, junto das instruções) | Vieram da migração do dossiê real: sem eles, contato, docência, publicações e lacunas não teriam onde morar. Lacunas alimentam a avaliação de vagas (Fase 3). |
| `tipo` | Gravado sem acento (`competencia`); na leitura, aceita acento e maiúscula | Quem edita à mão escreve "Competência". |
| Erros | Sempre com a linha do arquivo; com o dossiê quebrado o app não grava nada | O arquivo é da pessoa; o app não pode "consertar" apagando. |
| Propostas | `proposto` e `rejeitado` das importações ficam no banco do perfil, não no `dossie.md` | O arquivo fica limpo e legível no celular. |
| `proposto` escrito à mão | Continua válido no arquivo; a tela do Dossiê lista esses fatos e oferece Confirmar e Rejeitar (o rejeitado fica no arquivo, com `status: rejeitado`, e pode ser confirmado depois) | Regra 4: quem migra um dossiê marca o que ainda precisa conferir, e a confirmação acontece no app. |
| Rejeitado e a IA | `fatos_para_ia` também exclui `rejeitado` | Fato rejeitado não é fato; não pode orientar a avaliação. |
| Já registrado | A montagem compara pela identidade de cada tipo, não pelo texto inteiro: cargo pela empresa (uma contida na outra) e pelo início, ou pelo título; idioma pelo nome; formação pela instituição e pelo ano; os demais pelo texto contido palavra por palavra (ou pela sigla entre parênteses). Competência e ferramenta são o mesmo assunto | O dossiê é mais rico que o LinkedIn e escreve o mesmo fato com outras palavras ("Português: nativo" × "Portuguese (Native or Bilingual)"). No dossiê real, 30 dos 32 itens do PDF foram reconhecidos; o resto é proposto, e o rejeitado não volta. |
| LinkedIn em PDF | Experiências, formação, competências, idiomas e certificações lidas em código; a IA só lê as descrições | Princípio 1: a estrutura do PDF do LinkedIn é previsível. |
| Anti-invenção na extração | O `trecho` citado pela IA precisa existir na fonte, e todo número do fato precisa estar no trecho; empresa, cargo e anos do período precisam aparecer no texto. Se não, a proposta vem com alerta e começa rejeitada. A comparação ignora caixa, acentos, espaços e pontuação, mas exige palavras inteiras | Regra 3, checada em código desde a entrada. Anos e empresa costumam estar no título da seção, não na frase citada; por isso são conferidos no texto todo. |
| Contato e CPF antes da IA | E-mail, telefone e CPF saem do texto antes de ir para a IA; e-mail e telefone viram propostas de contato com `nao_enviar_ia`, achadas em código | Regra 5 e princípio 1: o provedor não precisa ver contato para extrair carreira, e regex acha contato sem token. |
| Texto e `.md` | Com dois ou mais títulos, a pessoa marca as seções antes; cada seção vai só com o próprio texto, até o título seguinte, e blocos de código não contam como título. Limite de 60.000 caracteres por importação | É assim que a Parte A entra sem a B e a C. O limite segura o custo e o tamanho do pacote do modo manual. |
| Descrições do LinkedIn | O resumo e as descrições dos cargos vão para `fontes/` e ficam como uma etapa opcional de IA na mesma importação. O que a IA repetir do que o código já leu do PDF não vira proposta nova | Os cargos lidos em código prevalecem; a IA só acrescenta resultados e competências. |
| CV antigo | PDF ou DOCX reconhecido pelo conteúdo, não pela extensão; o código só tira o texto (com as tabelas do DOCX) e a IA extrai os fatos. `.doc` antigo e PDF escaneado são recusados com o que fazer | CV não tem layout previsível. Nos conflitos, o CV tem o menor peso: o dossiê e o LinkedIn prevalecem. |
| Descartar | Uma importação pode ser descartada sem gravar. A lista de "já rejeitados", que não voltam, só conta rejeições de importações gravadas | Descartar é "agora não", não "isto está errado". |
| Erros do Pydantic | Tradução única em `app/validacao.py`, usada pelo modo manual e pelo dossiê | Uma mensagem em português para o mesmo erro, em qualquer tela. |

## Consequências

- `app/dossie/filtros.py` concentra a regra 5; nenhum outro módulo filtra `privado` ou `nao_enviar_ia` por conta própria.
- A edição livre de texto continua no `.md`; no app, a pessoa só alterna 🔒 e "não enviar à IA" e decide propostas.
