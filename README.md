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
*   **Banco de Dados**: PostgreSQL (Container Isolado)

### Smart Routing (Otimização de Custos)
O sistema decide automaticamente qual modelo de transcrição usar, visando economia sem perda de qualidade.
Regras configuráveis via `.env`:
*   `SMART_ROUTING_ENABLE` (Default: `1`): Liga/Desliga o roteamento inteligente.
*   `SMART_ROUTING_SNR_THRESHOLD` (Default: `15.0`): Nível mínimo de pureza do áudio (dB) para considerar o modelo econômico.
*   `SMART_ROUTING_MIN_DURATION` (Default: `5.0`): Duração mínima (segundos) para o modelo econômico (que tende a falhar em áudios muito curtos).

**Lógica:**
1.  **Áudios Curtos** (< 5s) → **ElevenLabs** (Maior precisão).
2.  **Áudios Longos** (>= 5s) e **Limpos** (> 15dB) → **AssemblyAI** (Economia).
3.  **Áudios Ruidosos** → **ElevenLabs** (Robustez).

---

## ✨ Funcionalidades Principais

### 1. 🛡️ Área Administrativa & Analytics
O sistema conta com um painel de administração e endpoints de análise:
*   **Monitoramento em Tempo Real**: Status do serviço e conexões.
*   **Histórico Completo**: Logs de sugestões, transcrições e feedback.
*   **Relatórios Comparativos**: Endpoint `/api/export/xlsx` para download direto de relatórios detalhados de interações e custos em formato Excel.

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

2.  **Configure o Ambiente**:
    - Copie o arquivo de exemplo: `cp backend/.env.example backend/.env`
    - Edite `backend/.env` com suas chaves de API reais (OpenAI, xAI, ElevenLabs, etc).

3.  **Inicie o Servidor**:
    ```bash
    cd backend
    PYTHONPATH=. PORT=8765 ../stress_venv/bin/python3 app/server.py
    ```

---

## 🔌 Manual de Integração WebSocket

O Balto Server expõe um endpoint WebSocket (`/ws`) para comunicação full-duplex em tempo real. Este manual descreve como implementar um cliente compatível.

**Endpoint**: `/ws` (Ex: `wss://balto.pbpmdev.com/ws` ou `ws://localhost:8765/ws`)

### 1. Autenticação (Handshake)

Imediatamente após conectar, o cliente **DEVE** enviar um frame JSON contendo a chave de API (Balcão ID). O servidor validará a chave antes de aceitar áudio.

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
> **vad_settings** (Opcional): Permite ajustar a sensibilidade do VAD por balcão.
> *   `threshold_multiplier`: Quão mais alta que o ruído a voz deve ser (Ex: 1.5x).
> *   `min_energy`: Energia mínima absoluta para considerar voz (Ex: 120.0).

---

## 🚀 Instalação e Execução Detalhada

### 1. Configuração de Variáveis (.env)

O arquivo `.env` controla todo o comportamento do servidor. Utilize o [backend/.env.example](file:///home/pedro/%C3%81rea%20de%20trabalho/PBPM/Projetos/Externos/Balto/server/backend/.env.example) como base.

**Principais variáveis:**
- `XAI_API_KEY`: Chave para o modelo Grok (xAI).
- `OPENAI_API_KEY`: Chave para o GPT-4o.
- `ELEVENLABS_API_KEY`: Chave para o serviço de transcrição ultrarrápida (Scribe).
- `POSTGRES_*`: Configurações de conexão com o banco de dados.
- `VAD_THRESHOLD_MULTIPLIER`: Sensibilidade da detecção de voz.

### Métricas (Timestamps)
Cada interação salva no banco inclui:
- `ts_audio_received`: Chegada do chunk.
- `ts_transcription_ready`: Fim do STT.
- `ts_ai_request`: Início do request LLM.
- `ts_ai_response`: Fim do request LLM.
- `ts_client_sent`: Envio da resposta ao cliente.

Consulte `Documentation.md` para o Schema completo do banco.
*   `venv_local/`: Ambiente virtual recomendado para execução local.

---

## 5. Segurança do Banco de Dados

Para proteger contra ataques, o Banco de Dados roda em um container isolado **sem portas expostas** para a internet.

### Acesso Administrativo (Via Docker)
Como a porta 5432 está fechada externamente, para acessar o banco você deve entrar no container:

```bash
# Entrar no container do banco
docker exec -it balto-db-prod psql -U balto_user -d balto_db
```

### Resetar Senha (Se necessário)
Se precisar trocar a senha:
1.  Edite `backend/.env`.
2.  Recrie o container: `docker-compose up -d --force-recreate db`.

---

## 4. Cadastro e Provisionamento

O sistema utiliza um fluxo de hierárquico para gerenciar **Clientes** (Redes/Donos) e seus **Balcões** (Dispositivos).

### A. Cadastro de Cliente (Admin/Backoffice)
Cria o registro do responsável e gera o **código de vinculação** (6 dígitos).

**Endpoint**: `POST /cadastro/cliente`
**Payload**:
```json
{
  "email": "contato@redepharma.com",
  "razao_social": "Rede Pharma LTDA",
  "telefone": "11999998888"
}
```
**Resposta**: `{"codigo": "123456"}`

### B. Cadastro de Balcão (Dispositivo)
O dispositivo usa o código do cliente para se registrar e obter sua API Key.

**Endpoint**: `POST /cadastro/balcao`
**Payload**:
```json
{
  "nome_balcao": "Balcão Entrada 01",
  "user_codigo": "123456"
}
```

**Resposta**:
```json
{
  "api_key": "bk_a1b2c3d4...",
  "balcao_id": "uuid...",
  "status": "registered"
}
```

> **Nota de Segurança**: A `api_key` retornada não expira e deve ser armazenada com segurança pelo cliente. O código de 6 dígitos é usado apenas para o vínculo inicial.

### 6. Métricas e Logs (Database)

A tabela `interacoes` armazena o histórico completo com timestamps detalhados para auditoria de latência:

*   **ts_audio_received**: Data/Hora que o servidor recebeu o chunk de áudio que completou a frase (fim do VAD).
*   **ts_transcription_ready**: Momento em que a transcrição (STT) ficou pronta.
*   **ts_transcription_sent**: (Legado) Mesmo que ready ou momento interno.
*   **ts_ai_request**: Momento que o contexto foi enviado para o LLM.
*   **ts_ai_response**: Momento que a resposta do LLM chegou.
*   **ts_client_sent**: Momento que a recomendação foi enviada via WebSocket para o cliente.
