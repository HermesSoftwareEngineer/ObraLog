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

## Alertas
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `GET /api/v1/alertas` | 🔄 | 2026-04-29 — Payload de lista simplificado e campo `reported_by_nome` adicionado |
| `POST /api/v1/alertas` | 🔄 | 2026-04-29 — Resposta padronizada no payload de detalhe |
| `GET /api/v1/alertas/{alert_id}` | 🔄 | 2026-04-29 — Payload de detalhe padronizado com `*_nome` |
| `PATCH /api/v1/alertas/{alert_id}/status` | 🔄 | 2026-04-29 — Retorno inclui `resolved_by_nome`, `read_by_nome`, `reported_by_nome` |
| `POST /api/v1/alertas/{alert_id}/read` | 🔄 | 2026-04-29 — Retorno inclui `leitura.worker_nome` e payload de detalhe |
| `POST /api/v1/alertas/{alert_id}/unread` | 🔄 | 2026-04-29 — Retorno usa payload de detalhe padronizado |
| `GET /api/v1/alertas/codigo/{code}` | 🔄 | 2026-04-29 — Payload de detalhe padronizado com `*_nome` |
| `DELETE /api/v1/alertas/{alert_id}` | ✅ | - |
| `GET /api/v1/alertas/tipos/simples` | 🔄 | 2026-04-29 — Novo endpoint simples para listagem de tipos |
| `POST /api/v1/alertas/tipos/simples` | 🔄 | 2026-04-29 — Novo endpoint simples para cadastro de tipos |
| `PATCH /api/v1/alertas/tipos/simples/{tipo_id}` | 🔄 | 2026-04-29 — Novo endpoint simples para atualização de tipos |
| `DELETE /api/v1/alertas/tipos/simples/{tipo_id}` | 🔄 | 2026-04-29 — Novo endpoint simples para remoção de tipos |
| `GET /api/v1/alertas/tipos` | ✅ | - |
| `GET /api/v1/alertas/tipos/{tipo_id}` | ✅ | - |
| `POST /api/v1/alertas/tipos` | ✅ | - |
| `PATCH /api/v1/alertas/tipos/{tipo_id}` | ✅ | - |
| `DELETE /api/v1/alertas/tipos/{tipo_id}` | ✅ | - |

---

## Chat (Conversas do Agente)
| Endpoint | Status | Última alteração |
|----------|--------|------------------|
| `GET /api/v1/chat/conversas` | ✅ | 2026-04-24 — Novo endpoint; acesso restrito a administradores |
| `GET /api/v1/chat/mensagens?chat_id={chat_id}` | ✅ | 2026-04-29 — Campo `direcao` (user\|agent) agora persistido; respostas do agente integradas |
| `GET /api/v1/chat/conversas/{chat_id}/mensagens` | ✅ | 2026-04-29 — Compatibilidade mantida com clientes legados |

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
