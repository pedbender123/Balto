import os
import sys
import threading
import time
import asyncio
import aiohttp
import statistics
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load Env
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Balto War Mode Orchestrator")

# --- Configuration & State ---
class GlobalState:
    is_running = False
    stop_event = threading.Event()
    active_clients = 0
    cpu_ram_log = []
    error_log = []
    start_time = None
    duration_minutes = 0
    report_path = None

state = GlobalState()

# Defaults
DEFAULT_DURATION = int(os.environ.get("STRESS_DURATION_MINUTES", 60))
DEFAULT_CLIENTS = int(os.environ.get("STRESS_CLIENTS", 5))
AUDIO_FILE = os.environ.get("STRESS_AUDIO_FILE", "/backend/test_audio.webm")
SERVER_HOST = os.environ.get("SERVER_HOST", "server")
WS_URL = f"ws://{SERVER_HOST}:8765/ws"
SHADOW_API_URL = "http://shadow-api:8000"

# --- Pydantic Models ---
class StartRequest(BaseModel):
    clients: int = DEFAULT_CLIENTS
    duration_minutes: int = DEFAULT_DURATION
    audio_file: Optional[str] = AUDIO_FILE

# --- Logic: Watchdog ---
def hardware_watchdog():
    print("[Watchdog] Started.")
    import docker
    client = docker.from_env()
    
    prev_cpu = 0
    prev_system = 0
    
    while not state.stop_event.is_set():
        try:
            # Check timeout
            if state.start_time and (time.time() - state.start_time) > (state.duration_minutes * 60):
                print("[Watchdog] Time limit reached. Stopping...")
                stop_test()
                break

            stats = client.containers.get(SERVER_HOST.replace("server", "balto-server-prod")).stats(stream=False)
            
            # MEMORY
            mem_usage = stats['memory_stats'].get('usage', 0)
            mem_limit = stats['memory_stats'].get('limit', 1)
            
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
            state.cpu_ram_log.append(f"{timestamp}|{cpu_percent:.2f}|{mem_usage}")
            
        except Exception as e:
            print(f"[Watchdog] Error: {e}")
            
        time.sleep(5)

# --- Logic: Clients ---
async def client_robot(client_id, api_key):
    state.active_clients += 1
    print(f"[Robot-{client_id}] Starting...")
    
    end_time = time.time() + (state.duration_minutes * 60)
    
    while not state.stop_event.is_set() and time.time() < end_time:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(WS_URL) as ws:
                    await ws.send_json({"api_key": api_key})
                    
                    if not os.path.exists(AUDIO_FILE):
                         print(f"[Robot-{client_id}] Audio missing")
                         break

                    with open(AUDIO_FILE, "rb") as f:
                        data = f.read(4096)
                        while data and not state.stop_event.is_set():
                            await ws.send_bytes(data)
                            await asyncio.sleep(0.1) 
                            data = f.read(4096)
                    
                    # Wait for responses or timeout
                    try:
                        while not state.stop_event.is_set():
                            await ws.receive_json(timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
                        
        except Exception as e:
            if not state.stop_event.is_set():
                state.error_log.append(f"[Robot-{client_id}] {e}")
                await asyncio.sleep(5) 
    
    state.active_clients -= 1

def run_robot_thread(cid, api_key):
    asyncio.run(client_robot(cid, api_key))

def ensure_user_balcao(client_id):
    # Idempotent DB Setup
    from app import db
    try:
        email = f"war_robot_{client_id}@test.com"
        balcao_name = f"Balcao War {client_id}"
        
        # 1. Get or Create User
        uid = db.get_user_by_email(email)
        if not uid:
            user_code = db.create_client(email, "War Corp", "00000")
            uid = db.get_user_by_code(user_code)
        
        # 2. Get or Create Balcao
        existing_balcao = db.get_balcao_by_name(uid, balcao_name)
        if existing_balcao:
            return existing_balcao[1]
        else:
            _, api_key = db.create_balcao(uid, balcao_name)
            return api_key
    except Exception as e:
        print(f"DB Error for robot {client_id}: {e}")
        return None

def start_stress_test(clients: int, duration: int):
    # 0. Reset Shadow API
    try:
        import requests
        requests.post(f"{SHADOW_API_URL}/reset")
    except:
        print("Warning: Could not reset Shadow API")

    # 1. Reset State
    state.is_running = True
    state.stop_event.clear()
    state.cpu_ram_log = []
    state.error_log = []
    state.start_time = time.time()
    state.duration_minutes = duration
    state.report_path = None
    
    # 2. Start Watchdog
    threading.Thread(target=hardware_watchdog, daemon=True).start()
    
    # 3. Start Clients
    for i in range(clients):
        # Setup DB first (blocking is fine here to avoid race conditions)
        api_key = ensure_user_balcao(i)
        if api_key:
            threading.Thread(target=run_robot_thread, args=(i, api_key), daemon=True).start()
        else:
            state.error_log.append(f"[Setup] Failed to create credentials for Robot {i}")

def stop_test():
    state.stop_event.set()
    state.is_running = False
    generate_final_report()

def generate_final_report():
    print("[Finale] Generating Report...")
    
    cpu_samples = []
    mem_samples = []
    for entry in state.cpu_ram_log:
        try:
            parts = entry.split('|')
            if len(parts) == 3:
                cpu_samples.append(float(parts[1]))
                mem_samples.append(float(parts[2]))
        except: pass

    avg_cpu = statistics.mean(cpu_samples) if cpu_samples else 0.0
    avg_mem_mb = (statistics.mean(mem_samples) / (1024*1024)) if mem_samples else 0.0
    
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_filename = f"stress_test_ONDEMAND_{timestamp_str}.txt"
    report_path = f"/backend/{report_filename}"
    state.report_path = report_path
    
    with open(report_path, "w") as f:
        f.write(f"WAR MODE REPORT (On-Demand)\nDate: {timestamp_str}\n")
        f.write(f"Duration: {state.duration_minutes}m\nClients: {state.active_clients}\n")
        f.write(f"Avg CPU: {avg_cpu:.2f}%\nAvg Mem: {avg_mem_mb:.2f}MB\n")
        f.write(f"Errors: {len(state.error_log)}\n")

# --- API Endpoints ---
@app.get("/")
def home():
    return {"name": "Balto War Mode Orchestrator", "status": "Ready" if not state.is_running else "Running"}

@app.post("/start")
def start_endpoint(req: StartRequest, background_tasks: BackgroundTasks):
    if state.is_running:
        raise HTTPException(status_code=400, detail="Test already running")
    
    background_tasks.add_task(start_stress_test, req.clients, req.duration_minutes)
    return {"message": "War Mode Initiated", "config": req.dict()}

@app.post("/stop")
def stop_endpoint():
    if not state.is_running:
        return {"message": "Not running"}
    stop_test()
    return {"message": "Stopping test..."}

@app.get("/status")
def status_endpoint():
    return {
        "running": state.is_running,
        "active_clients": state.active_clients,
        "elapsed": round(time.time() - state.start_time) if state.start_time and state.is_running else 0,
        "samples_collected": len(state.cpu_ram_log),
        "errors": len(state.error_log),
        "last_report": state.report_path
    }
