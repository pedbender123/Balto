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



---

## 🔌 Manual de Integração WebSocket

O Balto Server expõe um endpoint WebSocket (`/ws`) para comunicação full-duplex em tempo real. Este manual descreve como implementar um cliente compatível.

**Endpoint**: `/ws` (Ex: `wss://balto.pbpmdev.com/ws` ou `ws://localhost:8765/ws`)

### 1. Autenticação (Handshake)

Imediatamente após conectar, o cliente **DEVE** enviar um frame JSON contendo a chave de API (Balcão ID). O servidor validará a chave antes de aceitar áudio.

**Cliente -> Servidor (JSON):**
```json
{
  "api_key": "seu_token_de_acesso"
}
```

*   **Sucesso**: A conexão permanece aberta.
*   **Erro**: O servidor fecha a conexão com Code `4001` (Close Reason: `API Key Invalida`).

### 2. Streaming de Áudio

Após a autenticação, envie o áudio capturado através de frames **Binários**.

*   **Formato de Container**: WebM (Recomendado) ou WAV.
*   **Codec**: Opus (Recomendado) ou PCM.
*   **Especificações**: 16kHz, 16-bit, Mono.

> **Importante**: Envie chunks pequenos (ex: a cada 250ms ou 500ms) para garantir baixa latência. O servidor processa o stream continuamente usando FFmpeg, permitindo flexibilidade de formatos, mas **WebM/Opus** é fortemente sugerido para eficiência de banda.

**Cliente -> Servidor (Binary):**
*   `[Binary Data Chunk 1]`
*   `[Binary Data Chunk 2]`
*   `...`

### 3. Eventos de Recomendação

O servidor enviará frames JSON assíncronos sempre que o motor de IA detectar uma oportunidade de venda ou sugestão relevante baseada no diálogo.

**Servidor -> Cliente (JSON):**
```json
{
  "comando": "recomendar",
  "produto": "Nome do Produto Sugerido",
  "explicacao": "Explicação curta do motivo da recomendação (para o atendente).",
  "transcricao_base": "Trecho do diálogo que originou a sugestão.",
  "atendente": "Nome do Atendente (se identificado via biometria)"
}
```

### Exemplo de Fluxo

1.  **Client** Conecta em `wss://.../ws`.
2.  **Client** Envia `{"api_key": "123"}`.
3.  **Client** Começa a enviar chunks de áudio binário.
4.  **Server** Processa VAD e silêncio.
5.  **Server** Detecta fala -> Transcreve -> Analisa.
6.  **Server** Envia `{"comando": "recomendar", ...}`.
7.  **Client** Renderiza sugestão na tela.

---

## 📂 Estrutura do Projeto

*   `backend/`: Código fonte do servidor (`app/server.py`, `app/vad.py`, etc).
*   `testes/`: Scripts de teste e geração de relatórios.
    *   `planilhas`: Onde os relatórios Excel são salvos.
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
