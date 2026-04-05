# Status dos Endpoints - API ObraLog

Rastreamento do status e última atualização de cada endpoint da API.

## Legenda
- ✅ Estável e funcionando
- 🔄 Recentemente alterado
- ⚠️ Depreciado (akan ser removido)
- ❌ Removido

---

## Autenticação
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `POST /api/v1/auth/register` | ✅ | - |
| `POST /api/v1/auth/login` | ✅ | - |
| `GET /api/v1/auth/me` | ✅ | - |
| `PATCH /api/v1/auth/link-telegram` | ✅ | - |
| `POST /api/v1/auth/telegram-link-codes` | ✅ | - |

---

## Usuários
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `GET /api/v1/usuarios` | ✅ | - |
| `POST /api/v1/usuarios` | ✅ | - |
| `GET /api/v1/usuarios/{usuario_id}` | ✅ | - |
| `PUT/PATCH /api/v1/usuarios/{usuario_id}` | ✅ | - |
| `DELETE /api/v1/usuarios/{usuario_id}` | ✅ | - |

---

## Frentes de Serviço
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `GET /api/v1/frentes-servico` | ✅ | - |
| `POST /api/v1/frentes-servico` | 🔄 | 2026-04-05 — Campo `observacao` adicionado |
| `GET /api/v1/frentes-servico/{frente_id}` | ✅ | - |
| `PUT/PATCH /api/v1/frentes-servico/{frente_id}` | 🔄 | 2026-04-05 — Campo `observacao` adicionado |
| `DELETE /api/v1/frentes-servico/{frente_id}` | ✅ | - |

---

## Registros (Diário de Obra)
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `GET /api/v1/registros` | ✅ | - |
| `POST /api/v1/registros` | 🔄 | 2026-04-05 — `frente_servico_id` obrigatório; `data` e `usuario_registrador_id` opcionais; `hora_registro` removido; `observacao` adicionado |
| `GET /api/v1/registros/{registro_id}` | ✅ | - |
| `PUT/PATCH /api/v1/registros/{registro_id}` | 🔄 | 2026-04-05 — `hora_registro` removido; `observacao` adicionado |
| `DELETE /api/v1/registros/{registro_id}` | ✅ | - |

---

## Dashboard
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `GET /api/v1/dashboard/overview` | ✅ | - |

---

## Healthcheck
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `GET /health` | ✅ | - |
| `GET /` | ✅ | - |

---

## Webhook
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `POST /telegram/webhook` | ✅ | - |

---

## Notas
- Para detalhes sobre alterações, consulte [docs/api-changes/](./docs/api-changes/)
- Endpoints marcados com 🔄 podem ter mudanças na estrutura de requestbody ou response
