import os
import requests
from app import analysis, transcription

def check_grok():
    """Verifica conexão com a xAI (Grok)."""
    try:
        if not analysis.client:
            return "❌ OFF (Cliente não inicializado ou sem chave)"
        
        # Teste simples de conexão (list models ou chat curto)
        # Vamos tentar um chat ultra-básico p/ garantir que a chave funciona
        response = analysis.client.chat.completions.create(
            model="grok-3-mini",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1
        )
        return "✅ OK (Grok-3-Mini Online)"
    except Exception as e:
        return f"❌ ERRO ({str(e)})"

def check_elevenlabs():
    """Verifica chaves do ElevenLabs."""
    try:
        client = transcription.key_manager.get_client()
        if not client:
             return "❌ OFF (Sem chaves configuradas)"
        
        # Verifica user info (chamada leve)
        user = client.user.get()
        return f"✅ OK (Subscription: {user.subscription.tier})"
    except Exception as e:
         return f"❌ ERRO ({str(e)})"

def check_assemblyai():
    """Verifica chave AssemblyAI."""
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        return "❌ OFF (Sem chave)"
    
    try:
        # Tenta listar arquivos ou algo leve. Como AssemblyAI n tem "ping" oficial fácil, 
        # vamos fazer um request fake para validar auth no upload (sem enviar dados)
        # Ou melhor, consultar a API de lemur/models se possível, mas upload vazio é mais garantido de bater na auth.
        
        # Alternativa: Requests direto
        headers = {'authorization': api_key}
        # Tenta pegar informacoes da conta (se disponivel na API V2) 
        # ou apenas init de upload
        
        response = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=headers,
            data=b"" # Empty payload
        )
        
        # 400 Bad Request ainda significa que Autenticou (se fosse 401 seria Unauthorized)
        if response.status_code in [200, 201, 400]: 
            return "✅ OK"
        elif response.status_code == 401:
            return "❌ ERRO (401 Unauthorized)"
        else:
             return f"⚠️ Status {response.status_code}"
            
    except Exception as e:
        return f"❌ ERRO ({str(e)})"

def run_all_checks():
    print("\n--- 🩺 Diagnóstico de Inicialização ---")
    print(f"Grok (xAI):      {check_grok()}")
    print(f"ElevenLabs:      {check_elevenlabs()}")
    print(f"AssemblyAI:      {check_assemblyai()}")
    print("---------------------------------------\n")
