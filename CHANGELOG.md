# Changelog - ObraLog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/).

---

## [2026-04-05] - Alterações nos Modelos de Frente de Serviço e Registros

### 📝 Descrição Geral
Ajuste dos campos obrigatórios e opcionais, adição de campo de observação e remoção do campo `hora_registro` (redundante com `created_at`).

### ✨ Adicionado
- **Frentes de Serviço**: Campo `observacao` (texto, opcional)
- **Registros**: Campo `observacao` (texto, opcional)

### 🔄 Alterado
- **Frentes de Serviço**: 
  - `encarregado_responsavel` agora é opcional (antes era optional, mas agora mais claro)
  - Apenas `nome` é obrigatório

- **Registros**:
  - `frente_servico_id` agora é **obrigatório** (antes era opcional)
  - `data` agora é **opcional** (antes era obrigatório)
  - `usuario_registrador_id` agora é **opcional** (antes era obrigatório)
  - Demais campos (`estaca_inicial`, `estaca_final`, `resultado`, `tempo_manha`, `tempo_tarde`, `pista`, `lado_pista`) permanecem opcionais

### ❌ Removido
- **Registros**: Campo `hora_registro` removido. Use `created_at` para obter o timestamp de criação do registro.

### 📋 Arquivos Modificados
- `backend/db/models.py` - Modelos SQLAlchemy
- `backend/db/schema.sql` - Schema do banco de dados
- `backend/db/repository.py` - Métodos de persistência
- `backend/api/routes/crud.py` - Endpoints REST
- `backend/agents/tools/database_tools.py` - Tools dos agentes

### 🔢 Database
- Migration UP: `backend/db/migrations/sql/20260405_004_update_frente_servico_registros.up.sql`
- Migration DOWN: `backend/db/migrations/sql/20260405_004_update_frente_servico_registros.down.sql`

---
