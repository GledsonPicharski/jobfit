# 0003 — Modos de IA, com o modo manual como padrão

**Data:** 30/10/2026 · **Status:** aceita

## Contexto

O plano partia de uma chave de API por perfil. Na prática, a API é cobrada à parte da assinatura do Claude, e o plano grátis do OpenRouter estoura o limite de uso logo nos primeiros testes. Exigir conta, créditos e chave de API quebra a promessa de um app livre e gratuito para a Camila e para os mentorados.

## Decisão

A camada de IA passa a ter modos. Todos usam as mesmas tarefas, os mesmos prompts versionados, a mesma validação de saída, o mesmo cache e o mesmo registro:

| Modo | Para quem | Custo | Quando |
| --- | --- | --- | --- |
| Sem IA | todos: tudo que é determinístico funciona sem IA | zero | sempre |
| **Manual (copiar e colar)** | **padrão** de perfil novo; qualquer chat (Claude, ChatGPT, Gemini, inclusive grátis) | zero | Fase 0 |
| MCP para o Claude Desktop | quem tem Claude e quer menos cliques | zero além do plano | Fase 4b |
| API (Anthropic, OpenRouter) | automação (busca agendada) e evals | por uso | já existe |
| Ollama | privacidade total, máquina com memória sobrando | zero | v1.1 |

**Como o modo manual funciona.** `executar()` monta um pacote em código com as instruções, os dados delimitados e o formato de resposta (JSON Schema). Em seguida grava um pedido pendente e avisa a tela. A pessoa cola o pacote no chat dela e cola a resposta de volta. O JobFit confere o id do pedido, valida a resposta contra o modelo Pydantic da tarefa e grava no cache. Quando a funcionalidade roda de novo, encontra a resposta no cache, então nenhuma funcionalidade precisa saber qual modo está ativo.

## Alternativas descartadas

- **Usar o login da assinatura do Claude dentro do app:** os termos da Anthropic restringem credenciais da assinatura em apps de terceiros.
- **Salvar no Drive e pedir ao Claude para ler:** acrescenta um intermediário e não elimina o passo de trazer a resposta de volta.
- **Ollama como padrão:** instalação pesada e lento na CPU (os notebooks atuais não têm GPU que o Ollama use no Windows). Fica como opção.

## Consequências

- As regras continuam valendo em todos os modos. Saída validada (regra 2), nota calculada em código (regra 10), fatos `nao_enviar_ia` filtrados antes de montar o pacote (regra 5) e texto de vaga delimitado como dado não confiável (regra 8).
- No modo manual, a IA do chat pode ter ferramentas (busca na web). Isso aumenta o risco de injeção por texto de vaga, mas o impacto continua limitado, porque a saída é validada e a nota sai do código.
- A busca agendada só avalia vagas sozinha no modo API; nos outros, as vagas ficam esperando a pessoa.
- `jobfit eval` exige o modo API ou o Ollama. É custo de quem desenvolve, não de quem usa.
- O MCP sai do "fora da v1" e vira a Fase 4b, porque precisa das ferramentas de avaliar vaga e gerar CV.
