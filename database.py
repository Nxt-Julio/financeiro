"""Camada de dados do app.

Usa SQLAlchemy para funcionar tanto com **SQLite** (desenvolvimento local, arquivo
`finance.db`) quanto com **PostgreSQL** (produção, ex: Streamlit Community Cloud +
Neon/Supabase). A URL de conexão é resolvida nesta ordem:

1. `st.secrets["database"]["url"]`  (Streamlit Cloud → aba Secrets)
2. variável de ambiente `DATABASE_URL`
3. fallback: SQLite local (`finance.db`)

As telas do app não precisam saber qual banco está em uso — elas chamam apenas as
funções públicas deste módulo.
"""
import os
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    func,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.event import listens_for

DEFAULT_RESPONSAVEIS = ["Marido", "Esposa"]
ORIGENS = ["Dinheiro", "Cartão", "Conta"]
TIPOS = ["receita", "despesa"]

SEED_REGRAS = [
    ("Zandona", "Posto de Gasolina"),
    ("Fort", "Mercado"),
    ("Cooper", "Mercado"),
]

# Campos de uma transação que o usuário pode editar na tela de gerenciamento.
CAMPOS_EDITAVEIS = ("data", "descricao_original", "estabelecimento", "categoria", "valor", "tipo", "responsavel", "origem", "pago")


def _database_url() -> str:
    # 0) Modo de testes forçado: ignora qualquer secret/credencial e usa
    # SEMPRE o SQLite local (finance.db), mesmo que a produção esteja
    # configurada para Postgres/Supabase. Ativado com FORCE_LOCAL_DB=1.
    # Não depende de nenhuma senha/arquivo de segredo — só uma variável de
    # ambiente, então é seguro alternar sem tocar em credenciais reais.
    if os.getenv("FORCE_LOCAL_DB", "").lower() in ("1", "true", "yes"):
        return f"sqlite:///{Path(__file__).parent / 'finance.db'}"

    # 1) Streamlit secrets (produção na nuvem)
    try:
        import streamlit as st

        if "database" in st.secrets and "url" in st.secrets["database"]:
            return _normalizar_url(st.secrets["database"]["url"])
    except Exception:
        pass

    # 2) variável de ambiente
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return _normalizar_url(env_url)

    # 3) SQLite local
    return f"sqlite:///{Path(__file__).parent / 'finance.db'}"


def _normalizar_url(url: str) -> str:
    # Alguns provedores entregam "postgres://", que o SQLAlchemy não aceita.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    # Sem driver explícito, o SQLAlchemy 2.x tenta psycopg (v3), que não é uma
    # dependência deste projeto (usamos psycopg2-binary). Força o dialeto.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


engine: Engine = create_engine(_database_url(), pool_pre_ping=True, future=True)


@listens_for(engine, "connect")
def _habilitar_fk_sqlite(dbapi_conn, _rec):
    # Ativa a checagem de chave estrangeira no SQLite (no Postgres já é padrão).
    if engine.dialect.name == "sqlite":
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()


metadata = MetaData()

parcelamentos = Table(
    "parcelamentos",
    metadata,
    Column("id_origem", Integer, primary_key=True, autoincrement=True),
    Column("grupo_id", Integer, nullable=False),
    Column("descricao", Text, nullable=False),
    Column("parcela_atual", Integer, nullable=False),
    Column("total_parcelas", Integer, nullable=False),
    Column("data_vencimento", Text, nullable=False),
    Column("valor_parcela", Float, nullable=False),
)

regras_categorizacao = Table(
    "regras_categorizacao",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("termo_busca", String(255), nullable=False, unique=True),
    Column("categoria_destino", Text, nullable=False),
)

configuracoes = Table(
    "configuracoes",
    metadata,
    Column("chave", String(100), primary_key=True),
    Column("valor", Text, nullable=False),
)

transacoes = Table(
    "transacoes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("data", Text, nullable=False),
    Column("descricao_original", Text),
    Column("estabelecimento", Text),
    Column("categoria", Text),
    Column("valor", Float, nullable=False),
    Column("tipo", Text, nullable=False),
    Column("responsavel", Text, nullable=False),
    Column("origem", Text, nullable=False),
    Column("id_parcelamento", Integer, ForeignKey("parcelamentos.id_origem")),
    Column("pago", Boolean, nullable=False, default=False),
)


def _migrar_coluna_pago():
    """Migração leve: adiciona a coluna `pago` em `transacoes` se ela ainda não
    existir (para bancos criados antes desta coluna existir). Funciona em SQLite
    e PostgreSQL. `false` é aceito como default booleano nos dois."""
    colunas = [c["name"] for c in inspect(engine).get_columns("transacoes")]
    if "pago" not in colunas:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE transacoes ADD COLUMN pago BOOLEAN NOT NULL DEFAULT false"))


def init_db():
    """Cria as tabelas (se não existirem) e insere os dados semente (regras de
    categorização e nomes padrão de responsável)."""
    metadata.create_all(engine)
    _migrar_coluna_pago()

    with engine.begin() as conn:
        total_regras = conn.execute(select(func.count()).select_from(regras_categorizacao)).scalar()
        if not total_regras:
            conn.execute(
                insert(regras_categorizacao),
                [{"termo_busca": t, "categoria_destino": c} for t, c in SEED_REGRAS],
            )

        for chave, valor in (
            ("nome_responsavel_1", DEFAULT_RESPONSAVEIS[0]),
            ("nome_responsavel_2", DEFAULT_RESPONSAVEIS[1]),
        ):
            existe = conn.execute(
                select(func.count()).select_from(configuracoes).where(configuracoes.c.chave == chave)
            ).scalar()
            if not existe:
                conn.execute(insert(configuracoes).values(chave=chave, valor=valor))


# ---------------------------------------------------------------------------
# Responsáveis (nomes configuráveis)
# ---------------------------------------------------------------------------
def get_responsaveis():
    """Retorna os dois nomes de responsável configuráveis pelo usuário."""
    with engine.connect() as conn:
        linhas = conn.execute(
            select(configuracoes.c.chave, configuracoes.c.valor).where(
                configuracoes.c.chave.in_(["nome_responsavel_1", "nome_responsavel_2"])
            )
        ).all()

    valores = {chave: valor for chave, valor in linhas}
    return [
        valores.get("nome_responsavel_1", DEFAULT_RESPONSAVEIS[0]),
        valores.get("nome_responsavel_2", DEFAULT_RESPONSAVEIS[1]),
    ]


def atualizar_responsavel(chave, novo_nome):
    """Atualiza o nome configurado ('nome_responsavel_1' ou '..._2') e renomeia em
    cascata as transações que usavam o nome antigo (o responsável é texto livre)."""
    with engine.begin() as conn:
        nome_antigo = conn.execute(
            select(configuracoes.c.valor).where(configuracoes.c.chave == chave)
        ).scalar()

        if nome_antigo is None:
            conn.execute(insert(configuracoes).values(chave=chave, valor=novo_nome))
        else:
            conn.execute(
                update(configuracoes).where(configuracoes.c.chave == chave).values(valor=novo_nome)
            )

        if nome_antigo and nome_antigo != novo_nome:
            conn.execute(
                update(transacoes).where(transacoes.c.responsavel == nome_antigo).values(responsavel=novo_nome)
            )


# ---------------------------------------------------------------------------
# Transações
# ---------------------------------------------------------------------------
def inserir_transacao(data, descricao_original, estabelecimento, categoria, valor, tipo, responsavel, origem, id_parcelamento=None):
    """Insere uma única transação (abre e fecha sua própria transação de banco).
    Retorna o id gerado."""
    with engine.begin() as conn:
        result = conn.execute(
            insert(transacoes).values(
                data=data,
                descricao_original=descricao_original,
                estabelecimento=estabelecimento,
                categoria=categoria,
                valor=valor,
                tipo=tipo,
                responsavel=responsavel,
                origem=origem,
                id_parcelamento=id_parcelamento,
            )
        )
    return result.inserted_primary_key[0]


def inserir_transacoes_lote(linhas):
    """Insere várias transações em uma única transação de banco.

    `linhas` é uma lista de dicts com as chaves: data, descricao_original,
    estabelecimento, categoria, valor, tipo, responsavel, origem
    (id_parcelamento é opcional e assume None)."""
    if not linhas:
        return 0
    registros = []
    for linha in linhas:
        registro = {
            "data": linha["data"],
            "descricao_original": linha.get("descricao_original"),
            "estabelecimento": linha.get("estabelecimento"),
            "categoria": linha.get("categoria"),
            "valor": linha["valor"],
            "tipo": linha["tipo"],
            "responsavel": linha["responsavel"],
            "origem": linha["origem"],
            "id_parcelamento": linha.get("id_parcelamento"),
        }
        registros.append(registro)
    with engine.begin() as conn:
        conn.execute(insert(transacoes), registros)
    return len(registros)


def atualizar_transacao(id_transacao, campos):
    """Atualiza os campos informados de uma transação (allowlist CAMPOS_EDITAVEIS)."""
    permitidos = {k: v for k, v in campos.items() if k in CAMPOS_EDITAVEIS}
    if not permitidos:
        return
    with engine.begin() as conn:
        conn.execute(update(transacoes).where(transacoes.c.id == id_transacao).values(**permitidos))


def excluir_transacao(id_transacao):
    """Remove uma transação pelo id."""
    with engine.begin() as conn:
        conn.execute(delete(transacoes).where(transacoes.c.id == id_transacao))


def fetch_transacoes():
    with engine.connect() as conn:
        rows = conn.execute(select(transacoes).order_by(transacoes.c.data)).mappings().all()
    return [dict(r) for r in rows]


def fetch_categorias():
    """Categorias já usadas em transações, ordenadas (para sugerir em selects)."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(transacoes.c.categoria)
            .where(transacoes.c.categoria.isnot(None), transacoes.c.categoria != "")
            .distinct()
            .order_by(transacoes.c.categoria)
        ).all()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Parcelamentos
# ---------------------------------------------------------------------------
def criar_parcelamento(descricao, categoria, responsavel, origem, parcelas):
    """Cria um parcelamento completo em uma única transação de banco:
    para cada parcela, insere uma linha em `parcelamentos` e a transação
    (despesa) correspondente vinculada a ela.

    `parcelas` é a lista retornada por utils.installments.gerar_parcelas, com
    dicts contendo: parcela_atual, total_parcelas, data_vencimento (date),
    valor_parcela.
    """
    with engine.begin() as conn:
        proximo = conn.execute(select(func.coalesce(func.max(parcelamentos.c.grupo_id), 0))).scalar()
        grupo_id = (proximo or 0) + 1

        for parcela in parcelas:
            data_iso = parcela["data_vencimento"].isoformat()
            result = conn.execute(
                insert(parcelamentos).values(
                    grupo_id=grupo_id,
                    descricao=descricao,
                    parcela_atual=parcela["parcela_atual"],
                    total_parcelas=parcela["total_parcelas"],
                    data_vencimento=data_iso,
                    valor_parcela=parcela["valor_parcela"],
                )
            )
            id_origem = result.inserted_primary_key[0]

            conn.execute(
                insert(transacoes).values(
                    data=data_iso,
                    descricao_original=f"{descricao} ({parcela['parcela_atual']}/{parcela['total_parcelas']})",
                    estabelecimento=descricao,
                    categoria=categoria,
                    valor=parcela["valor_parcela"],
                    tipo="despesa",
                    responsavel=responsavel,
                    origem=origem,
                    id_parcelamento=id_origem,
                )
            )


def fetch_parcelamentos():
    """Retorna as parcelas com o status `pago` já resolvido (lido da transação
    vinculada), para que dashboards como a Projeção Futura possam excluir
    parcelas já quitadas do que ainda está "por vir"."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                parcelamentos,
                func.coalesce(transacoes.c.pago, False).label("pago"),
            )
            .select_from(
                parcelamentos.outerjoin(transacoes, transacoes.c.id_parcelamento == parcelamentos.c.id_origem)
            )
            .order_by(parcelamentos.c.grupo_id, parcelamentos.c.parcela_atual)
        ).mappings().all()
    return [dict(r) for r in rows]


def fetch_parcelas_pendentes():
    """Parcelas ainda não pagas, para vincular (ex: a um holerite que já desconta
    aquela parcela) e marcá-las como pagas de uma vez. Retorna lista de dicts:
    transacao_id (o id em `transacoes`, usado com atualizar_transacao), descricao,
    parcela_atual, total_parcelas, data_vencimento, valor_parcela — por vencimento."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                transacoes.c.id.label("transacao_id"),
                parcelamentos.c.descricao,
                parcelamentos.c.parcela_atual,
                parcelamentos.c.total_parcelas,
                parcelamentos.c.data_vencimento,
                parcelamentos.c.valor_parcela,
            )
            .select_from(
                parcelamentos.join(transacoes, transacoes.c.id_parcelamento == parcelamentos.c.id_origem)
            )
            .where(func.coalesce(transacoes.c.pago, False).is_(False))
            .order_by(parcelamentos.c.data_vencimento)
        ).mappings().all()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Regras de categorização
# ---------------------------------------------------------------------------
def fetch_regras():
    """Retorna as regras como lista de tuplas (termo_busca, categoria_destino)."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(regras_categorizacao.c.termo_busca, regras_categorizacao.c.categoria_destino)
        ).all()
    return [(termo, categoria) for termo, categoria in rows]
