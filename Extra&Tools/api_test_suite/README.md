# Protocolo de Testes de API Balto

Este diretório contém uma suíte de testes automatizados para validar a integridade da API REST e do fluxo WebSocket do Balto Server.

## Estrutura

- `run_protocol.py`: Script mestre que provisiona assets de teste e executa as suítes.
- `test_rest_api.py`: Testa endpoints de cadastro, login admin e análise de texto via HTTP.
- `test_websocket.py`: Simula um balcão real, enviando stream de áudio e aguardando recomendações.

## Como Executar

Recomenda-se o uso do ambiente virtual `stress_venv` já existente no projeto:

```bash
# Navegue até esta pasta
cd "Extra&Tools/api_test_suite"

# Execute o protocolo completo
../../stress_venv/bin/python3 run_protocol.py
```

## Requisitos

- `requests`
- `aiohttp`

(Instalados automaticamente no `stress_venv` durante a configuração do protocolo).

## Diagnóstico de Problemas Comuns

- **Connection Refused**: Certifique-se de que o container `balto-server-prod` está rodando (`docker ps`).
- **Timeout no WebSocket**: Verifique se o `MOCK_MODE` ou as chaves de API estão configuradas corretamente no `.env`. Utilize `docker compose logs -f server` para ver o processamento em tempo real.
- **Permission Denied**: Corrigido no protocolo de testes para usar caminhos internos ao container (`/backend/...`).
