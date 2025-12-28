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
*   **LLM (Inteligência)**: xAI (Grok Beta) / OpenAI (GPT-4o)
*   **Banco de Dados**: SQLite (Gerenciado via `app.db`)

---

## ✨ Funcionalidades Principais

### 1. 🛡️ Área Administrativa & Analytics
O sistema conta com um painel de administração e endpoints de análise:
*   **Monitoramento em Tempo Real**: Status do serviço e conexões.
*   **Histórico Completo**: Logs de sugestões, transcrições e feedback.
*   **Relatórios Comparativos**: Scripts para gerar planilhas Excel (`Relatorio_Originais.xlsx`, `Relatorio_Segmentos.xlsx`) comparando precisão de diferentes provedores de transcrição.

### 2. 🚀 Pipeline de Áudio Avançado
O fluxo de processamento de áudio foi rigorosamente otimizado:
1.  **Limpeza**: O áudio bruto passa por um filtro de redução de ruído estacionário para remover zumbidos de ar-condicionado e chiados.
2.  **VAD Adaptativo**: O sistema detecta apenas segmentos de voz humana, ignorando silêncio e ruídos impulsivos (bips, portas).
3.  **Segmentação Inteligente**: O áudio é cortado precisamente nas pausas de fala para maximizar a acurácia da transcrição.

---

## 📡 Endereços de Acesso

| Ambiente | URL Base (HTTP) | WebSocket (WSS) | Descrição |
| :--- | :--- | :--- | :--- |
| **Produção (VPS)** | `https://balto.pbpmdev.com` | `wss://balto.pbpmdev.com/ws` | Ambiente protegido com SSL/TLS. |
| **Local (Dev)** | `http://localhost:8765` | `ws://localhost:8765/ws` | Para testes locais e desenvolvimento. |

> **Nota**: O ambiente local pode rodar na porta **8766** caso a 8765 esteja ocupada. Verifique os logs ao iniciar.

---

## 🚀 Instalação e Execução

Para um guia passo-a-passo detalhado de como rodar tudo localmente, veja o arquivo **[MANUAL_EXECUCAO_LOCAL.md](MANUAL_EXECUCAO_LOCAL.md)**.

### Resumo Rápido (Local)

1.  **Instale dependências**:
    ```bash
    pip install -r backend/requirements.txt
    pip install imageio-ffmpeg
    ```

2.  **Configure `.env`** em `backend/`:
    ```env
    ELEVENLABS_API_KEY=...
    ASSEMBLYAI_API_KEY=...
    ADMIN_SECRET=admin123
    ```

3.  **Inicie o Servidor**:
    ```bash
    cd backend
    PYTHONPATH=. PORT=8766 ../venv_local/bin/python3 app/server.py
    ```

4.  **Execute Testes (Orquestrador Local)**:
    ```bash
    BALTO_SERVER_URL=http://localhost:8766 python3 testes/generate_spreadsheet_report.py
    ```

---

## 🔌 Protocolo WebSocket

O cliente Balto (Desktop/Web) deve se conectar ao endpoint `/ws`:

1.  **Autenticação**: Enviar JSON `{"comando": "auth", "api_key": "..."}`.
2.  **Streaming**: Enviar áudio (PCM 16-bit 16kHz) continuamente.
3.  **Recepção**: O servidor envia eventos `{"comando": "recomendar", ...}` quando identifica uma oportunidade.

---

## 📂 Estrutura do Projeto

*   `backend/`: Código fonte do servidor (`app/server.py`, `app/vad.py`, etc).
*   `testes/`: Scripts de teste e geração de relatórios.
    *   `1_input`: Pasta para colocar arquivos de áudio para teste.
    *   `planilhas`: Onde os relatórios Excel são salvos.
*   `venv_local/`: Ambiente virtual recomendado para execução local.
