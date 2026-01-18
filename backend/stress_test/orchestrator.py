
import os
import sys
import threading
import time
import asyncio
import aiohttp
import subprocess
import statistics
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import requests
from datetime import datetime

# Add parent dir to path to find app modules if needed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- Configuration ---
# Load from Environment (Passed via docker-compose)
from dotenv import load_dotenv
load_dotenv()

STRESS_DURATION_MINUTES = int(os.environ.get("STRESS_DURATION_MINUTES", 60))
STRESS_CLIENTS = int(os.environ.get("STRESS_CLIENTS", 5))
AUDIO_FILE = os.environ.get("STRESS_AUDIO_FILE")
REPORT_EMAIL = os.environ.get("STRESS_REPORT_EMAIL")

# If running inside docker stack, 'server' is the hostname.
# Fallback to localhost if running manually.
SERVER_HOST = os.environ.get("SERVER_HOST", "server") 
# WS_URL = f"ws://{SERVER_HOST}:8765/ws"
WS_URL = os.environ.get("STRESS_TARGET_URL", "wss://balto.pbpmdev.com/ws")

# Metrics & Logs
cpu_ram_log = []
error_log = []
active_clients = 0
impostor_stats = {"requests": 0}

print(f"--- WAR MODE ORCHESTRATOR ---")
print(f"Clients: {STRESS_CLIENTS}")
print(f"Duration: {STRESS_DURATION_MINUTES} minutes")
print(f"Audio: {AUDIO_FILE}")
print(f"Email: {REPORT_EMAIL}")
print(f"Target: {WS_URL}")

# --- Client Robot ---
# --- Client Robot ---
# --- Identity Management ---
IDENTITY_FILE = "stress_identity.json"

def get_or_create_identity_code():
    """
    Tenta carregar identidade (user_codigo) do arquivo.
    Se não existir, cria um NOVO cliente na API e salva no arquivo.
    Isso garante que todos os testes rodem sob o mesmo 'cliente pai',
    a menos que o arquivo seja deletado.
    """
    # 1. Tenta carregar
    if os.path.exists(IDENTITY_FILE):
        try:
            with open(IDENTITY_FILE, "r") as f:
                data = json.load(f)
                code = data.get("user_codigo")
                if code:
                    print(f"[Identity] Identidade carregada: {code}")
                    return code
        except Exception as e:
            print(f"[Identity] Erro ao ler arquivo: {e}")

    # 2. Se falhou, Cria Novo via API
    # Deriva URL HTTP
    base_url = WS_URL.replace("/ws", "").replace("ws://", "http://").replace("wss://", "https://")
    
    # Email único para garantir criação
    email = f"war_master_{int(time.time())}@stress.com"
    razao = "War Stress Corp"
    
    print(f"[Identity] Criando NOVA identidade master em {base_url} ({email})...")
    
    try:
        res = requests.post(f"{base_url}/cadastro/cliente", json={
            "email": email,
            "razao_social": razao,
            "telefone": "00000000"
        }, timeout=10)
        
        if res.status_code in [200, 201]:
            code = res.json().get("codigo")
            # Salva
            with open(IDENTITY_FILE, "w") as f:
                json.dump({"user_codigo": code, "email": email, "created_at": str(datetime.now())}, f)
            print(f"[Identity] Identidade criada e salva: {code}")
            return code
        else:
            print(f"[Identity] Falha API Cliente: {res.text}")
            return None
    except Exception as e:
        print(f"[Identity] Erro Conexão: {e}")
        return None

def register_balcao(user_codigo, client_id):
    """
    Registra um balcão para o código de usuário fornecido.
    Retorna a API Key.
    """
    base_url = WS_URL.replace("/ws", "").replace("ws://", "http://").replace("wss://", "https://")
    balcao_name = f"Balcao Robot {client_id}"
    
    try:
        res = requests.post(f"{base_url}/cadastro/balcao", json={
            "nome_balcao": balcao_name,
            "user_codigo": user_codigo
        }, timeout=10)
        
        if res.status_code in [200, 201]:
            return res.json().get("api_key")
        else:
            print(f"[Robot-{client_id}] Erro cadastro balcao: {res.text}")
            return None
    except Exception as e:
        print(f"[Robot-{client_id}] Erro Conexão Balcao: {e}")
        return None

async def client_robot(client_id, user_codigo):
    global active_clients
    active_clients += 1
    
    if not user_codigo:
        print(f"[Robot-{client_id}] Sem user_codigo. Abortando.")
        active_clients -= 1
        return

    print(f"[Robot-{client_id}] Starting (User: {user_codigo})...")
    
    # Registra Balcão deste robô
    api_key = None
    for _ in range(3):
        api_key = register_balcao(user_codigo, client_id)
        if api_key: break
        time.sleep(1)
        
    if not api_key:
        print(f"[Robot-{client_id}] Abortando: Falha ao obter API Key do balcão.")
        active_clients -= 1
        return

    # Loop for Duration
    end_time = time.time() + (STRESS_DURATION_MINUTES * 60)
    
    while time.time() < end_time:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(WS_URL) as ws:
                    await ws.send_json({"api_key": api_key})
                    
                    if not os.path.exists(AUDIO_FILE):
                         print(f"[Robot-{client_id}] Audio file missing: {AUDIO_FILE}")
                         break

                    with open(AUDIO_FILE, "rb") as f:
                        data = f.read(4096)
                        while data:
                            await ws.send_bytes(data)
                            await asyncio.sleep(0.1) 
                            data = f.read(4096)
                            
                            if time.time() > end_time: break
                    
                    try:
                        while True:
                            msg = await ws.receive_json(timeout=5.0)
                    except asyncio.TimeoutError:
                        pass
                        
        except Exception as e:
            error_log.append(f"[Robot-{client_id}] {datetime.now()}: {e}")
            await asyncio.sleep(5) 

    print(f"[Robot-{client_id}] Finished.")
    active_clients -= 1

def run_robot(cid, user_codigo):
    asyncio.run(client_robot(cid, user_codigo))

# --- Monitors --- (Logic moved to new hardware_watchdog definition above)

def log_janitor():
    print("[Janitor] Started.")
    end_time = time.time() + (STRESS_DURATION_MINUTES * 60) + 60
    while time.time() < end_time:
        time.sleep(300) # 5 mins
        # Filtering logs requires python docker sdk too
        pass

# --- Grand Finale ---

def parse_size(size_str):
    # Quick dirty parser for "12.5MiB", "1.2GiB"
    units = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}
    size_str = size_str.strip()
    for unit, multiplier in units.items():
        if size_str.endswith(unit):
            try:
                num = float(size_str[:-len(unit)].strip())
                return num * multiplier
            except:
                pass
    # Fallback try parsing just number
    try:
        return float(size_str)
    except:
        return 0.0

def generate_report():
    import openai
    
    print("[Finale] Generating Analytics...")
    
    # Process Metrics
    total_cpu = 0.0
    total_mem_bytes = 0.0
    samples = 0
    
    # Log format: "HH:MM:SS | Name,CPUPerc,MemUsage"
    # Example: "10:00:00 | CPU_Abstract: 0.5% | Mem: 120MiB" -- WAIT, looking at hardware_watchdog above:
    # It appends: f"{timestamp} | CPU_Abstract: {cpu} | Mem: {mem}"
    # cpu is from stats['cpu_stats']['cpu_usage']['total_usage'] which is raw nanoseconds in Docker API usually?
    # Wait, in the updated hardware_watchdog I used docker client stats(stream=False).
    # 'cpu_stats'['cpu_usage']['total_usage'] is cumulative counter in nanoseconds.
    # To get % usage we need delta between two samples. 
    # BUT, `docker stats` cli returns percentage. The python lib `stats` returns raw json.
    # Calculating CPU % from raw stats is complex (delta_cpu / delta_system * num_cpus).
    
    # HACK: Let's assume the user meant the previous visual log check or just wants the final numbers.
    # If I want true Avg CPU, I need to calculate it properly or switch back to CLI parsing if installed.
    # The previous `hardware_watchdog` implementation (which I replaced in step 136) was trying to be clever.
    # Let's check `hardware_watchdog` again. 
    # It does: `cpu = stats['cpu_stats']['cpu_usage']['total_usage']` -> This is a counter, not %.
    # It does: `mem = stats['memory_stats']['usage']` -> This is bytes.
    
    # I should change hardware_watchdog to calculate proper percentage or just use raw bytes for memory.
    # For CPU, getting a meaningful "Avg CPU %" from raw cumulative counter requires deltas.
    # SIMPLIFICATION: I will use the raw memory bytes (convert to MB) and for CPU... 
    # I will try to rely on the fact that I want "Average". 
    # Total CPU used (in seconds) / Duration (seconds) * 100 / Cores ?
    # Better: Re-implement hardware_watchdog to use the CLI if available or use a library that gives %.
    # Or just calc memory for now and show raw CPU counter difference?
    # User asked for "Uso de CPU". 
    # Let's fix hardware_watchdog to run `docker stats` via subprocess since the container has docker CLI ?
    # Wait, the container `server` image is based on python-slim. It does NOT have docker CLI installed unless added.
    # check Dockerfile... Step 155 output: "RUN apt-get update && apt-get install -y libsndfile1..." 
    # It does not seem to install docker-cli.
    # So `subprocess.run(["docker", ...])` will fail inside `stress-orchestrator`.
    # Using python `docker` lib is correct.
    # To get CPU %, we need two samples.
    
    # Refactoring hardware_watchdog loop in this same replacement to get proper metrics? 
    # Yes, let's fix the data collection first in `hardware_watchdog` then report it.
    pass

def hardware_watchdog():
    print("[Watchdog] Started.")
    import docker
    client = docker.from_env()
    
    time.sleep(10)
    end_time = time.time() + (STRESS_DURATION_MINUTES * 60) + 60
    
    # For CPU calculation
    prev_cpu = 0
    prev_system = 0
    
    while time.time() < end_time:
        try:
             # Use the implicit container name or allow override
            target_container = os.environ.get("STRESS_CONTAINER_NAME", "balto-server-prod")
            stats = client.containers.get(target_container).stats(stream=False)
            
            # MEMORY
            mem_usage = stats['memory_stats'].get('usage', 0)
            mem_limit = stats['memory_stats'].get('limit', 1)
            mem_percent = (mem_usage / mem_limit) * 100
            
            # CPU
            cpu_delta = 0.0
            system_delta = 0.0
            cpu_percent = 0.0
            
            cpu_total = stats['cpu_stats']['cpu_usage']['total_usage']
            system_usage = stats['cpu_stats'].get('system_cpu_usage', 0)
            online_cpus = stats['cpu_stats'].get('online_cpus', 1) or len(stats['cpu_stats']['cpu_usage'].get('percpu_usage', [1]))
            
            if prev_cpu > 0 and prev_system > 0:
                cpu_delta = float(cpu_total - prev_cpu)
                system_delta = float(system_usage - prev_system)
                if system_delta > 0.0:
                    cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0
            
            prev_cpu = cpu_total
            prev_system = system_usage
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            # Store structured data: "TIME | CPU_PERC | MEM_BYTES"
            cpu_ram_log.append(f"{timestamp}|{cpu_percent:.2f}|{mem_usage}")
            
        except Exception as e:
            # cpu_ram_log.append(f"Error|0|0")
            print(f"Watchdog error: {e}")
            pass
        time.sleep(15) # Sample every 15s

def generate_report():
    import openai
    import statistics
    
    print("[Finale] Generating Analytics...")
    
    cpu_samples = []
    mem_samples = []
    
    for entry in cpu_ram_log:
        try:
            parts = entry.split('|')
            if len(parts) == 3:
                cpu_samples.append(float(parts[1]))
                mem_samples.append(float(parts[2]))
        except:
            pass
            
    avg_cpu = statistics.mean(cpu_samples) if cpu_samples else 0.0
    avg_mem_mb = (statistics.mean(mem_samples) / (1024*1024)) if mem_samples else 0.0
    max_mem_mb = (max(mem_samples) / (1024*1024)) if mem_samples else 0.0
    
    # Per Client Normalization
    clients = max(1, STRESS_CLIENTS)
    avg_cpu_per_client = avg_cpu / clients
    avg_mem_per_client = avg_mem_mb / clients
    
    summary = f"""
=========================================
      BALTO WAR MODE REPORT
=========================================
Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Duration: {STRESS_DURATION_MINUTES} minutes
Concurrent Clients: {STRESS_CLIENTS}
Audio Source: {AUDIO_FILE}

--- SYSTEM METRICS (CONTAINER: balto-server-prod) ---
Samples Collected: {len(cpu_samples)}

[CPU USAGE]
Average Total: {avg_cpu:.2f}%
Average Per Client: {avg_cpu_per_client:.2f}%

[MEMORY RAM USAGE]
Average Total: {avg_mem_mb:.2f} MB
Max Peak: {max_mem_mb:.2f} MB
Average Per Client: {avg_mem_per_client:.2f} MB

--- STABILITY ---
Total App Errors Logged: {len(error_log)}
Sample Errors:
{chr(10).join(error_log[:10])}
"""
    
    # AI Analysis
    real_key = os.environ.get("OPENAI_API_KEY")
    if real_key and "placeholder" in real_key: real_key = None

    if real_key:
        client = openai.OpenAI(api_key=real_key) 
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "DevOps Engineer"},
                    {"role": "user", "content": f"Analyze:\n{summary}"}
                ]
            )
            analysis = response.choices[0].message.content
        except Exception as e:
            analysis = f"AI Error: {e}"
    else:
        analysis = "AI Analysis Skipped (No valid Key)"

    full_report = f"{summary}\n\n--- AI ANALYSIS ---\n{analysis}"
    
    # Save Locally with Timestamp
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_filename = f"stress_test_{timestamp_str}.txt"
    report_path = report_filename
    
    try:
        with open(report_path, "w") as f:
            f.write(full_report)
        print(f"[Orchestrator] Report saved to {report_path}")
    except Exception as e:
        print(f"[Orchestrator] Failed to save report locally: {e}") 


# --- Main ---
if __name__ == "__main__":
    # Delay to ensure server is up
    print("Waiting 10s for server startup...")
    time.sleep(10)

    # Start Monitors
    threading.Thread(target=hardware_watchdog, daemon=True).start()
    
    # 1. Obtain Shared Identity (One Client to rule them all)
    MASTER_CODE = get_or_create_identity_code()
    if not MASTER_CODE:
        print("[Fatal] Não foi possível obter o código do cliente mestre. Abortando.")
        sys.exit(1)
    
    # Start Clients
    threads = []
    
    try:
        for i in range(STRESS_CLIENTS):
            # Passa o MASTER_CODE para todos
            t = threading.Thread(target=run_robot, args=(i, MASTER_CODE))
            t.start()
            threads.append(t)
        
        # Wait for completion, but allow KeyboardInterrupt
        for t in threads:
            while t.is_alive():
                t.join(timeout=1.0)
                
    except KeyboardInterrupt:
        print("\n[Orchestrator] Interrupção detectada! Finalizando graciosamente...")
        # (Opcional: Poderíamos setar uma flag global para parar os threads mais rápido, 
        # mas elas vão morrer quando o processo principal sair ou podemos deixar assim)
        
    finally:
        generate_report()
        print("[Orchestrator] Fim.")

