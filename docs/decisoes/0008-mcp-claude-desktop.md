# 0008 — MCP para o Claude Desktop: um caminho de resposta do modo manual

Data: 2026-11-06 · Status: aceita

## Contexto

No modo manual (decisão 0003), cada avaliação de vaga e cada CV pedem um copiar e colar entre o JobFit e o chat. Quem tem o Claude pode usar a assinatura pelo Claude Desktop, que fala MCP: o Claude chama ferramentas do JobFit e faz a parte de IA, sem copiar e colar e sem custo de API. A saída precisa continuar validada pelo JobFit (regra 2) e a nota calculada em código (regra 10).

## Decisões

| Tema | Decisão | Por quê |
| --- | --- | --- |
| O que é o MCP | Mais um caminho de resposta para os pedidos do modo manual, não um provedor novo. `executar()` não muda. | A chave do cache inclui `provedor:modelo`. Com um provedor novo, a resposta dada pelo Claude Desktop não serviria à tela no modo manual. Assim, o pedido criado na tela pode ser respondido pelo Claude Desktop, e o contrário. |
| Fluxo | A ferramenta roda o mesmo serviço da tela. Com `AguardandoResposta`, devolve o pacote do pedido; o Claude responde por `responder_pedido`; o JobFit valida com o mesmo `responder_pedido()` do modo manual e grava no cache; a ferramenta chamada de novo acha o resultado. | É o padrão GET + cache da tela. O servidor não guarda estado. |
| Ferramentas | `avaliar_vaga`, `gerar_cv`, `listar_vagas`, `pedidos_pendentes`, `ver_pedido`, `responder_pedido`. | Cobrem a avaliação e o CV, e qualquer pedido criado na tela (como a extração de fatos). |
| O que fica de fora | Nenhuma ferramenta grava no dossiê, envia algo ou gera o PDF. | Regra 4: "Eu tenho isso", aplicar importação e confirmar tradução continuam na tela. O PDF sai depois da revisão no app. |
| Registro | `pedidos_ia.respondido_por` (`chat` ou `claude_desktop`). | Mostrar em "Custos e chamadas" por onde as respostas vêm. |
| Como o Claude Desktop inicia | `<.venv>\Scripts\python.exe -m app.mcp --perfil <slug>`, em stdio. | Sem `uv run` nem `jobfit.exe`, que travam a sincronização do uv com o app aberto. O stdout é só do protocolo. |
| Instalação | Um botão em Configurar IA (ou `jobfit mcp instalar`) grava só a entrada `mcpServers.jobfit` no `claude_desktop_config.json`, com cópia `.bak` antes. Na versão da Microsoft Store, o arquivo fica em `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\`. | Um clique, sem editar JSON à mão, preservando outros servidores da pessoa. |
| No modo API | As ferramentas funcionam, mas chamam a API, com o custo dela, e a resposta da ferramenta avisa isso. | O modo é escolha do perfil; o MCP não o troca por baixo. |

## Alternativas descartadas

- **Provedor "Claude Desktop" em `executar()`:** separa o cache da tela e do Claude Desktop e exige trocar o modo do perfil para usar.
- **Amostragem do MCP (o servidor pede ao cliente que rode o modelo):** o Claude Desktop não oferece. Com ela, o JobFit chamaria a IA sem a pessoa ver o pedido.
- **Extensão `.mcpb` do Claude Desktop:** exigiria empacotar o Python e as dependências do JobFit. O app já está instalado; basta apontar para ele.
- **Guardar no servidor o que fazer depois da resposta:** o estado se perde quando o Claude Desktop reinicia o servidor. Chamar a ferramenta de novo e achar no cache não depende disso.

## Consequências

- O risco de injeção por texto de vaga é o mesmo do modo manual. O Claude Desktop pode ter outras ferramentas ativas (web, arquivos). O texto vai delimitado, as instruções do servidor mandam ignorar ordens dentro dele, a saída é validada e a nota sai do código.
- O pacote já sai sem os fatos `nao_enviar_ia` (regra 5) e sem contato; o que o Claude recebe é o mesmo que a pessoa colaria no chat.
- O servidor MCP e o app web abrem o mesmo SQLite do perfil ao mesmo tempo, em WAL.
