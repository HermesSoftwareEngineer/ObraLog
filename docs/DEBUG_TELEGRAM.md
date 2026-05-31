# Guia de Debug - Logs do Telegram

## 📊 Fluxo Esperado de Logs (Caso de Sucesso)

Quando uma mensagem é enviada e processada corretamente, você verá esta sequência:

```
1. [TELEGRAM] Nova mensagem recebida - chat_id=123456789, usuario=João
2. [TELEGRAM] Texto extraído: "seu texto aqui"... (chat_id=123456789)
3. [TELEGRAM] Iniciando processamento - user_id=1, chat_id=123456789, thread_id=123456789:abc123...
4. [TELEGRAM] Invocando graph com mensagem: "seu texto aqui"...
5. [TELEGRAM] Graph retornou resposta. Tipo: <class 'dict'>
6. [TELEGRAM] Mensagens na resposta: 2
7. [TELEGRAM] UI Dispatched: False
8. [EXTRACT] Conteúdo é string: "Resposta do agente aqui"...
9. [TELEGRAM] Texto extraído (primeiro 100 chars): "Resposta do agente aqui"...
10. [TELEGRAM] Enviando resposta via Telegram - chat_id=123456789, tamanho=45
11. [SEND_MSG] Iniciando envio para chat_id=123456789, tamanho_texto=45
12. [API_CALL] Iniciando chamada: send_message com args: ['chat_id', 'text']
13. [API_CALL] Tentativa 1/3: send_message
14. [API_CALL] Sucesso em send_message
15. [TELEGRAM] Mensagem enviada com sucesso - chat_id=123456789
```

---

## 🔍 Checklist: Onde o Bot Para de Responder?

Procure pelos padrões de logs a seguir para identificar o problema:

### ❌ **Problema 1: Mensagem não é recebida**
```
[TELEGRAM] Nova mensagem recebida - chat_id=123456789, usuario=João
❌ FALTA: [TELEGRAM] Texto extraído
```
**Causa possível:** 
- Mensagem com tipo não suportado (foto, vídeo, etc. sem processamento correto)
- Veja a função `_extract_message_text_or_transcription()`

---

### ❌ **Problema 2: Graph não retorna resposta**
```
[TELEGRAM] Invocando graph com mensagem: "seu texto aqui"...
❌ FALTA: [TELEGRAM] Graph retornou resposta
📍 PROCURE POR: [TELEGRAM] ERRO ao invocar graph
```
**Causa possível:**
- Erro dentro do graph (agente IA)
- Verifique os logs do `backend/agents/graph.py`
- Problema com a thread_id ou configurable

---

### ❌ **Problema 3: Response vazio**
```
[TELEGRAM] Graph retornou resposta. Tipo: <class 'dict'>
[TELEGRAM] Mensagens na resposta: 0
❌ AVISO: response_messages vazio
```
**Causa possível:**
- Graph retornou estrutura vazia
- Verifique se `graph.invoke()` está retornando mensagens

---

### ❌ **Problema 4: Nenhuma resposta em texto (UI Despachada)**
```
[TELEGRAM] UI Dispatched: True
[TELEGRAM] Resposta via UI dispensada (ui_dispatched=True)
❌ Mensagem não é enviada porque UI foi disparada
```
**Causa possível:**
- O agente decidiu usar interface customizada em vez de texto
- Verifique a lógica em `_response_used_telegram_ui()`

---

### ❌ **Problema 5: Falha ao enviar mensagem (Erro na API)**
```
[TELEGRAM] Enviando resposta via Telegram - chat_id=123456789, tamanho=45
[SEND_MSG] Iniciando envio para chat_id=123456789, tamanho_texto=45
[API_CALL] Erro ao conectar (1/3), aguardando 1s...
[API_CALL] Erro ao conectar (2/3), aguardando 2s...
❌ [TELEGRAM] ERRO ao enviar mensagem
```
**Causa possível:**
- Token Telegram inválido
- Problema de rede/conectividade
- Telegram API bloqueando IP

---

## 📋 Níveis de Log

### `logger.info()` - Eventos importantes
Sempre visualizados. Mostram o fluxo principal.

```
[TELEGRAM] Nova mensagem recebida
[TELEGRAM] Enviando resposta via Telegram
[API_CALL] Sucesso em send_message
```

### `logger.warning()` - Alertas
Possíveis problemas, mas não críticos.

```
[TELEGRAM] Usuário não vinculado
[TELEGRAM] AVISO: response_messages vazio
[SEND_MSG] RuntimeError (sem loop)
```

### `logger.debug()` - Detalhes técnicos
Desativados por padrão. Para ativar, adicione ao seu código:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## 🎯 Seu Caso Específico: "Bot recebe mas não responde"

Baseado na sua descrição, o problema está em **uma destas etapas**:

1. **Graph está retornando sem mensagens**
   ```
   📍 Procure por: "Mensagens na resposta: 0"
   ```

2. **Resposta está sendo despachada via UI customizada**
   ```
   📍 Procure por: "UI Dispatched: True"
   ```

3. **Falha silenciosa ao enviar**
   ```
   📍 Procure por: "[TELEGRAM] ERRO ao enviar mensagem"
   ou: "[API_CALL] TelegramError"
   ```

---

## 🚀 Como Ativar Logs Detalhados

Quando rodando, você verá logs em tempo real. Para capturar tudo:

```bash
# No PowerShell
python backend/main.py 2>&1 | Tee-Object -FilePath telegram-debug.log

# Depois, procure por erros
Select-String "ERRO|WARNING" telegram-debug.log
```

---

## 💾 Logs Salvos Automaticamente

Se estiver usando o módulo `logging` corretamente, os logs são salvos em tempo real.

Procure por padrões chave:

```
GREP para encontrar problemas:
- "ERRO" - Erros críticos
- "WARNING" - Avisos
- "response_messages vazio" - Nenhuma resposta do graph
- "UI Dispatched: True" - UI customizada (sem texto)
```

---

## ✅ Próximos Passos

1. **Execute sua aplicação**
2. **Envie uma mensagem pelo Telegram**
3. **Procure pelos logs acima** no seu terminal
4. **Compartilhe comigo os logs** para diagnóstico preciso

Qual padrão você vê nos logs? 🔍
