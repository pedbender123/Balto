# Manual de Execução - Sistema Balto

Este manual descreve como configurar o ambiente e executar os scripts de transcrição e geração de relatório.

## 1. Pré-requisitos

*   **Python 3.10+** instalado.
*   **Virtualenv** configurado.
*   **Chaves de API** (ElevenLabs, AssemblyAI, Deepgram, Gladia).

## 2. Configuração do Ambiente

1.  **Navegue até a pasta do servidor**:
    ```bash
    cd server
    ```

2.  **Ative o ambiente virtual**:
    ```bash
    # Se ainda não criou: python3 -m venv venv_local
    source venv_local/bin/activate
    ```

3.  **Instale as dependências**:
    ```bash
    pip install -r backend/requirements.txt
    pip install openpyxl requests python-dotenv imageio-ffmpeg
    ```

4.  **Configure o arquivo `.env`**:
    Edite o arquivo `backend/.env` e adicione as chaves:
    ```env
    ELEVENLABS_API_KEY=sk_...
    ASSEMBLYAI_API_KEY=...
    DEEPGRAM_API_KEY=...
    GLADIA_API_KEY=...
    BALTO_SERVER_URL=https://balto.pbpmdev.com
    ```
    *(Nota: `BALTO_SERVER_URL` define onde o script vai buscar a segmentação. O padrão é a VPS. Para local, use `http://localhost:8765`)*

## 3. Fluxo de Execução

O processo é dividido em duas etapas para garantir segurança e performance.

### Etapa 1: Transcrição dos Originais (Local & Direto)
Este script transcreve os arquivos originais da pasta `testes/1_input` usando a API da ElevenLabs diretamente, sem passar pelo servidor de segmentação. Isso gera a "verdade absoluta" do áudio inteiro.

**Comando:**
```bash
python3 testes/transcribe_originals_direct.py
```
*   **Entrada**: `testes/1_input/*.webm`
*   **Saída**: `testes/planilhas/Relatorio_Originais.xlsx`
*   **Funcionalidade**: Resume automaticamente se parar.

### Etapa 2: Segmentação e Comparativo (Via VPS)
Este script pega os mesmos áudios, envia para o servidor (VPS) para serem segmentados (VAD), e então transcreve cada segmento usando 4 modelos (ElevenLabs, AssemblyAI, Deepgram, Gladia).

**Comando:**
```bash
# Se definiu BALTO_SERVER_URL no .env, basta rodar:
python3 testes/generate_spreadsheet_report.py

# OU forçando a URL manualmente:
BALTO_SERVER_URL=https://balto.pbpmdev.com python3 testes/generate_spreadsheet_report.py
```
*   **Entrada**: `testes/1_input/*.webm` e `Relatorio_Originais.xlsx` (cache)
*   **Saída**: `testes/planilhas/Relatorio_Segmentos.xlsx`

## 4. Resultados

Ao final, você terá na pasta `testes/planilhas`:
1.  **Relatorio_Originais.xlsx**: Transcrição completa de cada arquivo (ElevenLabs).
2.  **Relatorio_Segmentos.xlsx**: Quebra frase a frase com colunas comparativas:
    *   ElevenLabs
    *   AssemblyAI
    *   Deepgram
    *   Gladia

## 5. Rodando o Servidor Localmente (Opcional)

Se quiser rodar o backend na sua máquina (em vez da VPS):

1.  **Inicie o Servidor**:
    ```bash
    cd backend
    PYTHONPATH=. python3 app/server.py
    ```
    *O servidor rodará na porta 8765.*

2.  **Aponte os Scripts para Local**:
    No terminal dos testes:
    ```bash
    export BALTO_SERVER_URL=http://localhost:8765
    python3 testes/generate_spreadsheet_report.py
    ```

## Solução de Problemas

*   **Erro 401 (Quota Exceeded)**: Verifique se a chave da ElevenLabs tem créditos. Atualize no `.env`.
*   **Erro 502 Bad Gateway (VPS)**: O servidor pode estar reiniciando. Aguarde 1 minuto e tente novamente.
*   **Erro de Permissão**: Verifique se as pastas `testes/planilhas` e `testes/2_cortados` têm permissão de escrita.
