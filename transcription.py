import os
import io
import wave
import numpy as np
import noisereduce as nr
from elevenlabs.client import ElevenLabs

# Inicializa o cliente ElevenLabs
try:
    client = ElevenLabs(api_key=os.environ.get("ELEVENLABS_API_KEY"))
except Exception as e:
    print(f"Erro ao inicializar cliente ElevenLabs: {e}. Verifique sua ELEVENLABS_API_KEY.")
    client = None

# Constantes do áudio
RATE = 16000
CHANNELS = 1
SAMPWIDTH = 2 # 16-bit

def _clean_audio(audio_bytes: bytes) -> bytes:
    """
    Aplica redução de ruído (Deep Denoising) usando noisereduce.
    Remove chiados de TV, ar condicionado e ruídos de fundo estacionários.
    """
    try:
        # 1. Converte bytes para array numpy (int16)
        audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
        
        # 2. Aplica redução de ruído (stationary=True é mais rápido e bom para ruído constante)
        # prop_decrease=0.8 mantém 20% do "som ambiente" para não soar artificial demais
        reduced_noise_data = nr.reduce_noise(
            y=audio_data, 
            sr=RATE, 
            stationary=True, 
            prop_decrease=0.8,
            n_jobs=1 # 1 thread para não travar o servidor se tiver muitos requests
        )
        
        # 3. Converte de volta para bytes
        return reduced_noise_data.astype(np.int16).tobytes()
    except Exception as e:
        print(f"Aviso: Falha no denoiser ({e}), usando áudio original.")
        return audio_bytes

def transcrever(audio_bytes: bytes) -> str:
    """
    Limpa o áudio e converte em texto usando ElevenLabs.
    """
    if not client:
        return "[ERRO: Cliente ElevenLabs não inicializado]"

    try:
        # --- PASSO NOVO: LIMPEZA ---
        # Abafa sons de fundo antes de enviar para a IA
        clean_bytes = _clean_audio(audio_bytes)
        
        # --- Preparação do Arquivo WAV ---
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPWIDTH)
            wf.setframerate(RATE)
            wf.writeframes(clean_bytes)
        
        wav_buffer.seek(0)
        wav_buffer.name = "audio.wav"

        # --- Envio para ElevenLabs ---
        response = client.speech_to_text.convert(
            file=wav_buffer,
            model_id="scribe_v1"
        )
        
        return response.text
        
    except Exception as e:
        print(f"Erro na API de Transcrição: {e}")
        return f"[Erro na transcrição: {e}]"