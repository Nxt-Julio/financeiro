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
import datetime
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
    UniqueConstraint,
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

from utils.allocation import TOLERANCIA

DEFAULT_RESPONSAVEIS = ["Marido", "Esposa"]
ORIGENS = ["Dinheiro", "Cartão", "Conta"]
TIPOS = ["receita", "despesa"]

SEED_REGRAS = [
    ("Zandona", "Posto de Gasolina"),
    ("Fort", "Mercado"),
    ("Cooper", "Mercado"),
]

# Campos de uma transação que o usuário pode editar na tela de gerenciamento.
CAMPOS_EDITAVEIS = ("data", "descricao_original", "estabelecimento", "categoria", "valor", "tipo", "responsavel", "origem", "pago", "cartao_id")


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

# Cartões de crédito cadastrados (limite e ciclo da fatura). Os cálculos de
# fatura/limite ficam em utils/cards.py.
cartoes = Table(
    "cartoes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nome", String(100), nullable=False, unique=True),
    Column("limite", Float, nullable=False, default=0.0),
    Column("dia_fechamento", Integer, nullable=False),
    Column("dia_vencimento", Integer, nullable=False),
    Column("cor", String(20), nullable=False, default="#6366F1"),
)

# Teto mensal de gasto por categoria (Orçamento & Metas).
orcamentos = Table(
    "orcamentos",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("categoria", String(255), nullable=False, unique=True),
    Column("teto", Float, nullable=False),
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
    # Cartão da compra (opcional; só faz sentido com origem "Cartão").
    Column("cartao_id", Integer, ForeignKey("cartoes.id", ondelete="SET NULL")),
)

# Alocação financeira (vínculo De/Para): destina parte de uma receita para cobrir
# uma despesa. Relação N:N entre transações — uma receita pode ser dividida entre
# várias despesas e uma despesa pode ser coberta por várias receitas. Há no
# máximo um vínculo por par (receita, despesa); "vincular de novo" o mesmo par
# substitui o valor (ver salvar_alocacao).
alocacoes = Table(
    "alocacoes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("receita_id", Integer, ForeignKey("transacoes.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("despesa_id", Integer, ForeignKey("transacoes.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("valor", Float, nullable=False),
    Column("criado_em", Text, nullable=False),
    UniqueConstraint("receita_id", "despesa_id", name="uq_alocacao_par"),
)


class AlocacaoInvalida(ValueError):
    """Vínculo recusado por regra de negócio (mensagem pronta para exibir)."""


def _migrar_coluna_pago():
    """Migração leve: adiciona a coluna `pago` em `transacoes` se ela ainda não
    existir (para bancos criados antes desta coluna existir). Funciona em SQLite
    e PostgreSQL. `false` é aceito como default booleano nos dois."""
    colunas = [c["name"] for c in inspect(engine).get_columns("transacoes")]
    if "pago" not in colunas:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE transacoes ADD COLUMN pago BOOLEAN NOT NULL DEFAULT false"))


def _migrar_coluna_cartao():
    """Migração leve: adiciona `transacoes.cartao_id` em bancos criados antes da
    tela Contas & Cartões. Coluna nula por padrão — nenhum dado existente muda."""
    colunas = [c["name"] for c in inspect(engine).get_columns("transacoes")]
    if "cartao_id" not in colunas:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE transacoes ADD COLUMN cartao_id INTEGER REFERENCES cartoes(id) ON DELETE SET NULL"
            ))


def init_db():
    """Cria as tabelas (se não existirem) e insere os dados semente (regras de
    categorização e nomes padrão de responsável)."""
    metadata.create_all(engine)
    _migrar_coluna_pago()
    _migrar_coluna_cartao()

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
def inserir_transacao(data, descricao_original, estabelecimento, categoria, valor, tipo, responsavel, origem, id_parcelamento=None, cartao_id=None):
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
                cartao_id=cartao_id,
            )
        )
    return result.inserted_primary_key[0]


def inserir_transacoes_lote(linhas):
    """Insere várias transações em uma única transação de banco.

    `linhas` é uma lista de dicts com as chaves: data, descricao_original,
    estabelecimento, categoria, valor, tipo, responsavel, origem
    (id_parcelamento e cartao_id são opcionais e assumem None)."""
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
            "cartao_id": linha.get("cartao_id"),
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
        # Se o tipo mudou, os vínculos do papel antigo deixam de fazer sentido
        # (ex: uma "receita" que virou "despesa" não pode mais cobrir nada).
        if permitidos.get("tipo") == "despesa":
            conn.execute(delete(alocacoes).where(alocacoes.c.receita_id == id_transacao))
        elif permitidos.get("tipo") == "receita":
            conn.execute(delete(alocacoes).where(alocacoes.c.despesa_id == id_transacao))
        conn.execute(update(transacoes).where(transacoes.c.id == id_transacao).values(**permitidos))


def excluir_transacao(id_transacao):
    """Remove uma transação pelo id (e os vínculos de alocação dela)."""
    with engine.begin() as conn:
        conn.execute(
            delete(alocacoes).where(
                (alocacoes.c.receita_id == id_transacao) | (alocacoes.c.despesa_id == id_transacao)
            )
        )
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
def criar_parcelamento(descricao, categoria, responsavel, origem, parcelas, cartao_id=None):
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
                    cartao_id=cartao_id,
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


# ---------------------------------------------------------------------------
# Alocações (vínculo De/Para receita -> despesa)
# ---------------------------------------------------------------------------
def fetch_alocacoes():
    """Todos os vínculos: id, receita_id, despesa_id, valor, criado_em."""
    with engine.connect() as conn:
        rows = conn.execute(select(alocacoes).order_by(alocacoes.c.id)).mappings().all()
    return [dict(r) for r in rows]


def salvar_alocacao(receita_id, despesa_id, valor):
    """Cria o vínculo receita -> despesa ou, se o par já estiver vinculado,
    substitui o valor alocado. Valida tudo dentro de uma única transação de banco:

    - a receita é do tipo "receita" e a despesa é do tipo "despesa";
    - o valor é positivo;
    - não ultrapassa o saldo livre da receita nem o que falta cobrir da despesa
      (desconsiderando o valor atual do próprio par, já que ele será substituído).

    Levanta AlocacaoInvalida com uma mensagem amigável se alguma regra falhar.
    """
    from utils.ui import _fmt_brl

    valor = round(float(valor), 2)
    if valor <= 0:
        raise AlocacaoInvalida("O valor alocado deve ser maior que zero.")

    with engine.begin() as conn:
        # FOR UPDATE trava as duas transações no Postgres enquanto validamos,
        # evitando que dois vínculos simultâneos estourem o saldo (no SQLite a
        # cláusula é ignorada — lá a escrita já é serializada).
        linhas = conn.execute(
            select(transacoes.c.id, transacoes.c.tipo, transacoes.c.valor, transacoes.c.descricao_original)
            .where(transacoes.c.id.in_([receita_id, despesa_id]))
            .with_for_update()
        ).mappings().all()
        por_id = {linha["id"]: linha for linha in linhas}
        receita, despesa = por_id.get(receita_id), por_id.get(despesa_id)
        if receita is None or receita["tipo"] != "receita":
            raise AlocacaoInvalida("A origem do vínculo precisa ser uma receita existente.")
        if despesa is None or despesa["tipo"] != "despesa":
            raise AlocacaoInvalida("O destino do vínculo precisa ser uma despesa existente.")

        mesmo_par = (alocacoes.c.receita_id == receita_id) & (alocacoes.c.despesa_id == despesa_id)

        def _ja_alocado(coluna, id_transacao):
            return conn.execute(
                select(func.coalesce(func.sum(alocacoes.c.valor), 0.0))
                .where(coluna == id_transacao, ~mesmo_par)
            ).scalar()

        livre = round(receita["valor"] - _ja_alocado(alocacoes.c.receita_id, receita_id), 2)
        restante = round(despesa["valor"] - _ja_alocado(alocacoes.c.despesa_id, despesa_id), 2)
        if valor > livre + TOLERANCIA:
            raise AlocacaoInvalida(
                f"Valor maior que o saldo livre da receita \"{receita['descricao_original']}\" "
                f"({_fmt_brl(max(livre, 0))})."
            )
        if valor > restante + TOLERANCIA:
            raise AlocacaoInvalida(
                f"Valor maior que o que falta cobrir da despesa \"{despesa['descricao_original']}\" "
                f"({_fmt_brl(max(restante, 0))})."
            )

        existente = conn.execute(select(alocacoes.c.id).where(mesmo_par)).scalar()
        if existente is None:
            conn.execute(
                insert(alocacoes).values(
                    receita_id=receita_id,
                    despesa_id=despesa_id,
                    valor=valor,
                    criado_em=datetime.datetime.now().isoformat(timespec="seconds"),
                )
            )
        else:
            conn.execute(update(alocacoes).where(alocacoes.c.id == existente).values(valor=valor))


def remover_alocacao(id_alocacao):
    """Desfaz um vínculo (as transações originais não são tocadas)."""
    with engine.begin() as conn:
        conn.execute(delete(alocacoes).where(alocacoes.c.id == id_alocacao))


# ---------------------------------------------------------------------------
# Cartões de crédito
# ---------------------------------------------------------------------------
def fetch_cartoes():
    """Cartões cadastrados: id, nome, limite, dia_fechamento, dia_vencimento, cor."""
    with engine.connect() as conn:
        rows = conn.execute(select(cartoes).order_by(cartoes.c.nome)).mappings().all()
    return [dict(r) for r in rows]


def salvar_cartao(nome, limite, dia_fechamento, dia_vencimento, cor, id_cartao=None):
    """Cria (sem id) ou atualiza (com id) um cartão."""
    valores = dict(
        nome=nome.strip(), limite=float(limite), dia_fechamento=int(dia_fechamento),
        dia_vencimento=int(dia_vencimento), cor=cor,
    )
    with engine.begin() as conn:
        if id_cartao is None:
            conn.execute(insert(cartoes).values(**valores))
        else:
            conn.execute(update(cartoes).where(cartoes.c.id == id_cartao).values(**valores))


def excluir_cartao(id_cartao):
    """Remove o cartão; os lançamentos dele continuam, só perdem o vínculo."""
    with engine.begin() as conn:
        conn.execute(update(transacoes).where(transacoes.c.cartao_id == id_cartao).values(cartao_id=None))
        conn.execute(delete(cartoes).where(cartoes.c.id == id_cartao))


def atribuir_cartao_sem_vinculo(id_cartao):
    """Vincula ao cartão todas as despesas de origem "Cartão" que ainda não têm
    cartão (lançamentos anteriores a esta tela). Retorna quantas foram vinculadas."""
    with engine.begin() as conn:
        result = conn.execute(
            update(transacoes)
            .where(
                transacoes.c.origem == "Cartão",
                transacoes.c.tipo == "despesa",
                transacoes.c.cartao_id.is_(None),
            )
            .values(cartao_id=id_cartao)
        )
    return result.rowcount


# ---------------------------------------------------------------------------
# Orçamento (teto mensal por categoria)
# ---------------------------------------------------------------------------
def fetch_orcamentos():
    """Tetos cadastrados: id, categoria, teto."""
    with engine.connect() as conn:
        rows = conn.execute(select(orcamentos).order_by(orcamentos.c.categoria)).mappings().all()
    return [dict(r) for r in rows]


def salvar_orcamento(categoria, teto):
    """Define o teto mensal da categoria (cria ou substitui)."""
    categoria = categoria.strip()
    with engine.begin() as conn:
        existente = conn.execute(select(orcamentos.c.id).where(orcamentos.c.categoria == categoria)).scalar()
        if existente is None:
            conn.execute(insert(orcamentos).values(categoria=categoria, teto=float(teto)))
        else:
            conn.execute(update(orcamentos).where(orcamentos.c.id == existente).values(teto=float(teto)))


def excluir_orcamento(id_orcamento):
    with engine.begin() as conn:
        conn.execute(delete(orcamentos).where(orcamentos.c.id == id_orcamento))
