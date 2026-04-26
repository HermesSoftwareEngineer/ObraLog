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
| `POST /api/v1/registros` | 🔄 | 2026-04-14 — contrato atualizado: `pista` é alias legado e `lado_pista` é o campo técnico persistido |
| `GET /api/v1/registros/{registro_id}` | ✅ | - |
| `PUT/PATCH /api/v1/registros/{registro_id}` | 🔄 | 2026-04-14 — contrato atualizado: `pista` é alias legado e `lado_pista` é o campo técnico persistido |
| `GET /api/v1/registros/{registro_id}/auditoria` | ✅ | 2026-04-14 — Novo endpoint para trilha de alterações |
| `DELETE /api/v1/registros/{registro_id}` | ✅ | - |

---

## Mensagens de Campo
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `GET /api/v1/mensagens-campo` | ✅ | 2026-04-14 — Novo endpoint para rastreabilidade de entrada |
| `GET /api/v1/mensagens-campo/{mensagem_id}` | ✅ | 2026-04-14 — Novo endpoint de detalhe |

---

## Fluxo Removido
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `/api/v1/lancamentos/*` | ❌ | 2026-04-14 — Fluxo removido; API retorna `410 Gone` |

---

## Dashboard
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `GET /api/v1/dashboard/overview` | ✅ | - |

---

## Chat (Conversas do Agente)
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `GET /api/v1/chat/conversas` | ✅ | 2026-04-24 — Novo endpoint; acesso restrito a administradores |
| `GET /api/v1/chat/conversas/{chat_id}/mensagens` | ✅ | 2026-04-24 — Novo endpoint; acesso restrito a administradores |

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
