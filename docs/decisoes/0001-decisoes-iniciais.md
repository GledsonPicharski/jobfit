# 0001 — Decisões iniciais

**Data:** 29/10/2026 · **Status:** aceita

## Contexto

Projeto pessoal e de portfólio de engenharia de IA para apoiar a busca de emprego do Gledson e da Camila, com possibilidade futura de uso por mentorados.

## Decisões

| Tema | Decisão |
| --- | --- |
| Nome | JobFit (repositório e comando `jobfit`) |
| Usuários | Gledson, depois Camila; mentorados numa fase futura |
| Execução | Local na máquina, app no navegador em `127.0.0.1` |
| Sistema operacional | Windows nos dois computadores |
| Mercado | Vagas no Brasil e internacionais remotas |
| Licença e objetivo | Aberto, gratuito, MIT, portfólio de engenharia de IA |
| Relação com o career-ops | Inspiração, sem fork |
| Stack | Python 3.12 + uv + FastAPI + Jinja2/HTMX + SQLite |
| Dossiê | `.md` com blocos de fatos em YAML, origem, itens privados e histórico; só carreira |
| LinkedIn | Sem raspagem: link ou texto colado; alertas por e-mail na v1.1 |
| Nota | IA julga requisitos; código calcula a nota; corte recomenda, não bloqueia |
| Qualidade dos portais | Medida por candidatura e entrevista; compartilhamento anônimo depois |
| Áudio | Na v1, com transcrição local |
| Notion | Fonte só para a migração inicial; depois sai |
| Do JobCopilot | Buscas salvas, cópia da vaga, banco de respostas, vagas parecidas, aprender com edições, simulador de entrevista (Fase 9) |
| Fora do escopo | Candidatura automática, envio de e-mails, compra de contatos |

## Consequências

- Toda lógica determinística em código, com testes; IA isolada em `app/ia/`.
- Atenção especial a UTF-8 e caminhos no Windows.
- Os dados pessoais ficam fora do repositório; o catálogo de portais é público.
