# JobFit

**Living career dossier.** Um app local, aberto e gratuito que mantém um dossiê de carreira vivo e o usa para avaliar vagas, gerar um CV por vaga e controlar candidaturas, sem inventar nada e sem enviar nada por você.

> Status: em construção (Fase 0: fundação). O plano completo está em [`docs/PLANO.md`](docs/PLANO.md).

## O que ele faz

- **Dossiê vivo:** importa o PDF do LinkedIn, CVs, textos e áudios, e transforma tudo em fatos com origem. Nada entra sem a sua aprovação.
- **Avaliação de vagas:** filtros em código, requisitos julgados pela IA e nota calculada em código, com forças, lacunas e o botão "eu tenho isso", que alimenta o dossiê.
- **CV por vaga:** em português e inglês, com checagem em código de que todo número, data, empresa e cargo existe no dossiê.
- **Candidaturas:** estados, histórico, follow-ups e banco de respostas de formulário.
- **Portais:** leitores de APIs públicas e feeds, buscas salvas e métricas de quais portais realmente geram entrevistas.

## Princípios

1. Código antes de token.
2. Nunca inventar: todo texto gerado aponta para fatos do dossiê.
3. Você decide e envia; o app nunca se candidata por você.
4. Seus dados ficam com você, numa pasta local.
5. Você usa a sua própria IA, sem custo obrigatório: cola o pedido no chat que já usa ou, se preferir, conecta uma chave de API.

## Instalação (Windows)

> Disponível a partir da Fase 8. Até lá, para desenvolvimento:

```powershell
# 1. Instalar o uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. Instalar as dependências
uv sync

# 3. Subir o app (abre o navegador em http://127.0.0.1:8765)
uv run jobfit
```

Na primeira execução, o app pede a pasta de dados (pode ser dentro do Google Drive para desktop) e depois o primeiro perfil. Não precisa de chave de IA: no modo manual, que é o padrão, o JobFit monta o pedido e você cola no chat que já usa (Claude, ChatGPT ou Gemini, inclusive nas versões grátis). Quem quiser automação pode trocar para o modo API (Anthropic ou OpenRouter); a chave fica no Gerenciador de Credenciais do Windows.

### Para contribuir

```powershell
uv run pre-commit install   # ruff e checagem de dados pessoais em cada commit
uv run pytest
uv run ruff check . ; uv run ruff format .
```

O pre-commit barra CPF, e-mail real, valores em R$ e celulares. Para barrar também os seus nomes e e-mails reais, liste-os num arquivo `.dados-sensiveis.txt` na raiz (um termo por linha). Esse arquivo está no `.gitignore` e nunca vai para o repositório.

## Stack

Python 3.12 · uv · FastAPI · Jinja2 + HTMX · SQLite (SQLModel) · Pydantic AI · faster-whisper · Playwright · pytest

## Inspirações

- [career-ops](https://github.com/career-ops-hq/career-ops): avaliação de vagas, checagem de fatos e leitores de portais.
- JobCopilot: buscas salvas, banco de respostas e simulador de entrevista.

## Licença

MIT
