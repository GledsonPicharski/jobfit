# 0002 — Fundação (Fase 0)

**Data:** 29/10/2026 · **Status:** aceita

## Contexto

Ao planejar a Fase 0, alguns pontos do `PLANO.md` estavam em aberto ou se contradiziam, e a implementação revelou detalhes das bibliotecas que mudam o desenho.

## Decisões

| Tema | Decisão | Por quê |
| --- | --- | --- |
| Provedores na Fase 0 | Anthropic e OpenRouter | O checklist pede trocar de provedor; o OpenRouter também dá acesso a OpenAI e Gemini. OpenAI, Gemini e Ollama diretos entram quando alguém precisar. |
| Servidor local | Middleware aceita só `Host` 127.0.0.1/localhost e exige `Origin`/`Referer` do próprio app em POST | Escutar em 127.0.0.1 não impede DNS rebinding nem CSRF vindo de outro site aberto no navegador. Também envia `X-Frame-Options: DENY`. |
| Pre-commit | Regras genéricas no repositório (CPF com dígito verificador, e-mail fora da lista permitida, R$ com valor, celular); termos reais em `.dados-sensiveis.txt`, fora do git | Os nomes reais não podem estar no repositório público. A saída mascara o achado, porque o log da CI é público. |
| Configuração global | `%LOCALAPPDATA%\JobFit\config.json` e `bancos\<slug>.db` | O banco fica fora do Google Drive; `JOBFIT_HOME` sobrescreve em testes. |
| Configuração do perfil | `perfis/<slug>/perfil.json` na pasta de dados, sem segredos | Sobrevive à troca de máquina junto com o dossiê. A lista de perfis vem da varredura das pastas, sem banco global. |
| Cache de IA | Tabela `cache_ia` no banco do perfil | Isolado por perfil e incluído no backup. |
| Custo | Inteiro em micro-dólares; `NULL` quando o preço é desconhecido | Sem erro de arredondamento de float, e "desconhecido" nunca vira US$ 0. |
| Preço | `usage.cost` do Pydantic AI 2.x, que já usa o `genai-prices` | Sem dependência direta nem tabela própria de preços. |
| Versão do prompt | Declarada na `Tarefa`, não deduzida do arquivo mais novo | Mudar o prompt exige um passo explícito, que invalida o cache e pede evals. |
| Regras do CLAUDE.md como lint | ruff `TID251` proíbe `pydantic_ai`, `anthropic`, `openai` e `keyring` fora de `app/ia/`; `PLW1514` exige `encoding` em `open()` | A regra 2 e o UTF-8 explícito deixam de depender de disciplina. |
| Migrações | Alembic programático ao abrir cada banco, `render_as_batch=True` | Com um banco por perfil, ninguém deve rodar `alembic upgrade` à mão. |
| Datas | Sempre com fuso; o SQLModel grava e devolve em UTC (`UTCDateTime`) | O SQLModel atual recusa datas sem fuso; o "gasto do dia" usa o dia do relógio local. |
| Importação dos SDKs | `anthropic`/`openai` carregados só na primeira chamada de IA | Importá-los levava ~9 s no Windows; o app passou a abrir em ~4 s. |
| Front | HTMX 2.0.11 e Pico 2.1.1 servidos de `app/web/static/` | Funciona sem internet e sem CDN. |
| CLI | Só `jobfit` (sobe o app); os outros subcomandos nascem nas fases deles | Sem código morto. Se a porta já está em uso, só abre o navegador. |

## Consequências

- O módulo de `executar()` chama `app/ia/execucao.py`: `app.ia.executar` é a função exportada, e o mesmo nome para o módulo atrapalharia `monkeypatch` e imports.
- O filtro de `privado` e `nao_enviar_ia` entra na Fase 1, junto com os fatos.
- `prompts/` fica na raiz do repositório e é lido a partir do checkout; empacotar o app como wheel exigirá movê-lo para dentro do pacote.
