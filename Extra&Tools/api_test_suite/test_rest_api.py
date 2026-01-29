import requests
import json
import os
import sys

# Configurações
BASE_URL = os.environ.get("BALTO_URL", "http://localhost:8765")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "x9PeHTY7ouQNvzJH")

def print_result(name, success, info=""):
    status = "✅ PASSED" if success else "❌ FAILED"
    print(f"[{status}] {name}")
    if info:
        print(f"    Info: {info}")

def test_basic_endpoints():
    print(f"\n--- Testing Basic REST Endpoints on {BASE_URL} ---")
    
    import time
    email = f"test_api_{int(time.time())}@pbpmdev.com"
    try:
        res = requests.post(f"{BASE_URL}/cadastro/cliente", json={
            "email": email,
            "razao_social": "API Protocol Test Corp",
            "telefone": "11900000000"
        })
        success = res.status_code in [201, 200]
        data = res.json() if success else {}
        user_codigo = data.get("codigo")
        print_result("POST /cadastro/cliente", success, f"Code: {user_codigo}")
    except Exception as e:
        print_result("POST /cadastro/cliente", False, str(e))
        return None

    # 2. Cadastro de Balcão
    if user_codigo:
        try:
            res = requests.post(f"{BASE_URL}/cadastro/balcao", json={
                "nome_balcao": "Test Counter 01",
                "user_codigo": user_codigo
            })
            success = res.status_code == 200
            data = res.json() if success else {}
            api_key = data.get("api_key")
            balcao_id = data.get("balcao_id")
            print_result("POST /cadastro/balcao", success, f"ID: {balcao_id}, Key: {api_key[:10]}...")
            return {"user_codigo": user_codigo, "api_key": api_key, "balcao_id": balcao_id}
        except Exception as e:
            print_result("POST /cadastro/balcao", False, str(e))
    
    return None

def test_admin_access():
    print(f"\n--- Testing Admin Endpoints ---")
    
    # 1. Admin Login
    try:
        res = requests.post(f"{BASE_URL}/admin/login", json={"password": ADMIN_SECRET}, allow_redirects=False)
        success = res.status_code == 200 and "admin_token=auth_ok" in res.headers.get("Set-Cookie", "")
        print_result("POST /admin/login", success)
        return res.cookies if success else None
    except Exception as e:
        print_result("POST /admin/login", False, str(e))
    
    return None

def test_ai_simulated(cookies):
    print(f"\n--- Testing AI / Test Endpoints ---")
    
    # 1. Test Analisar (LLM)
    try:
        res = requests.post(f"{BASE_URL}/api/test/analisar", json={
            "texto": "Preciso de um remédio para dor de cabeça"
        })
        success = res.status_code == 200
        print_result("POST /api/test/analisar", success)
    except Exception as e:
        print_result("POST /api/test/analisar", False, str(e))

    # 2. Data Interações (Admin)
    if cookies:
        try:
            res = requests.get(f"{BASE_URL}/api/data/interacoes", cookies=cookies)
            success = res.status_code == 200
            print_result("GET /api/data/interacoes", success)
        except Exception as e:
            print_result("GET /api/data/interacoes", False, str(e))

if __name__ == "__main__":
    creds = test_basic_endpoints()
    cookies = test_admin_access()
    test_ai_simulated(cookies)
    
    print("\n--- REST API Test Suite Finished ---")
