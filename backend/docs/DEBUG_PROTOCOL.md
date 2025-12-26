# Protocolo de Depuração de Áudio (Debug Stream)

Este documento descreve o protocolo de comunicação WebSocket para a rota de testes `/ws/debug_audio`.
Esta rota é destinada ao desenvolvimento e calibração de modelos, fornecendo feedback em tempo real sobre o pipeline de processamento de áudio.

## Conexão

**Endpoint:** `ws://<HOST>/ws/debug_audio`

**Autenticação:**
É obrigatório fornecer a chave de administrador (ADM Key) configurada no `.env`.
- **Query Param:** `?key=SUA_ADM_KEY`
- **Header:** `X-Adm-Key: SUA_ADM_KEY`

Se a chave for inválida, a conexão será encerrada imediatamente com código 4003.

## Fluxo de Dados

1.  **Cliente -> Servidor (Áudio):**
    O cliente envia streams de áudio binário (PCM 16-bit, 16kHz, Mono) CONTINUAMENTE.
    Não envie JSON pelo socket, apenas bytes de áudio.

2.  **Servidor -> Cliente (Eventos JSON):**
    O servidor envia mensagens de texto JSON descrevendo eventos internos.

### Tipos de Eventos

Todos os eventos seguem o formato:
```json
{
  "event": "NOME_DO_EVENTO",
  "data": { ... }
}
```

#### 1. `vad_signal` (Opcional/Verbose)
Indica o estado atual do VAD (falando ou silêncio) para frames individuais.
```json
{
  "event": "vad_signal",
  "data": {
    "is_speech": true,
    "prob": 0.98
  }
}
```

#### 2. `segment_created`
Disparado quando o servidor fecha um segmento de fala e começa a processá-lo.
```json
{
  "event": "segment_created",
  "data": {
    "segment_id": "seg_12345",
    "duration_seconds": 2.45,
    "timestamp": "2024-12-26T15:00:00"
  }
}
```

#### 3. `routing_decision`
Explica a decisão de qual modelo usar (ElevenLabs vs AssemblyAI).
```json
{
  "event": "routing_decision",
  "data": {
    "segment_id": "seg_12345",
    "snr_db": 25.4,
    "duration": 2.45,
    "chosen_model": "AssemblyAI",
    "reason": "HighSNR+Short (>15dB, <5s)"
  }
}
```

#### 4. `transcription_result`
Retorna o texto transcrito para o segmento.
```json
{
  "event": "transcription_result",
  "data": {
    "segment_id": "seg_12345",
    "model": "AssemblyAI",
    "text": "Olá, eu gostaria de pedir uma pizza.",
    "latency_ms": 450
  }
}
```

#### 5. `analysis_result` (Grok/LLM)
Retorna a análise semântica ou resposta da IA sobre o texto.
```json
{
  "event": "analysis_result",
  "data": {
    "segment_id": "seg_12345",
    "analysis": "Pedido de comida identificado. Item: Pizza."
  }
}
```

## Exemplo de Cliente (Python)

```python
import websocket
import threading

def on_message(ws, message):
    print(f"Evento: {message}")

ws = websocket.WebSocketApp("ws://localhost:8000/ws/debug_audio?key=123",
                            on_message=on_message)
# Em uma thread separada, envie audio_bytes pelo ws.send(bytes, opcode=websocket.ABNF.OPCODE_BINARY)
ws.run_forever()
```
