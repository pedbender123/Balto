import os
import io
import time
import numpy as np
import requests
import wave
from elevenlabs.client import ElevenLabs

# --- Gerenciamento de Chaves ElevenLabs ---
class ElevenLabsKeyManager:
    def __init__(self):
        # Lê chaves separadas por vírgula 'KEY1,KEY2,KEY3'
        keys_str = os.environ.get("ELEVENLABS_API_KEYS", "")
        if not keys_str:
            # Fallback para a chave antiga única se a nova env não existir
            single_key = os.environ.get("ELEVENLABS_API_KEY", "")
            self.keys = [k.strip() for k in single_key.split(',') if k.strip()]
        else:
            self.keys = [k.strip() for k in keys_str.split(',') if k.strip()]
        
        self.current_key_index = 0
        # Mapa de uso: {key: seconds_used}
        self.usage_map = {k: 0.0 for k in self.keys}
        self.limit_seconds = 120 * 60 # 120 minutos

        print(f"[ElevenLabs] Carregadas {len(self.keys)} chaves.")

    def get_client(self):
        if not self.keys:
            return None
        
        # Pega chave atual
        current_key = self.keys[self.current_key_index]
        
        # Verifica se estourou o limite (apenas check local simples)
        if self.usage_map[current_key] >= self.limit_seconds:
             # Tenta rodar para a próxima se tiver mais de uma
             if len(self.keys) > 1:
                 print(f"[ElevenLabs] Chave {current_key[:5]}... excedeu limite ({self.usage_map[current_key]/60:.1f} min). Trocando.")
                 self.rotate_key()
                 current_key = self.keys[self.current_key_index]
        
        return ElevenLabs(api_key=current_key)

    def rotate_key(self):
        if not self.keys: return
        self.current_key_index = (self.current_key_index + 1) % len(self.keys)
        new_key = self.keys[self.current_key_index]
        print(f"[ElevenLabs] Rotacionado para chave: {new_key[:5]}...")

    def register_usage(self, seconds: float):
        if not self.keys: return
        current_key = self.keys[self.current_key_index]
        self.usage_map[current_key] += seconds

# Instância Global do Manager
key_manager = ElevenLabsKeyManager()

# --- Configuração AssemblyAI (Substituto do Soniox) ---
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY")

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
    """Modelo Caro e Robusto (ElevenLabs Scribe)."""
    client = key_manager.get_client()
    if not client: return "[Erro: Nenhuma chave ElevenLabs configurada]"
    
    # Duração em segundos para tracking
    duration = len(audio_bytes) / 32000.0 # 16k * 2 bytes
    
    try:
        # Wrap PCM in WAV container
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio_bytes)
        
        # Reset pointer for reading
        wav_buffer.seek(0)
        wav_buffer.name = "audio.wav"
        
        result = client.speech_to_text.convert(
            file=wav_buffer,
            model_id="scribe_v1",
            language_code="pt"
        )
        
        # Se sucesso, registra uso
        key_manager.register_usage(duration)
        
        return result.text
    except Exception as e:
        print(f"Erro ElevenLabs: {e}")
        return f"[ERROR] {e}"

def transcrever_assemblyai(audio_bytes: bytes) -> str:
    """
    Modelo Econômico (AssemblyAI).
    Substitui o antigo Soniox.
    """
    if not ASSEMBLYAI_API_KEY:
        print("[AssemblyAI] API Key não configurada.")
        return ""
    
    headers = {
        "authorization": ASSEMBLYAI_API_KEY
    }
    
    try:
        # Wrap PCM in WAV container
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio_bytes)
        
        wav_data = wav_buffer.getvalue()

        # 1. Upload
        upload_response = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=headers,
            data=wav_data
        )
        upload_response.raise_for_status()
        upload_url = upload_response.json()["upload_url"]
        
        # 2. Transcribe
        json_data = {
            "audio_url": upload_url,
            "language_code": "pt" # Forçar português
        }
        transcript_response = requests.post(
            "https://api.assemblyai.com/v2/transcript",
            headers=headers,
            json=json_data
        )
        transcript_response.raise_for_status()
        transcript_id = transcript_response.json()["id"]
        
        # 3. Polling
        polling_endpoint = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        
        while True:
            poll_response = requests.get(polling_endpoint, headers=headers)
            poll_response.raise_for_status()
            status = poll_response.json()["status"]
            
            if status == "completed":
                return poll_response.json()["text"] or ""
            elif status == "error":
                print(f"[AssemblyAI] Erro no processamento: {poll_response.json().get('error')}")
                return ""
            
            time.sleep(0.5) # Polling rápido
            
    except Exception as e:
        print(f"[AssemblyAI] Erro de requisição: {e}")
        return ""

def transcrever_inteligente(audio_bytes: bytes) -> dict:
    """
    Smart Routing: Decide qual modelo usar baseado na qualidade do áudio.
    """
    snr = calcular_snr(audio_bytes)
    duration_sec = len(audio_bytes) / 32000.0
    
    # Lógica de Decisão
    # Se o áudio é muito limpo (SNR > 15dB) e curto, modelo barato resolve.
    # Se o áudio é sujo ou muito longo (complexo), usa ElevenLabs.
    
    usar_economico = (snr > 15.0) and (duration_sec < 5.0)
    
    if usar_economico:
        texto = transcrever_assemblyai(audio_bytes)
        modelo = "assemblyai"
        custo = 0.005 # Estimativa AssemblyAI
    else:
        texto = transcrever_elevenlabs(audio_bytes)
        modelo = "elevenlabs"
        custo = 0.05 # Estimativa ElevenLabs
        
    return {
        "texto": texto,
        "modelo": modelo,
        "custo": custo,
        "snr": snr
    }