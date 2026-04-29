# Inicializar Banco de Dados

## Opção 1: Via Script Python (Recomendado)

```bash
python backend/db/init_db.py
```

Isso vai executar o schema.sql no seu banco de dados Supabase automaticamente.

Observação: na inicialização da aplicação, o módulo de sessão também executa migrações runtime idempotentes para alinhar ambientes já existentes.

## Opção 2: Via Supabase Console (SQL Editor)

1. Abra [Supabase Console](https://supabase.com/dashboard)
2. Selecione seu projeto
3. Vá para **SQL Editor**
4. Copie e cole o conteúdo de [backend/db/schema.sql](schema.sql)
5. Execute

## Opção 3: Via psql (Linha de Comando)

```bash
psql -h db.pfehfanphodgazizebpt.supabase.co \
     -U postgres \
     -d postgres \
     -f backend/db/schema.sql
```

## Verificar Tabelas

```python
from backend.db.models import Base
from backend.db.repository import Repository
from sqlalchemy import inspect
from backend.core.config import settings
from sqlalchemy import create_engine

engine = create_engine(settings.database_url)
inspector = inspect(engine)
print("Tabelas criadas:", inspector.get_table_names())
```

## Migração SQL Aplicada (2026-04-14)

Para bancos já existentes, execute também a migration:

- `backend/db/migrations/sql/20260414_010_ingestao_lancamentos_e_integridade_registros.up.sql`

Essa migration inclui:

- Correção de integridade em `registros` (`usuario_registrador_id` com `ON DELETE RESTRICT`)
- Remoção da coluna redundante `pista` (mantendo `lado_pista`)
- Criação de `mensagens_campo`, `lancamentos_diario`, `lancamento_itens`, `lancamento_recursos`, `lancamento_midias`
- Ajuste da constraint de campos obrigatórios sem exigir `observacao`

## Usar no Código

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.repository import Repository
from backend.db.models import NivelAcesso

engine = create_engine(settings.database_url)

# Criar um usuário
with Session(engine) as db:
    usuario = Repository.usuarios.criar(
        db,
        nome="João Silva",
        email="joao@example.com",
        senha="hash_da_senha",
        nivel_acesso=NivelAcesso.GERENTE
    )
    print(f"Usuário criado: {usuario.id}")

    # Exemplos de leitura
    usuarios = Repository.usuarios.listar(db)
    registro = Repository.usuarios.obter_por_email(db, "joao@example.com")
```
