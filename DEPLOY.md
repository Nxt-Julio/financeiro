# Deploy no Streamlit Community Cloud + Postgres (Neon)

O app foi migrado para **SQLAlchemy** e funciona com dois bancos, sem mudança de código:

- **Local (seu PC):** sem configurar nada, usa o SQLite (`finance.db`).
- **Nuvem:** se existir o secret `database.url`, usa o Postgres apontado por ele.

Siga os passos abaixo. Os itens marcados com 🧑 exigem você (contas, senhas, cliques) —
não dá para eu fazer por você.

---

## 1. 🧑 Criar um Postgres grátis (Neon)

1. Acesse https://neon.tech e crie uma conta (login com Google/GitHub).
2. Crie um projeto (New Project). Escolha a região mais próxima (ex: US East).
3. Ao criar, o Neon mostra a **connection string**. Copie a versão
   "psycopg2"/"parameters" no formato:
   `postgresql://usuario:senha@ep-xxxx.us-east-2.aws.neon.tech/neondb?sslmode=require`
4. Guarde essa string — é o seu `database.url`.

> Alternativa: **Supabase** (https://supabase.com) também funciona. Em
> Project Settings → Database → Connection string (URI). Mesmo formato.
> Só troque `postgres://` por `postgresql://` se vier assim (o app já corrige isso sozinho).

As tabelas são criadas automaticamente na primeira vez que o app rodar (`init_db()`),
inclusive as regras de categorização (Zandona/Fort/Cooper) e os nomes padrão de
responsável. Você reconfigura os nomes depois em ⚙️ Configurações.

## 2. 🧑 Subir o código para um repositório no GitHub

1. Crie um repositório **privado** no GitHub (dados financeiros — mantenha privado).
2. Envie o conteúdo da pasta `D:\financeiro` para o repositório. O `.gitignore` já
   garante que o `finance.db`, os backups e o `secrets.toml` **não** vão junto.

   Sugestão de comandos (rode dentro de `D:\financeiro`):
   ```
   git init
   git add .
   git commit -m "Gestão financeira pessoal"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git
   git push -u origin main
   ```

## 3. 🧑 Criar o app no Streamlit Community Cloud

1. Acesse https://share.streamlit.io e faça login com o GitHub.
2. **New app** → selecione o repositório, o branch `main` e o arquivo principal `app.py`.
3. Em **Advanced settings → Secrets**, cole (com a URL real do passo 1):
   ```toml
   [database]
   url = "postgresql://usuario:senha@host:5432/banco?sslmode=require"
   ```
4. **Deploy**. Na primeira execução o app cria as tabelas no Postgres.

## 4. 🧑 Deixar o app privado (importante — dados pessoais)

No painel do app: **Settings → Sharing** → desmarque o acesso público e adicione
apenas os e-mails autorizados (o seu e o da Bianca). Assim só quem você liberar,
logando com a conta Google, consegue abrir o app.

## 5. Importar os dados do ano

Com o app no ar e apontando para o Postgres, use normalmente as telas de
**Leitura de Holerite**, **Leitura de Extrato** e **Lançamento Manual**. Tudo é
gravado direto no Postgres (persistente, ao contrário do disco do Streamlit Cloud).

---

## Backup do banco para o Google Drive (opcional)

Com Postgres na nuvem, o backup deixa de ser "copiar um arquivo". Duas opções:

- **Neon/Supabase já fazem backups automáticos** do banco (ver painel de cada um).
- Para exportar você mesmo, rode `pg_dump` com a sua connection string e envie o
  arquivo `.sql` gerado para o Google Drive (manual, ou automatizado com `rclone`).
  Posso preparar um script para isso se quiser.

## Desenvolvimento local continua igual

No seu PC, sem `secrets.toml`, o app segue usando o `finance.db` (SQLite) via
`iniciar.bat`. Assim você testa mudanças localmente sem tocar no banco de produção.
