# 2026-05-01 - Unidade (dados de empresa no Tenant) + Convites de Cadastro

## Resumo
Estende o modelo `Tenant` com campos de empresa (CNPJ, endereço, etc.) e introduz o fluxo de convite para cadastro de usuários, eliminando o registro livre.

---

## Banco de dados (migration 021)

### Novos campos em `tenants`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `cnpj` | VARCHAR(18) | CNPJ formatado (opcional) |
| `razao_social` | VARCHAR(200) | Razão social |
| `nome_fantasia` | VARCHAR(200) | Nome fantasia |
| `logradouro` | VARCHAR(200) | Rua/Av. |
| `numero` | VARCHAR(20) | Número |
| `complemento` | VARCHAR(100) | Complemento |
| `cep` | VARCHAR(9) | CEP formatado |
| `cidade` | VARCHAR(100) | Cidade |
| `estado` | VARCHAR(2) | UF (2 letras) |
| `telefone_comercial` | VARCHAR(20) | Telefone comercial |
| `email_comercial` | VARCHAR(200) | E-mail comercial |

### Nova tabela `user_invite_codes`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | UUID PK | Identificador |
| `tenant_id` | INT FK | Unidade que gerou o convite |
| `criado_por` | INT FK | Usuário que gerou (admin/gerente) |
| `email_destinatario` | VARCHAR | E-mail do convidado (opcional, informativo) |
| `codigo` | VARCHAR(32) UNIQUE | Código alfanumérico do convite |
| `nivel_acesso` | VARCHAR | Nível de acesso pré-definido (`encarregado`, `gerente`, `administrador`) |
| `expira_em` | TIMESTAMPTZ | Expiração (24 horas após criação) |
| `usado_em` | TIMESTAMPTZ | Preenchido quando consumido |
| `usado_por` | INT FK | Usuário que se cadastrou com o convite |
| `ativo` | BOOLEAN | `false` após uso ou cancelamento |

---

## Endpoints novos / alterados

### `POST /api/v1/auth/register` — **breaking change**
Agora exige `invite_code` no body. Sem convite válido, retorna `400`.

**Request body:**
```json
{
  "nome": "João Silva",
  "email": "joao@empresa.com",
  "senha": "minhasenha",
  "telefone": "11999998888",
  "invite_code": "ABC123XYZ456"
}
```

**Regras:**
- Convite deve existir, estar ativo e não ter sido usado.
- Convite deve estar dentro da validade (24 h).
- O usuário é criado no tenant do convite com o nível de acesso definido no convite.
- O convite é marcado como usado (não reutilizável).

**Erros:**
| Código | Motivo |
|--------|--------|
| 400 | `invite_code` ausente |
| 404 | Código não encontrado |
| 409 | Convite já utilizado |
| 409 | E-mail já cadastrado nesta unidade |
| 410 | Convite expirado |

---

### `POST /api/v1/auth/invite-codes` — novo
Gera um convite de cadastro. Requer perfil **admin** ou **gerente**.

**Request body:**
```json
{
  "nivel_acesso": "encarregado",
  "email_destinatario": "convidado@empresa.com"
}
```

**Response `201`:**
```json
{
  "ok": true,
  "invite": {
    "id": "uuid",
    "codigo": "ABC123XYZ456",
    "email_destinatario": "convidado@empresa.com",
    "nivel_acesso": "encarregado",
    "expira_em": "2026-05-02T12:00:00+00:00",
    "usado_em": null,
    "ativo": true,
    "criado_por": 1,
    "created_at": "2026-05-01T12:00:00+00:00"
  }
}
```

---

### `GET /api/v1/auth/invite-codes` — novo
Lista convites ativos (não usados) da unidade do usuário autenticado. Requer admin/gerente.

**Response `200`:** lista de objetos `invite` (mesmo schema acima).

---

### `DELETE /api/v1/auth/invite-codes/{codigo}` — novo
Cancela (desativa) um convite. Requer admin/gerente.

**Response `200`:** `{"ok": true}`

---

### `GET /api/v1/tenant` — novo (substitui `/config`)
Retorna todos os dados da unidade do usuário autenticado.

**Response `200`:**
```json
{
  "ok": true,
  "tenant_id": 1,
  "nome": "Construtora XYZ",
  "slug": "construtora-xyz",
  "location_type": "estaca",
  "tipo_negocio": "construção civil",
  "ativo": true,
  "cnpj": "12.345.678/0001-99",
  "razao_social": "Construtora XYZ Ltda",
  "nome_fantasia": "XYZ Obras",
  "logradouro": "Av. Brasil",
  "numero": "1000",
  "complemento": "Sala 201",
  "cep": "01234-567",
  "cidade": "São Paulo",
  "estado": "SP",
  "telefone_comercial": "(11) 3000-0000",
  "email_comercial": "contato@xyz.com.br"
}
```

---

### `PATCH /api/v1/tenant` — novo (substitui `/config`)
Atualiza dados da unidade. Requer admin/gerente.

**Campos aceitos no body** (todos opcionais):
`nome`, `tipo_negocio`, `location_type`, `cnpj`, `razao_social`, `nome_fantasia`, `logradouro`, `numero`, `complemento`, `cep`, `cidade`, `estado`, `telefone_comercial`, `email_comercial`

**Response `200`:** mesmo schema do `GET /api/v1/tenant`.

---

### `/api/v1/tenant/config` — alias legado
`GET` e `PATCH /api/v1/tenant/config` continuam funcionando e delegam para os novos endpoints acima.

---

## Arquivos alterados
- `backend/db/migrations/sql/20260501_021_extend_tenants_and_invite_codes.up.sql`
- `backend/db/migrations/sql/20260501_021_extend_tenants_and_invite_codes.down.sql`
- `backend/db/models.py` — campos de empresa em `Tenant`, novo model `UserInviteCode`
- `backend/db/repository.py` — novo `UserInviteCodeRepository`
- `backend/api/routes/auth.py` — `register` exige convite; 3 novos endpoints de invite
- `backend/api/routes/tenant.py` — refatorado com rotas limpas e helper `_tenant_payload`
