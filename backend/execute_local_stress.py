
import asyncio
import aiohttp
import json
import wave
import sys
import os
import time
import threading
import random
from datetime import datetime

# --- CONFIG ---
DURATION_MINUTES = 360 # 6 Horas
CLIENTS = 5
AUDIO_FILE = "8_20250702093051.webm" # Na mesma pasta (/backend)
WS_URL = "wss://balto.pbpmdev.com/ws" # WebSocket Seguro
HTTP_URL = "https://balto.pbpmdev.com" # API HTTP

# Add backend to path (assumption: this script is in server/ or backend/)
sys.path.append(os.path.abspath("backend"))

running = True
stats_lock = threading.Lock()
stats = {"sent_chunks": 0, "responses": 0, "errors": 0}

async def register_remote_client(idx):
    """Cria credenciais via API HTTP Remota"""
    import requests
    try:
        email = f"stress_auto_{idx}_{random.randint(1000,9999)}@teste.com"
        # 1. Cria Cliente
        res = requests.post(f"{HTTP_URL}/cadastro/cliente", json={
            "email": email,
            "razao_social": "Auto Stress Corp",
            "telefone": "000"
        }, timeout=5)
        
        if res.status_code != 201:
            print(f"[Setup-{idx}] Falha criar cliente: {res.text}")
            return None
            
        codigo = res.json().get("codigo")
        
        # 2. Cria Balcão
        res = requests.post(f"{HTTP_URL}/cadastro/balcao", json={
            "nome_balcao": f"Balcao Auto {idx}",
            "user_codigo": codigo
        }, timeout=5)
        
        if res.status_code != 200:
             print(f"[Setup-{idx}] Falha criar balcao: {res.text}")
             return None
             
        data = res.json()
        print(f"[Setup-{idx}] Sucesso! Key: {data.get('api_key')[:10]}...")
        return data.get("api_key")
        
    except Exception as e:
        print(f"[Setup-{idx}] Erro Conexão API: {e}")
        return None

async def client_robot(client_id, api_key):
    global running
    print(f"[Robot-{client_id}] Iniciando (Key: {api_key[:5]}...)...")
    
    end_time = time.time() + (DURATION_MINUTES * 60)
    
    while running and time.time() < end_time:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(WS_URL) as ws:
                    # Auth
                    await ws.send_json({"api_key": api_key})
                    
                    if not os.path.exists(AUDIO_FILE):
                         print(f"[Robot-{client_id}] ERRO: Arquivo {AUDIO_FILE} não encontrado.")
                         return

                    with open(AUDIO_FILE, "rb") as f:
                        data = f.read(4096)
                        while data and running:
                            await ws.send_bytes(data)
                            with stats_lock: stats["sent_chunks"] += 1
                            await asyncio.sleep(0.1)
                            data = f.read(4096)
                            
                            # Check response occasionally
                            try:
                                msg = await ws.receive_json(timeout=0.01)
                                with stats_lock: stats["responses"] += 1
                            except asyncio.TimeoutError:
                                pass
                            except Exception:
                                pass
                                
                    # End of file, wait a bit then loop (simulate new call)
                    await asyncio.sleep(2)
                    
        except Exception as e:
            with stats_lock: stats["errors"] += 1
            print(f"[Robot-{client_id}] Erro Conexão ({WS_URL}): {e}. Retentando em 5s...")
            await asyncio.sleep(5)

    print(f"[Robot-{client_id}] Finalizado.")

def run_thread(cid, api_key):
    asyncio.run(client_robot(cid, api_key))

def main():
    print(f"--- STRESS REMOTO (AUTO-PROVISIONAMENTO) ---")
    print(f"Duração: {DURATION_MINUTES} min")
    print(f"Clientes: {CLIENTS}")
    print(f"Alvo API: {HTTP_URL}")
    print(f"Alvo WS: {WS_URL}")
    print("----------------------------------")

    # 1. Setup DB Credentials via API
    api_keys = []
    print("Criando credenciais via API HTTP Remota...")
    
    # Run sync for simplicity in setup phase
    for i in range(CLIENTS):
        # We need an async loop just for the requests? No, requests is sync.
        # Wait, inside async def? I used requests sync lib in register_remote_client.
        # But I defined it async? Let's fix that.
        key = asyncio.run(register_remote_client(i))
        if key:
            api_keys.append(key)
        else:
            print("Falha crítica ao obter chave. Abortando.")
            return

    # 2. Start Threads
    threads = []
    for i in range(len(api_keys)):
        t = threading.Thread(target=run_thread, args=(i, api_keys[i]))
        t.start()
        threads.append(t)


    # 3. Monitor Loop
    try:
        start_ts = time.time()
        while any(t.is_alive() for t in threads):
            elapsed = int(time.time() - start_ts)
            with stats_lock:
                print(f"[{elapsed}s] Chunks: {stats['sent_chunks']} | Respostas: {stats['responses']} | Erros: {stats['errors']}", end='\r')
            time.sleep(1)
            
            if elapsed > (DURATION_MINUTES * 60) + 10:
                break
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário!")
        global running
        running = False

    print("\n--- FINALIZADO ---")

if __name__ == "__main__":
    main()
