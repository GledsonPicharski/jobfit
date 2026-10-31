---
perfil: ana-exemplo
versao: 3
atualizado: 2026-10-29
idiomas_cv: [pt, en]
---
# Dossiê de carreira — Ana Exemplo (perfil fictício)

## 0. Como a IA deve usar este arquivo

Hierarquia de fontes: dossiê confirmado > LinkedIn > CV antigo. Não inventar.
Itens marcados com 🔒 (`privado: true`) nunca vão para CV, LinkedIn ou e-mail.

## 1. Objetivo e preferências

Busco posições de liderança em dados e IA, remotas ou híbridas em São Paulo.

```fatos
- id: F-001
  tipo: preferencia
  texto: Prefere trabalho remoto ou híbrido em São Paulo.
  origem: manual 2026-10-20
  status: confirmado
  privado: false
- id: F-002
  tipo: preferencia
  texto: Faixa salarial mínima definida no contexto pessoal.
  origem: manual 2026-10-20
  status: confirmado
  privado: true   # 🔒 nunca vai para CV
  nao_enviar_ia: true
```

## 2. Resumo

Gerente de dados com dez anos de experiência em produtos de IA aplicada — da coleta à operação.

## 3. Experiências

### Empresa Exemplo

Narrativa livre escrita pela Ana: o que fez, com quem e por quê. Esta parte é só para ela;
o código lê apenas os blocos de fatos.

```fatos
- id: F-010
  tipo: cargo
  texto: Gerente de Dados e IA na Empresa Exemplo.
  empresa: Empresa Exemplo
  cargo: Gerente de Dados e IA
  periodo: {inicio: 2023-03, fim: null}
  origem: linkedin_pdf 2026-10-22
  status: confirmado
  privado: false
- id: F-014
  tipo: resultado
  texto: Lançou o Leitor Automático, que automatizou mais de 80% das leituras de documentos.
  empresa: Empresa Exemplo
  metricas: {leituras_automatizadas: ">80%"}
  origem: audio 2026-10-22
  status: confirmado
  privado: false
  # campo escrito à mão, que o app precisa preservar
  observacao_ana: confirmar o número com a equipe de operações
```

### Consultoria Fictícia

```fatos
- id: F-020
  tipo: cargo
  texto: Analista de Dados Sênior na Consultoria Fictícia.
  empresa: Consultoria Fictícia
  cargo: Analista de Dados Sênior
  periodo: {inicio: 2018-01, fim: 2023-02}
  origem: linkedin_pdf 2026-10-22
  status: confirmado
  privado: false
- id: F-021
  tipo: resultado
  texto: Reduziu de 5 para 2 dias o fechamento dos relatórios de operação.
  empresa: Consultoria Fictícia
  metricas: {dias_antes: 5, dias_depois: 2}
  origem: cv 2026-10-22
  status: confirmado
  privado: false
```

## 4. Formação

```fatos
- id: F-030
  tipo: formacao
  texto: Bacharelado em Estatística pela Universidade Exemplo.
  periodo: {inicio: 2010, fim: 2014}
  origem: linkedin_pdf 2026-10-22
  status: confirmado
  privado: false
```

## 5. Competências e ferramentas

```fatos
- id: F-040
  tipo: competencia
  texto: Gestão de produtos de IA, da descoberta à operação.
  origem: manual 2026-10-20
  status: confirmado
  privado: false
- id: F-041
  tipo: ferramenta
  texto: Python, SQL e dbt.
  origem: linkedin_pdf 2026-10-22
  status: confirmado
  privado: false
```

## 6. Idiomas

```fatos
- id: F-050
  tipo: idioma
  texto: Inglês avançado (C1).
  origem: linkedin_pdf 2026-10-22
  status: confirmado
  privado: false
```

## 7. Certificações

Nenhuma ainda.
