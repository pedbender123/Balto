import os
import io
import numpy as np
import requests
from elevenlabs.client import ElevenLabs

# Configuração ElevenLabs
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
try:
    client_eleven = ElevenLabs(api_key=ELEVENLABS_API_KEY)
except:
    client_eleven = None

# Configuração Modelo Econômico (Ex: Soniox ou Whisper Local)
# Se fosse Whisper Local, carregaríamos o modelo aqui.
SONIOX_API_KEY = os.environ.get("SONIOX_API_KEY")

def calcular_snr(audio_bytes: bytes) -> float:
    """
    Calcula a relação Sinal-Ruído (SNR) aproximada.
    Retorna valor em dB.
    """
    try:
        # Converte bytes pcm16 para array numpy
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        
        if len(audio_array) == 0: return 0.0
        
        # Estimação simples:
        # Assumimos que os 10% de menor energia são ruído de fundo
        # E os 10% de maior energia são o sinal
        energy = np.abs(audio_array)
        sorted_energy = np.sort(energy)
        
        noise_floor_len = max(1, int(len(audio_array) * 0.1))
        signal_peak_len = max(1, int(len(audio_array) * 0.1))
        
        noise_power = np.mean(sorted_energy[:noise_floor_len] ** 2)
        signal_power = np.mean(sorted_energy[-signal_peak_len:] ** 2)
        
        if noise_power == 0: return 50.0 # Muito limpo
        
        ratio = signal_power / noise_power
        snr_db = 10 * np.log10(ratio)
        return snr_db
        
    except Exception as e:
        print(f"Erro SNR: {e}")
        return 0.0

def transcrever_elevenlabs(audio_bytes: bytes) -> str:
    """Modelo Caro e Robusto."""
    if not client_eleven: return "[Erro: ElevenLabs não configurado]"
    try:
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.wav"
        result = client_eleven.speech_to_text.convert(
            file=audio_file,
            model_id="scribe_v1",
            tag="balto_pharmacy"
        )
        return result.text
    except Exception as e:
        print(f"Erro ElevenLabs: {e}")
        return ""

def transcrever_economico(audio_bytes: bytes) -> str:
    """
    Modelo Barato (Soniox / Whisper Tiny).
    Placeholder para implementação real.
    """
    # Exemplo mockado de baixo custo
    # Aqui entraria: requests.post('https://api.soniox.com/transcribe', ...)
    print("[Transcriber] Usando modelo ECONÔMICO")
    return transcrever_elevenlabs(audio_bytes) # Fallback temporário para garantir que funciona

def transcrever_inteligente(audio_bytes: bytes) -> dict:
    """
    Smart Routing: Decide qual modelo usar baseado na qualidade do áudio.
    """
    snr = calcular_snr(audio_bytes)
    duration_sec = len(audio_bytes) / 32000 # 16k * 2 bytes
    
    # Lógica de Decisão
    # Se o áudio é muito limpo (SNR > 15dB) e curto, modelo barato resolve.
    # Se o áudio é sujo ou muito longo (complexo), usa ElevenLabs.
    
    usar_economico = (snr > 15.0) and (duration_sec < 5.0)
    
    if usar_economico:
        texto = transcrever_economico(audio_bytes)
        modelo = "economico"
        custo = 0.001 # Custo fictício baixo
    else:
        texto = transcrever_elevenlabs(audio_bytes)
        modelo = "elevenlabs"
        custo = 0.05 # Custo fictício alto
        
    return {
        "texto": texto,
        "modelo": modelo,
        "custo": custo,
        "snr": snr
    }