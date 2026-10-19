"""Copia os dados do banco de produção (Supabase, conforme configurado em
`.streamlit/secrets.toml`) para o SQLite local (`finance.db`), criando um
ambiente de testes seguro e isolado.

Só LÊ do Supabase — nunca escreve nada de volta lá. O SQLite local de destino
é recriado do zero (schema + dados), então rode isto sabendo que qualquer
dado que já estivesse no `finance.db` local será substituído (um backup é
feito automaticamente antes).

Uso:
    python scripts/clonar_supabase_para_local.py
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, insert, select  # noqa: E402

import database as db  # noqa: E402

LOCAL_DB_PATH = Path(__file__).parent.parent / "finance.db"

# Ordem importa: parcelamentos precisa existir antes de transacoes por causa
# do id_parcelamento (FK), e transacoes antes de alocacoes (FKs receita/despesa).
# regras_categorizacao/configuracoes não têm FK.
TABELAS_EM_ORDEM = [
    db.regras_categorizacao,
    db.configuracoes,
    db.parcelamentos,
    db.transacoes,
    db.alocacoes,
]


def main():
    origem = db.engine
    if origem.dialect.name == "sqlite":
        print("A origem configurada (database.py) já é o próprio SQLite local — nada para clonar.")
        print("Isso normalmente significa que o secrets.toml não está apontando para o Supabase.")
        return

    print(f"Origem (produção): {origem.dialect.name} @ {origem.url.host}/{origem.url.database}")

    if LOCAL_DB_PATH.exists():
        carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = LOCAL_DB_PATH.with_name(f"finance.db.bak-{carimbo}")
        shutil.copy2(LOCAL_DB_PATH, backup)
        print(f"Backup do finance.db local existente: {backup.name}")

    destino = create_engine(f"sqlite:///{LOCAL_DB_PATH}", future=True)
    db.metadata.drop_all(destino)
    db.metadata.create_all(destino)

    with origem.connect() as conn_origem, destino.begin() as conn_destino:
        for tabela in TABELAS_EM_ORDEM:
            linhas = [dict(r) for r in conn_origem.execute(select(tabela)).mappings().all()]
            if linhas:
                conn_destino.execute(insert(tabela), linhas)
            print(f"  {tabela.name}: {len(linhas)} linha(s) copiada(s)")

    print(f"\nConcluído. Banco de testes local: {LOCAL_DB_PATH}")
    print("Use `iniciar_testes.bat` para rodar o app apontando para este banco local.")


if __name__ == "__main__":
    main()
