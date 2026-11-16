"""Vagas no banco do perfil: a cópia da vaga, as avaliações e os ajustes da pessoa."""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.ia.modelos import agora_utc


class Vaga(SQLModel, table=True):
    __tablename__ = "vagas"

    id: int | None = Field(default=None, primary_key=True)
    criado_em: datetime = Field(default_factory=agora_utc, index=True)
    url: str | None = Field(default=None, index=True)  # normalizada
    fonte: str  # greenhouse | lever | gupy | pagina | texto
    titulo: str | None = None
    empresa: str | None = None
    local: str | None = None
    modalidade: str | None = None
    senioridade: str | None = None
    idioma: str = "pt"
    ingles: int | None = None
    salario: str | None = None  # JSON: moeda, minimo e maximo por mês
    texto: str  # a cópia da vaga: continua aqui se ela sair do ar
    hash_texto: str = Field(index=True)
    # nova (trazida pelo scan) | avaliada | quero_aplicar | descartada (a Fase 5 amplia)
    estado: str = "avaliada"
    faixa_esperada: str | None = None  # a faixa que a pessoa daria (concordância)
    prenota: int | None = None  # estimativa por palavras, em código (decisão 0009)
    publicada_em: datetime | None = None
    aberta: bool | None = None  # None: ainda não conferida
    checada_em: datetime | None = None
    encerrada_em: datetime | None = None


class VagaOrigem(SQLModel, table=True):
    """Onde a vaga foi vista: a mesma vaga em dois portais tem duas origens."""

    __tablename__ = "vaga_origens"

    id: int | None = Field(default=None, primary_key=True)
    vaga_id: int = Field(foreign_key="vagas.id", index=True)
    portal: str = Field(index=True)  # id do catálogo, ou "colada"
    url: str | None = None
    busca_id: int | None = Field(default=None, foreign_key="buscas.id")
    primeira_vez: datetime = Field(default_factory=agora_utc)
    ultima_vez: datetime = Field(default_factory=agora_utc)


class Busca(SQLModel, table=True):
    """Busca salva: o que o scan procura e os filtros dela (listas em JSON)."""

    __tablename__ = "buscas"

    id: int | None = Field(default=None, primary_key=True)
    nome: str
    titulos: str = "[]"  # até 5
    so_remoto: bool = True
    paises: str = "[]"  # quando não é só remoto
    senioridades: str = "[]"
    salario_minimo: int | None = None  # R$ por mês; privado, nunca vai para a IA
    empresas_excluidas: str = "[]"
    setores_excluidos: str = "[]"
    palavras_obrigatorias: str = "[]"
    palavras_proibidas: str = "[]"
    portais: str = "[]"  # vazia: todos os ativos
    ativa: bool = True
    criado_em: datetime = Field(default_factory=agora_utc)
    atualizado_em: datetime = Field(default_factory=agora_utc)


class Varredura(SQLModel, table=True):
    """Uma rodada do scan e o que cada portal trouxe."""

    __tablename__ = "varreduras"

    id: int | None = Field(default=None, primary_key=True)
    inicio: datetime = Field(default_factory=agora_utc, index=True)
    fim: datetime | None = None
    origem: str = "tela"  # tela | cli | agendada
    estado: str = "rodando"  # rodando | concluida | falhou
    portais: str = "{}"  # JSON: por portal, trazidas, novas, repetidas, filtradas e erro
    novas: int = 0
    erros: int = 0


class ConsultaPortal(SQLModel, table=True):
    """Quando cada consulta foi feita a cada portal: o intervalo mínimo (Remotive: 6 h)."""

    __tablename__ = "consultas_portal"

    chave: str = Field(primary_key=True)  # portal|termo
    feita_em: datetime = Field(default_factory=agora_utc)


class PortalPerfil(SQLModel, table=True):
    """O status da pessoa em cada portal; o catálogo é público, isto é do perfil."""

    __tablename__ = "portais_perfil"

    portal: str = Field(primary_key=True)
    desligado: bool = False  # o scan não lê este portal
    cadastro: str | None = None  # sem_conta | cadastrado
    frequencia_dias: int | None = None  # lembrete
    ultima_checagem: datetime | None = None
    observacoes: str | None = None


class Avaliacao(SQLModel, table=True):
    __tablename__ = "avaliacoes"

    id: int | None = Field(default=None, primary_key=True)
    vaga_id: int = Field(foreign_key="vagas.id", index=True)
    criado_em: datetime = Field(default_factory=agora_utc)
    versao_dossie: int | None = None
    filtros: str = "{}"  # JSON: bloqueios e alertas
    bloqueada: bool = False  # barrada pelos filtros, sem chamar a IA
    requisitos: str = "[]"  # JSON: requisitos julgados, já conferidos em código
    alertas: str = "[]"  # JSON: o que a checagem depois da IA corrigiu
    nota: int | None = None
    faixa: str | None = None
    recomenda: bool | None = None
    chamada_id: int | None = None
    versao_prompt: int | None = None


class Ajuste(SQLModel, table=True):
    """O que a pessoa disse sobre um requisito: muda a nota sem nova chamada de IA."""

    __tablename__ = "ajustes"

    id: int | None = Field(default=None, primary_key=True)
    avaliacao_id: int = Field(foreign_key="avaliacoes.id", index=True)
    requisito: int  # posição na lista de requisitos da avaliação
    acao: str  # tenho | nao_tenho | nao_se_aplica | nao_e_bem_assim
    texto: str | None = None
    fato_id: str | None = None  # o fato criado por "eu tenho isso"
    criado_em: datetime = Field(default_factory=agora_utc)
