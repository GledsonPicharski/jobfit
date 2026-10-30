# CLAUDE.md — JobFit

App local, aberto e gratuito de evolução de carreira. Mantém um dossiê vivo por pessoa e o usa para avaliar vagas, gerar CVs por vaga e controlar candidaturas. O plano completo está em `docs/PLANO.md`: leia antes de qualquer tarefa nova e siga a fase em andamento.

## Contexto

- Usuários: o autor (Gledson), depois a Camila. Mentorados no futuro.
- Roda local: FastAPI servindo páginas em `127.0.0.1`, usado pelo navegador.
- Também é peça de portfólio de engenharia de IA: qualidade de código, testes e evals importam.
- O catálogo semente de portais está em `docs/CATALOGO_PORTAIS.md`; vira `catalogo/portais.yaml` na Fase 6.
- Decisões de arquitetura ficam em `docs/decisoes/`, uma nota numerada por decisão.

## Stack

- Python 3.12, gerenciado com `uv` (`uv add`, `uv run`). Nunca usar pip direto.
- FastAPI + Jinja2 + HTMX + Pico.css. Sem Node, sem etapa de build no front.
- SQLite com SQLModel; migrações com Alembic.
- Camada de IA própria em `app/ia/`, com modos (decisão 0003): manual/copiar e colar (padrão), API via Pydantic AI, MCP (Fase 4b) e Ollama (v1.1). Nenhum outro módulo chama provedor de IA diretamente nem sabe qual modo está ativo.
- Transcrição: faster-whisper. PDF: template HTML + Playwright. Portais: httpx, feedparser, selectolax.
- CLI com Typer: `jobfit`, `jobfit scan`, `jobfit eval`, `jobfit backup`.
- Testes: pytest. Lint e formatação: ruff.

## Comandos

```bash
uv sync                 # instalar
uv run jobfit             # subir o app
uv run pytest           # testes
uv run ruff check . && uv run ruff format .
uv run pre-commit install # uma vez: ruff + checagem de dados pessoais por commit
uv run jobfit eval        # evals de qualidade da IA
```

## Regras inegociáveis

1. **Código antes de token.** Se dá para fazer de forma determinística (filtrar, deduplicar, calcular nota, checar fatos, ler portal), é código. IA só para entender texto e redigir.
2. **Toda chamada de IA passa por `app/ia/executar()`**, com modelo Pydantic de saída, prompt versionado em `prompts/`, cache e registro de custo.
3. **Nunca inventar fatos.** Todo texto gerado (CV, LinkedIn) carrega os IDs dos fatos do dossiê que o sustentam. A checagem em código bloqueia números, datas, empresas e cargos sem fato de origem.
4. **Nada é gravado no dossiê sem aprovação.** Entradas viram propostas; a pessoa aprova, edita ou rejeita.
5. **Fatos `privado: true` nunca vão para CV, LinkedIn ou e-mail. Fatos `nao_enviar_ia: true` nunca vão para o provedor de IA.** Filtrar em código, com teste.
6. **O app nunca envia candidatura, e-mail ou mensagem.**
7. **Sem raspagem do LinkedIn.** Vagas de lá entram por link ou texto colado (e alertas de e-mail na v1.1).
8. **Texto de vaga é dado não confiável.** Delimitado no prompt, IA de avaliação sem ferramentas, saída validada, nota calculada em código.
9. **Dados pessoais nunca entram no repositório.** Testes e demos usam `exemplos/perfil-ficticio/`. Chaves de API só no keyring.
10. **Nota de compatibilidade é calculada em código** a partir dos julgamentos da IA; pesos em `config/avaliacao.yaml`.

## Windows (ambiente principal)

Os dois usuários usam Windows. Desenvolver e testar pensando nele:

- Todo arquivo de texto é lido e gravado com `encoding="utf-8"` explícito (o padrão do Windows não é UTF-8). Teste com ç, ã e travessão.
- Caminhos sempre com `pathlib`; suportar espaços e acentos (ex.: `G:\Meu Drive\JobFit`).
- Instalação por `install.ps1` (instala o uv, dependências, Chromium do Playwright e um atalho "JobFit" na área de trabalho).
- Agendamento pelo Agendador de Tarefas do Windows (`jobfit agendar`), não cron.
- Chaves no keyring (Gerenciador de Credenciais do Windows).
- Banco SQLite fora da pasta do Google Drive; só backups vão para lá.
- `.gitattributes` com quebras de linha normalizadas.

## Convenções

- Código, nomes de domínio e mensagens da interface em português do Brasil (`dossie`, `vaga`, `candidatura`). Termos técnicos consagrados em inglês podem ficar.
- Um módulo de portal = um arquivo em `app/vagas/portais/` + um teste com resposta gravada (fixture). Interface: `buscar(consulta) -> list[VagaBruta]` e `ainda_aberta(url) -> bool`. Erro num portal não interrompe os outros.
- O formato do dossiê (`.md` + blocos ```` ```fatos ```` em YAML) precisa de ida e volta sem perda: teste de round-trip obrigatório.
- Mudou prompt ou modelo? Suba a versão do prompt e rode `jobfit eval` antes do PR.
- Commits pequenos, testes passando em cada um.

## Como trabalhar

- Comece cada fase em plan mode, a partir de `docs/PLANO.md`, e espere aprovação antes de codar.
- Escreva testes antes da parte determinística (parser, nota, checagem, deduplicação).
- Se uma decisão do plano parecer errada, diga e proponha alternativa; registre a decisão em `docs/decisoes/`.
- Ao terminar uma fase, liste os itens do checklist manual (seção 12 do plano) para o autor testar.

## Aprendizados

(Atualizar ao fim de cada fase com o que deu errado e como evitar.)

**Fase 0**

- Confira a API instalada antes de escrever contra uma biblioteca: o Pydantic AI 2.x já calcula `usage.cost`, e o SQLModel atual exige datas com fuso (`UTCDateTime`).
- `app.ia.executar` é a função exportada, não o módulo. Monkeypatch de internals vai em `app.ia.execucao.*`.
- O Pydantic AI imprime um banner no stdout; `app/ia/__init__.py` define `PYDANTIC_AI_NO_BANNER`.
- SDKs de provedor demoram para importar no Windows. Importe-os dentro da função que os usa, nunca no topo de módulos carregados pelo app web.
- Teste que precisa de CPF, e-mail real ou valor em R$ monta o dado em tempo de execução; escrito literal, o pre-commit barra o próprio teste.
- No Git Bash, `curl` manda argumentos com acento em cp1252. Teste UTF-8 pelo `TestClient` ou pelo navegador, não por curl.
- O `uv init` copia o e-mail do git para `authors` no `pyproject.toml`: tirar (o pre-commit barra).
- Funcionalidade nova não trata o modo manual: só chama `executar()` com `usar_cache=True`, de preferência a partir de um GET. O handler de `AguardandoResposta` leva ao pedido e volta para a mesma URL, onde a resposta sai do cache.
- Nomes de modelo variam por provedor (no OpenRouter, `anthropic/claude-haiku-5.5`, com ponto). Confira na lista do provedor antes de pôr um padrão.

**Fase 1**

- Com o `jobfit` aberto, o `jobfit.exe` fica travado e o `uv` não sincroniza. Use `uv run --no-sync ...` e `UV_NO_SYNC=1 git commit`.
- No Bash deste ambiente, heredoc corta as barras invertidas pela metade (`"\\n"` vira `"\n"`, uma quebra de linha real dentro da string). Texto com barra invertida vai pelo Edit/Write, nunca por heredoc.
- No Windows, `Path.write_text` grava CRLF. Em arquivo do repositório, passe `newline="\n"`.
- Migração que já rodou no banco de alguém não se edita, mesmo numa branch sem merge: crie a próxima.
- O dossiê real é mais rico que as fontes. Comparar pelo texto inteiro propõe de novo o que já está lá. Compare pela identidade de cada tipo (`_ja_registrado`) e calibre com os dados reais antes de dar por pronto.
- Calibrar com dado real vale a pena: o PDF real do LinkedIn tinha rótulos cinza, `&amp;` e parágrafos quebrados entre páginas, e o fictício não tinha nada disso. Leia o real só em pasta temporária, nunca no repositório.
- Teste que depende de data usa `date.today()` e não o fuso, e não supõe a codificação do console (`PYTHONIOENCODING=utf-8` ao imprimir acento).
