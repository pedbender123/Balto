# Documentação Técnica - Balto Server

## 1. Visão Geral
O Balto Server é o backend responsável por processar áudio em tempo real de "balcões" (clientes), realizar transcrição (STT), identificação de interlocutores (Speaker ID) e gerar recomendações ou insights usando LLMs (Grok/OpenAI) com base no contexto da conversa.

## 2. Arquitetura

### 2.1 WebSocket (`/ws`)
A comunicação principal ocorre via WebSocket.
- **Protocolo**:
    1. **Handshake**: Cliente envia JSON com `api_key` e configurações iniciais.
       ```json
       {
         "api_key": "bk_...",
         "vad_settings": {
           "threshold_multiplier": 1.5,
           "min_energy": 50.0
         }
       }
       ```
    2. **Streaming de Áudio**: Cliente envia chunks binários (WebM/Opus ou PCM).
    3. **Respostas do Servidor**: O servidor envia JSONs com `comando`.
       - `recomendar`: Sugestões da IA.
       - `ping`/`pong`: Keep-alive.

### 2.2 Pipeline de Áudio
1. **Decoder**: `imageio_ffmpeg` converte entrada (ex: WebM) para PCM 16kHz Mono.
2. **AudioCleaner**: Redução de ruído (SpectralGating) stateless para performance.
3. **VAD (Voice Activity Detection)**:
    - Utiliza `webrtcvad` + heurísticas de energia.
    - **Configuração Dinâmica**: Sensibilidade ajustável via `vad_settings` no handshake.
    - `threshold_multiplier`: Multiplicador sobre o ruído base (padrão 1.5).
    - `min_energy`: Piso de energia para considerar fala (padrão 50.0).

### 2.3 Speaker Identification
- **Módulo**: `speaker_id.py`
- **Fluxo**:
    - Após o VAD segmentar um trecho de fala, o áudio é enviado para `add_segment`.
    - O sistema compara o embedding do áudio com perfis cadastrados no banco.
    - Retorna: `top_id`, `score` e `speaker_data` (lista JSON com todas as probabilidades).
    - **Persistência**: O JSON bruto das probabilidades é salvo na coluna `speaker_data` da tabela `interacoes`.

### 2.4 Transcrição & Buffer
- **STT**: `transcription.py` (Whisper ou API externa).
- **Buffer (`buffer.py`)**:
    - Acumula texto transcrito para formar contexto.
    - **Regras de Disparo (LLM)**:
        1. **Acúmulo**: > 10 palavras.
        2. **Tempo**: > 5 segundos sem envio.
        3. **Gap Longo**: Se silêncio > 45s e palavras <= 2, **descarta** (evita "Ok" solto pós-conversa).
        4. **Retomada Rápida**: Se silêncio > 5s e palavras > 3, envia imediatamente (novo tópico).

## 3. Banco de Dados (PostgreSQL)

### 3.1 Tabela `interacoes`
Armazena cada ciclo de processamento (transcrição + IA).

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | SERIAL | ID único. |
| `balcao_id` | TEXT | ID do balcão emissor. |
| `transcricao_completa` | TEXT | Contexto enviado ao LLM. |
| `recomendacao_gerada` | TEXT | Log legível das sugestões ("S: ... | S: ...") ou "Nenhuma". |
| `grok_raw_response` | TEXT | JSON bruto retornado pelo LLM. |
| `speaker_data` | TEXT | JSON bruto das probabilidades de identificação de voz. |
| `ts_*` | TIMESTAMP | Métricas de latência (audio_received, trans_sent, ai_req, etc). |

### 3.2 Lógica "Nenhuma" vs NULL
- **NULL**: O campo `recomendacao_gerada` fica `NULL` se a IA **não** foi acionada (ex: buffer não atingiu limite ou regra de supressão ativada).
- **"Nenhuma"**: A IA foi acionada, mas retornou uma lista vazia de sugestões ou explicitamente nada.

## 4. Variáveis de Ambiente (.env)
- `POSTGRES_*`: Credenciais do banco.
- `VAD_THRESHOLD_MULTIPLIER`: Padrão se não enviado no WS.
- `VAD_MIN_ENERGY_THRESHOLD`: Padrão se não enviado no WS.
- `SMART_ROUTING_*`: Configuração de roteamento de modelos STT.
- `*_API_KEY`: Chaves para serviços de IA (ElevenLabs, Assembly, XAI).
