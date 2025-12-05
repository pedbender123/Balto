import os
import io
from elevenlabs.client import ElevenLabs

# Inicializa ElevenLabs
try:
    client = ElevenLabs(api_key=os.environ.get("ELEVENLABS_API_KEY"))
except Exception as e:
    print(f"Erro client ElevenLabs: {e}")
    client = None

def transcrever(audio_bytes: bytes) -> str:
    if not client:
        return "[ERRO: API ElevenLabs não config]"

    try:
        # ElevenLabs requer um objeto file-like com nome
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.wav" 

        # Chamada para Speech to Text (Scribe)
        # Verifique na doc deles se o modelo é 'scribe_v1' ou similar na sua versão da lib
        result = client.speech_to_text.convert(
            file=audio_file,
            model_id="scribe_v1", 
            tag="audio_farmacia"
        )
        
        return result.text
        
    except Exception as e:
        print(f"Erro Transcrição ElevenLabs: {e}")
        return f"[Erro: {e}]"