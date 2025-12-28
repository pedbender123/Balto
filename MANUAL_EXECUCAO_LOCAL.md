# Manual de Execução Local - Sistema Balto

Este documento descreve como configurar e rodar o sistema completo (Servidor Backend + Script de Relatório) inteiramente em sua máquina local.

## 1. Pré-requisitos

*   **Python 3.12+** instalado.
*   **Virtualenv** (recomendado).
*   Chaves de API (ElevenLabs, AssemblyAI) no arquivo `.env`.

## 2. Configuração do Ambiente

1.  **Navegue até a pasta do servidor**
    ```bash
    cd /caminho/para/Balto/server 
    ```

2.  **Crie e ative o ambiente virtual** (caso não exista):
    ```bash
    python3 -m venv venv_local
    source venv_local/bin/activate
    ```

3.  **Instale as dependências**:
    O backend possui requisitos específicos. Além disso, para rodar local sem instalar o FFmpeg no sistema, instalamos o `imageio-ffmpeg`.
    ```bash
    pip install -r backend/requirements.txt
    pip install imageio-ffmpeg
    ```

## 3. Configuração das Chaves (Env)

Certifique-se de que o arquivo `backend/.env` exista e contenha as chaves necessárias:

```env
ELEVENLABS_API_KEY=sua_chave_aqui
ASSEMBLYAI_API_KEY=sua_chave_aqui
ADMIN_SECRET=admin123
# Outras variáveis opcionais
```

## 4. Executando o Servidor Localmente

Para iniciar o servidor, precisamos definir o `PYTHONPATH` para que ele encontre o pacote `app`, e opcionalmente definir a porta (padrão 8765, mas recomendamos 8766 se o 8765 estiver ocupado).

Execute o seguinte comando na raiz `server/`:

```bash
cd backend
PYTHONPATH=. PORT=8766 ../venv_local/bin/python3 app/server.py
```

*Se tudo der certo, você verá:*
`[BOOT] ...`
`Balto Server 2.0 Rodando na porta 8766`

Mantenha esse terminal aberto.

## 5. Executando o Teste / Gerador de Relatório

Em **outro terminal**, navegue até a pasta `server/` e ative o ambiente virtual novamente.

1.  **Prepare os áudios**:
    Coloque os arquivos `.webm` que deseja processar na pasta `testes/1_input`.
    *(Para teste rápido, coloque apenas 1 arquivo)*.

2.  **Rode o script apontando para o servidor local**:
    O script padrão tenta conectar em `localhost:8765`. Se você mudou a porta para 8766 (como sugerido acima), use a variável de ambiente `BALTO_SERVER_URL`.

    ```bash
    BALTO_SERVER_URL=http://localhost:8766 python3 testes/generate_spreadsheet_report.py
    ```

## 6. Resultados

O script irá:
1.  Enviar o áudio para o servidor local (`/api/test/segmentar`).
2.  O servidor limpará o áudio e fará a detecção de voz (VAD).
3.  O servidor devolverá os segmentos.
4.  O script enviará cada segmento de volta para transcrição (`/api/test/transcrever`).
5.  Os resultados serão salvos em:
    *   `testes/planilhas/Relatorio_Originais.xlsx`
    *   `testes/planilhas/Relatorio_Segmentos.xlsx`

## Solução de Problemas Comuns

*   **Erro "Address already in use"**: A porta 8765 ou 8766 está ocupada. Use `fuser -k 8766/tcp` para matar o processo ou mude a porta no comando `PORT=...`.
*   **Erro de FFmpeg**: Se aparecer erro de decodificação, verifique se instalou `imageio-ffmpeg`.
*   **Erro 404**: Verifique se a URL no comando do cliente bate com a porta que o servidor iniciou.
