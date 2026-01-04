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
        
        # O endpoint user.get() requer permissão 'user_read', que algumas chaves não têm.
        # Vamos tentar listar modelos, que é mais provável de funcionar, ou apenas validar a lib.
        try:
             # Tenta listar modelos (leve e geralmente permitido)
             models = client.models.get_all()
             return f"✅ OK (Models List ok)"
        except Exception:
             # Se falhar permissão, tenta check minimalista
             # Se chegamos aqui, a LIB instanciou, mas a API pode ter negado. 
             # Retornamos aviso.
             return "⚠️ Aviso (Chave configurada, mas sem permissão de leitura de User/Models)"

    except Exception as e:
         return f"❌ ERRO ({str(e)})"

def check_assemblyai():
    """Verifica chave AssemblyAI."""
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        return "❌ OFF (Sem chave)"
    
    try:
        # 422 no upload vazio é esperado para alguns clients.
        # Vamos tentar um GET leve para validar a chave sem enviar dados.
        # GET /v2/transcript (sem id) -> 404 ou 400?
        # A doc diz que listar models não requer auth? Vamos tentar upload com 1 byte.
        
        headers = {'authorization': api_key}
        # Tenta pegar token info se existir endpoint, se não, um upload minimo valido.
        
        response = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=headers,
            data=b"0" # 1 byte payload (evita 422 Unprocessable Entity por ser vazio)
        )
        
        if response.status_code in [200, 201]: 
            return "✅ OK"
        elif response.status_code == 401:
            return "❌ ERRO (401 Unauthorized)"
        elif response.status_code == 422:
             # 422 significa que leu a chave mas rejeitou o arquivo (talvez formato).
             # Se fosse auth ruim, seria 401. 
             # Então 422 confirma que a autenticação passou.
             return "✅ OK (Auth Validada)"
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
