import docker
import requests
import os
import time
import threading
import logging
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- CONFIGURAÇÃO ---
# URL do Webhook (Padrão para o seu servidor)
WEBHOOK_URL = os.getenv('LOG_MONITOR_WEBHOOK_URL', 'http://api.pbpmdev.com/webhook')
# Chave da API (Obrigatória)
API_KEY = os.getenv('LOG_MONITOR_API_KEY')
# Nome do projeto (opcional, para filtrar logs apenas deste docker-compose)
PROJECT_NAME = os.getenv('COMPOSE_PROJECT_NAME') 
# Identificação deste container para não ler o próprio log (evita loop infinito)
MY_HOSTNAME = os.getenv('HOSTNAME', '')

# Setup basic print/logging
print(f"--- PREPARANDO LOG MONITOR ---")
if not API_KEY:
    print("FATAL: Variável LOG_MONITOR_API_KEY não definida. O monitor não pode iniciar.")
    # Não exit(1) direto, vamos deixar rodar com aviso ou esperar env
    # Mas o user pediu para avisar.

# --- PREPARAÇÃO DA CONEXÃO HTTP (Alta Performance) ---
# Usamos Session para reaproveitar conexões TCP e evitar overhead em cada log
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
session.mount('http://', HTTPAdapter(max_retries=retries))
session.headers.update({
    "x-api-key": API_KEY if API_KEY else "",
    "Content-Type": "application/json"
})

# Controle de containers já monitorados
monitored_containers = set()

def detect_log_level(log_line):
    """Detecta nível do log baseado em palavras-chave comuns."""
    line_upper = log_line.upper()
    if any(x in line_upper for x in ['ERROR', 'CRITICAL', 'EXCEPTION', 'FATAL', '❌']):
        return "ERROR"
    if any(x in line_upper for x in ['WARN', 'WARNING', '⚠️']):
        return "WARN"
    if 'DEBUG' in line_upper:
        return "DEBUG"
    return "INFO"

# Filtros de Log (ignorar logs irrelevantes para o monitor)
IGNORED_PATTERNS = [
    "[DB] Tentando registrar interação",
    "[DB] Interação registrada com sucesso",
    "[VAD] SEGMENT FINISHED",
    "MOCK VOICE: Sleeping",
    "Connection closed during Mock Latency",
    "[LogMonitor]", # Ignora logs do próprio monitor
]

def should_ignore(log_line):
    line_check = log_line.strip()
    for pattern in IGNORED_PATTERNS:
        if pattern in line_check:
            return True
    return False

def send_log_batch(container_name, log_line):
    """Envia o log formatado para a API."""
    if not log_line.strip():
        return
        
    if should_ignore(log_line):
        return
    
    # Se não temos API Key, só imprime no stdout (debug local)
    if not API_KEY:
        return

    payload = {
        "container": container_name,
        "message": log_line.strip(),
        "created_at": datetime.utcnow().isoformat()
    }
    try:
        # Timeout curto para não travar a thread de leitura
        resp = session.post(WEBHOOK_URL, json=payload, timeout=2)
        if resp.status_code >= 400:
            print(f"[LogMonitor] Erro API {resp.status_code}: {resp.text[:50]}")
    except requests.exceptions.RequestException as e:
        # Silencia erros de conexão momentâneos para não sujar o stdout do próprio monitor
        pass

def follow_container_logs(container):
    """Thread dedicada para ler logs de um container específico."""
    print(f"[LogMonitor] Conectado a: {container.name}")
    try:
        # tail=0 pega apenas logs novos a partir de agora
        # stream=True mantém o socket aberto
        for line in container.logs(stream=True, follow=True, tail=0):
            decoded_line = line.decode('utf-8', errors='replace')
            send_log_batch(container.name, decoded_line)
    except Exception as e:
        print(f"[LogMonitor] Desconectado de {container.name} ({e})")
    finally:
        # Se o container morrer ou a conexão cair, removemos da lista para tentar reconectar depois
        monitored_containers.discard(container.id)

def main_loop():
    global PROJECT_NAME
    print(f"--- INICIANDO MONITOR DE LOGS ---")
    print(f"Alvo: {WEBHOOK_URL}")
    print(f"Projeto: {PROJECT_NAME if PROJECT_NAME else 'Todos (Sem filtro)'}")
    
    try:
        client = docker.from_env()
        
        # Auto-detect Project Name from own labels if not provided
        if not PROJECT_NAME and MY_HOSTNAME:
            try:
                # MY_HOSTNAME is usually the container ID (short) in Docker
                me = client.containers.get(MY_HOSTNAME)
                PROJECT_NAME = me.labels.get('com.docker.compose.project')
                if PROJECT_NAME:
                    print(f"[LogMonitor] Auto-detected Project Filter: {PROJECT_NAME}")
            except Exception as e:
                print(f"[LogMonitor] Warning: Could not auto-detect project name: {e}")
                
    except Exception as e:
        print(f"FATAL: Não foi possível conectar ao Docker Socket. {e}")
        return

    while True:
        try:
            # Lista apenas containers rodando
            active_containers = client.containers.list()
            for container in active_containers:
                # 1. Ignora o próprio monitor (evita loop infinito de logs)
                if container.id.startswith(MY_HOSTNAME) or container.name == MY_HOSTNAME:
                    continue
                
                # 2. Se já estamos monitorando, pula
                if container.id in monitored_containers:
                    continue

                # 3. (Opcional) Filtra pelo projeto do docker-compose
                if PROJECT_NAME:
                    container_project = container.labels.get('com.docker.compose.project')
                    # Se o container não tiver label ou for diferente, ignora
                    if container_project != PROJECT_NAME:
                        continue
                
                # Inicia monitoramento em thread separada
                monitored_containers.add(container.id)
                t = threading.Thread(target=follow_container_logs, args=(container,))
                t.daemon = True
                t.start()
            
            # Verifica novos containers a cada 5 segundos
            time.sleep(5)
        except Exception as e:
            print(f"[LogMonitor] Erro no loop principal: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main_loop()
