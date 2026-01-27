
import asyncio
import aiohttp
import requests
import os
import sys
import time
import uuid
import random
from dotenv import load_dotenv
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Load config from local .env
load_dotenv(".env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SERVER_URL = os.getenv("STRESS_SERVER_URL", "http://localhost:8765")
WS_URL = os.getenv("STRESS_WS_URL", "ws://localhost:8765/ws")
MODE = os.getenv("STRESS_MODE", "FIXED").upper()
AUDIO_FILE = os.getenv("STRESS_AUDIO_FILE", "test_audio.wav")

# Fixed Mode
FIXED_CLIENTS = int(os.getenv("STRESS_FIXED_CLIENTS", 5))
DURATION_HOURS = float(os.getenv("STRESS_DURATION_HOURS", 1.0))

# Ramp Mode
RAMP_STEP = int(os.getenv("STRESS_RAMP_STEP", 1))
RAMP_INTERVAL = int(os.getenv("STRESS_RAMP_INTERVAL", 60))

active_clients = 0
stop_event = asyncio.Event()
created_balcoes = [] # list of (idx, balcao_id)

def get_api_key(idx):
    """
    Cadastra um usuário e balcão temporários para o teste.
    """
    email = f"stress_{uuid.uuid4().hex[:8]}@test.com"
    try:
        # 1. Create User
        res = requests.post(f"{SERVER_URL}/cadastro/cliente", json={
            "email": email,
            "razao_social": f"Stress Corp {idx}",
            "telefone": "00000000"
        }, timeout=30)
        
        if res.status_code != 201:
            print(f"[Setup] Erro ao criar cliente: {res.text}")
            return None
            
        codigo = res.json().get("codigo")
        
        # 2. Create Balcao
        res = requests.post(f"{SERVER_URL}/cadastro/balcao", json={
            "nome_balcao": f"Balcao Stress {idx}",
            "user_codigo": codigo
        }, timeout=30)
        
        if res.status_code != 200:
             print(f"[Setup] Erro ao criar balcao: {res.text}")
             return None
             
        data = res.json()
        b_id = data.get("balcao_id")
        created_balcoes.append({"idx": idx, "id": b_id})
        
        return data.get("api_key")
        
    except Exception as e:
        print(f"[Setup] Erro de Conexão: {e}")
        return None

async def run_client(idx, api_key):
    global active_clients
    active_clients += 1
    print(f"[Client-{idx}] Iniciando com Key={api_key[:8]}...")
    
    if not os.path.exists(AUDIO_FILE):
        print(f"[Client-{idx}] ERRO: Arquivo de audio '{AUDIO_FILE}' nao encontrado.")
        active_clients -= 1
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(WS_URL) as ws:
                # Auth
                await ws.send_json({"api_key": api_key})
                
                # Audio Loop
                with open(AUDIO_FILE, "rb") as f:
                    audio_data = f.read() # Load all to memory for simplicity or chunk stream
                
                # We need to chunk it properly to simulate real-time
                chunk_size = 4096
                idx_ptr = 0
                
                while not stop_event.is_set():
                    if idx_ptr >= len(audio_data):
                        idx_ptr = 0 # Loop
                        await asyncio.sleep(1.0) # Pause between loops
                        
                    chunk = audio_data[idx_ptr:idx_ptr+chunk_size]
                    await ws.send_bytes(chunk)
                    idx_ptr += chunk_size
                    
                    # Simulate ~realtime (chunk_size / (16000*2) sec)
                    # 4096 bytes / 32000 bytes/s ~= 0.128s
                    await asyncio.sleep(0.12)
                    
                    # Drain messages
                    try:
                        while not ws.closed:
                            msg = await ws.receive_json(timeout=0.01)
                            # print(print(f"[Client-{idx}] Recv: {msg.get('comando')}"))
                    except asyncio.TimeoutError:
                        pass
                    except Exception as e:
                        # Se fechar, é erro crítico
                        break
                        
    except aiohttp.WSServerHandshakeError as e:
         if e.status == 4002:
             print(f"!!! LIMIT REACHED: Server rejected connection due to capacity (4002) !!!")
             stop_event.set()
         else:
             print(f"[Client-{idx}] Handshake Error: {e}")
    except Exception as e:
        print(f"[Client-{idx}] Disconnected/Error: {e}")
        stop_event.set() # FAIL FAST as requested
        
    active_clients -= 1

async def main():
    print(f"=== BALTO STRESS CLIENT ===")
    print(f"Mode: {MODE}")
    print(f"Server: {SERVER_URL}")
    
    if MODE == "FIXED":
        print(f"Target: {FIXED_CLIENTS} clients for {DURATION_HOURS} hours.")
        
        tasks = []
        for i in range(FIXED_CLIENTS):
            key = await asyncio.to_thread(get_api_key, i)
            if key:
                tasks.append(asyncio.create_task(run_client(i, key)))
            else:
                print(f"Falha ao criar credenciais para {i}")
        
        end_time = time.time() + (DURATION_HOURS * 3600)
        while time.time() < end_time and not stop_event.is_set():
            await asyncio.sleep(1)
            print(f"Active: {active_clients} | Time remaining: {int(end_time - time.time())}s", end='\r')
            
        stop_event.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        
    elif MODE == "RAMP":
        start_count = int(os.environ.get("STRESS_RAMP_START", 0))
        print(f"Discovery Mode: Start {start_count}, +{RAMP_STEP} clients every {RAMP_INTERVAL}s")
        
        tasks = []
        client_count = 0
        
        # Initial Burst
        if start_count > 0:
             print(f"Adding initial burst of {start_count} clients (Parallel Setup)...")
             
             # Create tasks for all API keys first (Parallel requests)
             # Use semaphores? No, just gather for now.
             setup_tasks = [asyncio.to_thread(get_api_key, i) for i in range(start_count)]
             keys = await asyncio.gather(*setup_tasks)
             
             for i, key in enumerate(keys):
                if key:
                    tasks.append(asyncio.create_task(run_client(i, key)))
                    client_count += 1
                if i % 20 == 0: await asyncio.sleep(0.1) # Batch join
             
             print(f"Burst setup complete. {client_count} clients active.") 
        
        while not stop_event.is_set():
            # Add batch
            for _ in range(RAMP_STEP):
                key = await asyncio.to_thread(get_api_key, client_count)
                if key:
                    tasks.append(asyncio.create_task(run_client(client_count, key)))
                    client_count += 1
                await asyncio.sleep(0.5) # stagger slightly
            
            print(f"Clients: {client_count} | Waiting for capacity check...")
            
            # Wait interval or until stop
            for _ in range(RAMP_INTERVAL):
                if stop_event.is_set(): break
                await asyncio.sleep(1)
                
        print(f"\nTest Ended. Max Clients Achieved: {active_clients}")
        # Cancel all
        for t in tasks: t.cancel()
        
    print("\n=== Generating Report ===")
    await generate_report()

async def generate_report():
    if not created_balcoes:
        print("No balcoes created. Skipping report.")
        return

    print(f"Fetching metrics for {len(created_balcoes)} balcoes...")
    
    all_metrics = []
    
    async with aiohttp.ClientSession() as session:
        for b in created_balcoes:
            try:
                async with session.get(f"{SERVER_URL}/api/data/balcao/{b['id']}/metricas") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        interactions = data.get("interacoes", [])
                        if interactions:
                            all_metrics.extend(interactions)
            except Exception as e:
                print(f"Failed to fetch {b['id']}: {e}")
                
    if not all_metrics:
        print("No interactions found.")
        return
        
    # Summary Stats
    total_inter = len(all_metrics)
    avg_cpu = sum(m.get('cpu_usage_percent', 0) or 0 for m in all_metrics) / total_inter
    avg_ram = sum(m.get('ram_usage_mb', 0) or 0 for m in all_metrics) / total_inter
    
    # Calculate Latency Stats if timestamps present
    latencies = []
    for m in all_metrics:
        ts_rcv = m.get('ts_audio_received')
        ts_sent = m.get('ts_client_sent')
        if ts_rcv and ts_sent:
            try:
                t1 = datetime.fromisoformat(ts_rcv)
                t2 = datetime.fromisoformat(ts_sent)
                latencies.append((t2 - t1).total_seconds())
            except: pass
            
    avg_lat = sum(latencies)/len(latencies) if latencies else 0.0
    
    summary_text = f"""
    Stress Test Report
    ------------------
    Total Balcoes: {len(created_balcoes)}
    Total Interactions: {total_inter}
    Avg Server CPU: {avg_cpu:.1f}%
    Avg Server RAM: {avg_ram:.1f} MB
    Avg Latency: {avg_lat:.2f}s
    """
    print(summary_text)

    print(f"\nTest Ended. Max Clients Achieved: {active_clients}")
    # Cancel all
    for t in tasks: t.cancel()

if __name__ == "__main__":
    from datetime import datetime
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
