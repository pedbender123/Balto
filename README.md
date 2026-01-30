# 🤖 Balto Server Backend

**Sistema de Inteligência Farmacêutica em Tempo Real**

O Balto Server é um serviço de backend assíncrono de alta performance desenvolvido em Python. Ele atua como o cérebro da operação, orquestrando o reconhecimento de fala (STT), processamento de linguagem natural (LLM) e a lógica de sugestão farmacêutica.

O sistema suporta operação **Híbrida**, podendo rodar tanto em servidores VPS quanto localmente para testes e desenvolvimento.

---

## 📋 Stack Tecnológica

*   **Linguagem**: Python 3.12+
*   **Server**: AIOHTTP (Async/WebSockets & REST API)
*   **Audio Pipeline**:
    *   **Cleaning**: `noisereduce` (Stationary Noise Reduction)
    *   **VAD**: `webrtcvad` + Adaptive Energy Gate (Detecção precisa de fala vs. ruído)
    *   **Decoding**: `ffmpeg` (via `imageio-ffmpeg` para portabilidade local)
*   **STT (Speech-to-Text)**:
    *   ElevenLabs (Scribe)
    *   AssemblyAI (Backup/Comparativo)
*   **LLM (Inteligência)**: OpenAI (GPT-4o / GPT-4o-mini)
*   **Banco de Dados**: PostgreSQL (Container Isolado)

---

## ✨ Funcionalidades Principais

### 1. 🛒 Sistema de Cestas Inteligentes
O sistema implementa uma lógica de recomendação baseada em cestas de produtos (`cestas.json`):
*   **Pipeline em Duas Etapas**:
    1.  **Normalização**: A IA limpa a transcrição ruidosa, extraindo apenas Medicamentos, Sintomas e Doenças.
    2.  **Classificação**: Define a Macro e Micro categoria da intenção de venda.
*   **Motor de Resolução**: Cruza a classificação com a base de conhecimento de cestas para sugerir itens complementares (Cross-selling).

### 2. 📊 Telemetria Avançada e Bio-Métricas
O sistema registra métricas profundas de cada interação para análise de BI e diagnóstico:
*   **Performance**: Uso de CPU e RAM no exato momento da frase.
*   **Bio-Métricas**: Pitch médio, SNR real, Centróide Espectral e ZCR do áudio.
*   **Timestamps**: Rastreamento completo da latência (Áudio -> STT -> IA 1 -> IA 2 -> WS).

---

## �️ Ferramentas e Testes (Extra&Tools)
Todo o material de utilidade e validação está concentrado na pasta `Extra&Tools/api_test_suite`:
*   `/assets`: Áudios de teste e amostras de voz reais.
*   `/results`: Relatórios de validação (`walkthrough.md`) e provas de banco de dados (`db_proof.txt`).
*   `run_protocol.py`: Protocolo de teste automatizado (REST + WebSocket).

---

## 📡 Endereços de Acesso

| Ambiente | URL Base (HTTP) | WebSocket (WSS) | Descrição |
| :--- | :--- | :--- | :--- |
| **Produção (VPS)** | `https://balto.pbpmdev.com` | `wss://balto.pbpmdev.com/ws` | Ambiente protegido com SSL/TLS. |
| **Local (Dev)** | `http://localhost:8765` | `ws://localhost:8765/ws` | Para testes locais e desenvolvimento. |

---

##  Manual de Integração WebSocket

O Balto Server expõe um endpoint WebSocket (`/ws`) para comunicação full-duplex em tempo real.

**Endpoint**: `/ws` (Ex: `ws://localhost:8765/ws`)

### 1. Autenticação (Handshake)
Imediatamente após conectar, o cliente **DEVE** enviar a chave de API.

**Cliente -> Servidor (JSON):**
```json
{
  "api_key": "seu_token_de_acesso",
  "vad_settings": {
    "threshold_multiplier": 1.5,
    "min_energy": 120.0
  }
}
```

---

## 🚀 Instalação e Execução
Consulte o arquivo **[MANUAL_EXECUCAO_LOCAL.md](MANUAL_EXECUCAO_LOCAL.md)** para instruções detalhadas.

### Resumo Rápido
1. `pip install -r backend/requirements.txt`
2. Configure o `.env` seguindo o modelo.
3. Inicie: `docker-compose up -d --build`
