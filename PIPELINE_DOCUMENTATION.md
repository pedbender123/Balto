# Documentação Técnica do Pipeline

## 1. Visão Geral do Pipeline
O pipeline atual foi projetado para processar, analisar e gerenciar dados de áudio e outros artefatos relacionados. Ele é composto por diversos scripts e serviços que trabalham em conjunto para realizar tarefas como:

- Processamento de áudio.
- Integração com APIs externas.
- Geração de relatórios e logs.
- Execução de testes de estresse e diagnósticos.

O pipeline é modular e pode ser executado tanto localmente quanto em ambientes de produção.

---

## 2. Componentes Principais

### Diretórios
- **`audio_dumps/`**: Contém arquivos de áudio processados e exportados.
- **`audio_samples/`**: Repositório de amostras de áudio para benchmarks e testes de qualidade.
- **`backend/`**: Diretório principal do backend, contendo scripts, configurações e dependências.
- **`local_stress/`**: Scripts para execução de testes de estresse localmente.
- **`testes/`**: Scripts para testes de integração e validação de lógica de IA.

### Scripts Importantes
- **`fetch_vps_csvs.py`**: Responsável por buscar arquivos CSV de servidores VPS.
- **`fix_vps_branch.py`**: Corrige branches de VPS.
- **`vps_check.py`**: Realiza verificações em servidores VPS.
- **`backend/app/main.py`**: Ponto de entrada principal do backend.
- **`backend/stress_test/orchestrator.py`**: Orquestrador para testes de estresse.
- **`testes/verify_ai_logic.py`**: Valida a lógica de IA implementada.

---

## 3. Fluxo de Operações

1. **Entrada de Dados**:
   - Dados de áudio são carregados em `audio_dumps/` ou `audio_samples/`.
   - Arquivos CSV são buscados por `fetch_vps_csvs.py`.

2. **Processamento**:
   - O script `backend/app/audio_processor.py` realiza o processamento de áudio.
   - Ferramentas como `silero_vad.py` e `speaker_id.py` são usadas para detecção de voz e identificação de locutores.

3. **Integração**:
   - `backend/app/integration_client.py` gerencia a comunicação com APIs externas.

4. **Testes e Diagnósticos**:
   - Testes de estresse são executados com `backend/stress_test/orchestrator.py`.
   - Diagnósticos são realizados por `backend/app/diagnostics.py`.

5. **Geração de Relatórios**:
   - Relatórios são gerados por scripts como `testes/generate_spreadsheet_report.py`.

---

## 4. Vertentes do Pipeline

### 4.1. Processamento de Áudio
- Scripts principais: `audio_processor.py`, `silero_vad.py`, `speaker_id.py`.
- Funções:
  - Detecção de voz.
  - Identificação de locutores.
  - Transcrição de áudio.

### 4.2. Integração com APIs
- Scripts principais: `integration_client.py`.
- Funções:
  - Comunicação com serviços externos.
  - Envio e recebimento de dados.

### 4.3. Testes de Estresse
- Scripts principais: `orchestrator.py`, `shadow_api.py`.
- Funções:
  - Simulação de cargas altas no sistema.
  - Identificação de gargalos.

### 4.4. Geração de Relatórios
- Scripts principais: `generate_spreadsheet_report.py`.
- Funções:
  - Criação de planilhas detalhadas.
  - Análise de resultados.

---

## 5. Operações em Segundo Plano

- **Testes de Estresse**:
  - Executados em segundo plano para simular cenários de alta carga.
  - Logs gerados em `backend/server_log.txt`.

- **Processamento de Áudio**:
  - Operações assíncronas para otimizar o desempenho.

- **Integração com APIs**:
  - Requisições e respostas gerenciadas em segundo plano.

---

## 6. Configurações e Dependências

### Arquivos de Configuração
- **`.env`**: Contém variáveis de ambiente para configuração do sistema.
- **`rclone.conf`**: Configuração para sincronização de arquivos.

### Dependências
- Listadas em:
  - `backend/requirements.txt`
  - `backend/requirements-stress.txt`

Para instalar as dependências, execute:
```bash
pip install -r backend/requirements.txt
pip install -r backend/requirements-stress.txt
```

---

## 7. Execução Local e em Produção

### Execução Local
1. Configure o ambiente:
   - Edite o arquivo `.env` com as variáveis necessárias.
2. Inicie o backend:
   ```bash
   python backend/app/main.py
   ```
3. Execute testes de estresse:
   ```bash
   bash backend/run_stress_local.sh
   ```

### Execução em Produção
1. Configure o Docker:
   - Utilize o `Dockerfile` localizado em `backend/`.
2. Suba os containers:
   ```bash
   docker-compose up --build
   ```

---

Esta documentação fornece uma visão detalhada do pipeline, suas vertentes e operações. Para dúvidas ou melhorias, consulte o arquivo `README.md` ou entre em contato com o time responsável.