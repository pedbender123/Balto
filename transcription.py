import os
import io
import wave
import numpy as np
import noisereduce as nr
from openai import OpenAI

# Inicializa o cliente OpenAI (requer OPENAI_API_KEY no .env)
try:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
except Exception as e:
    print(f"Erro ao inicializar cliente OpenAI: {e}. Verifique sua OPENAI_API_KEY.")
    client = None

# Constantes do áudio (mantidas do original)
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
        
        # 2. Aplica redução de ruído
        # stationary=True é mais rápido e bom para ruído constante
        reduced_noise_data = nr.reduce_noise(
            y=audio_data, 
            sr=RATE, 
            stationary=True, 
            prop_decrease=0.8,
            n_jobs=1 
        )
        
        # 3. Converte de volta para bytes
        return reduced_noise_data.astype(np.int16).tobytes()
    except Exception as e:
        print(f"Aviso: Falha no denoiser ({e}), usando áudio original.")
        return audio_bytes

def transcrever(audio_bytes: bytes) -> str:
    """
    Limpa o áudio e converte em texto usando OpenAI Whisper.
    """
    if not client:
        return "[ERRO: Cliente OpenAI não inicializado]"

    try:
        # --- LIMPEZA ---
        # Abafa sons de fundo antes de enviar para a IA
        clean_bytes = _clean_audio(audio_bytes)
        
        # --- Preparação do Arquivo WAV ---
        # O Whisper exige um arquivo nomeado (ex: audio.wav)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPWIDTH)
            wf.setframerate(RATE)
            wf.writeframes(clean_bytes)
        
        wav_buffer.seek(0)
        wav_buffer.name = "audio.wav" 

        # --- Envio para OpenAI (Whisper) ---
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=wav_buffer,
            language="pt" # Força o português para evitar erros de detecção
        )
        
        return response.text
        
    except Exception as e:
        print(f"Erro na API de Transcrição (Whisper): {e}")
        return f"[Erro na transcrição: {e}]"