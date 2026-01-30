import asyncio
import os
import subprocess
import sys

# Script mestre para rodar o protocolo completo
# Uso: python run_protocol.py [API_URL]

def run_step(name, command):
    print(f"\n{'='*20}")
    print(f"RUNNING STEP: {name}")
    print(f"{'='*20}")
    try:
        # Usar o python atual
        full_cmd = [sys.executable] + command
        process = subprocess.run(full_cmd, capture_output=False, text=True)
        return process.returncode == 0
    except Exception as e:
        print(f"Error running {name}: {e}")
        return False

if __name__ == "__main__":
    # 1. Rodar Testes REST e capturar credenciais
    # (Para simplificar a integração, o run_protocol pode rodar o rest e extrair a key se necessário,
    # mas por agora vamos rodar sequencialmente)
    
    print("🚀 BALTO API TESTING PROTOCOL 🚀")
    
    # Criar balcão de teste via REST para usar no WS
    import requests
    BASE_URL = os.environ.get("BALTO_URL", "http://localhost:8765")
    
    import time
    timestamp = int(time.time())
    print(f"\n[1/3] Provisioning Test Assets on {BASE_URL}...")
    max_retries = 5
    for i in range(max_retries):
        try:
            print(f"   Attempt {i+1}/{max_retries}...")
            res = requests.post(f"{BASE_URL}/cadastro/cliente", json={
                "email": f"protocol_test_{timestamp}@pbpm.dev",
                "razao_social": "Protocol Test",
                "telefone": "0"
            }, timeout=10)
            
            if res.status_code not in [200, 201]:
                print(f"      ⚠️ Failed to create client: {res.status_code}")
                time.sleep(3)
                continue
                
            code = res.json().get("codigo")
            if not code:
                print(f"      ⚠️ No code in response")
                time.sleep(3)
                continue

            res = requests.post(f"{BASE_URL}/cadastro/balcao", json={
                "nome_balcao": "Protocol Counter",
                "user_codigo": str(code)
            }, timeout=10)
            
            if res.status_code != 200:
                print(f"      ⚠️ Failed to create balcao: {res.status_code}")
                time.sleep(3)
                continue

            creds = res.json()
            api_key = creds.get("api_key")
            os.environ["BALTO_API_KEY"] = api_key
            print(f"   ✅ Assets Ready. API_KEY: {api_key[:10]}...")
            break
        except Exception as e:
            print(f"   ⚠️ Wait for server stabilization: {e}")
            if i == max_retries - 1:
                print("❌ Final failure after retries.")
                sys.exit(1)
            time.sleep(5)

    # 2. Rodar suite REST
    run_step("REST API SUITE", ["test_rest_api.py"])
    
    # 3. Rodar suite WebSocket
    run_step("WEBSOCKET FLOW", ["test_websocket.py"])
    
    print("\n" + "!" * 40)
    print("PROTOCOL EXECUTION FINISHED")
    print("Refer to server logs for deep trace analysis.")
    print("!" * 40)
