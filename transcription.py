import os
import io
import wave
from elevenlabs.client import ElevenLabs # <-- Biblioteca nova

# Inicializa o cliente ElevenLabs
try:
    client = ElevenLabs(api_key=os.environ.get("ELEVENLABS_API_KEY"))
except Exception as e:
    print(f"Erro ao inicializar cliente ElevenLabs: {e}. Verifique sua ELEVENLABS_API_KEY.")
    client = None

# Constantes do nosso áudio (sem mudança)
RATE = 16000
CHANNELS = 1
SAMPWIDTH = 2 # 16-bit = 2 bytes

def transcrever(audio_bytes: bytes) -> str:
    """
    Converte um bloco de áudio (bytes) em texto (string) usando ElevenLabs.
    """
    if not client:
        return "[ERRO: Cliente ElevenLabs não inicializado]"

    try:
        # --- Lógica do .wav na memória (sem mudança) ---
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPWIDTH)
            wf.setframerate(RATE)
            wf.writeframes(audio_bytes)
        
        wav_buffer.seek(0)
        wav_buffer.name = "audio.wav"
        # --- Fim da lógica do .wav ---

        # --- A CORREÇÃO ESTÁ AQUI ---
        # Trocamos 'audio=wav_buffer' por 'files=wav_buffer'
        response = client.speech_to_text.convert(
            file=wav_buffer,
            model_id="scribe_v1"
        )
        
        return response.text
        
    except Exception as e:
        print(f"Erro na API de Transcrição (ElevenLabs): {e}")
        return f"[Erro na transcrição: {e}]"