
import os
import requests
from app import transcription
from app.core import ai_client

def check_openai():
    """Verifica conexão com a OpenAI."""
    try:
        if not ai_client.ai_client.client:
            return "❌ OFF (Cliente não inicializado ou sem chave)"
        
        # Teste simples de conexão (list models ou chat curto)
        # Vamos tentar um chat ultra-básico p/ garantir que a chave funciona
        response = ai_client.ai_client.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1
        )
        return "✅ OK (OpenAI Online)"
    except Exception as e:
        return f"❌ ERRO ({str(e)})"

def check_elevenlabs():
    """Verifica chaves do ElevenLabs."""
    try:
        client = transcription.key_manager.get_client()
        if not client:
             return "❌ OFF (Sem chaves configuradas)"
        
        try:
             # Tenta listar modelos (leve e geralmente permitido)
             models = client.models.get_all()
             return f"✅ OK (Models List ok)"
        except Exception:
             return "⚠️ Aviso (Chave configurada, mas sem permissão de leitura de User/Models)"

    except Exception as e:
         return f"❌ ERRO ({str(e)})"

def check_assemblyai():
    """Verifica chave AssemblyAI."""
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        return "❌ OFF (Sem chave)"
    
    try:
        headers = {'authorization': api_key}
        response = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=headers,
            data=b"0" # 1 byte payload
        )
        
        if response.status_code in [200, 201]: 
            return "✅ OK"
        elif response.status_code == 401:
            return "❌ ERRO (401 Unauthorized)"
        elif response.status_code == 422:
             return "✅ OK (Auth Validada)"
        else:
             return f"⚠️ Status {response.status_code}"
            
    except Exception as e:
        return f"❌ ERRO ({str(e)})"

def run_all_checks():
    print("\n--- 🩺 Diagnóstico de Inicialização ---")
    print(f"OpenAI (GPT-4o): {check_openai()}")
    print(f"ElevenLabs:      {check_elevenlabs()}")
    print(f"AssemblyAI:      {check_assemblyai()}")
    print("---------------------------------------\n")
