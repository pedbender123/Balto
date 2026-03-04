import os
import io
import time
import numpy as np
import requests
import wave
import re
import json
from app.core import config
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
# --- Configuração AssemblyAI (Substituto do Soniox) ---
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY")

# --- Configuração Deepgram ---
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")

# --- Configuração Gladia ---
GLADIA_API_KEY = os.environ.get("GLADIA_API_KEY")

# --- Smart Routing Config ---
SMART_ROUTING_ENABLE = os.environ.get("SMART_ROUTING_ENABLE", "1") == "1"
SMART_ROUTING_SNR_THRESHOLD = float(os.environ.get("SMART_ROUTING_SNR_THRESHOLD", "15.0"))
SMART_ROUTING_MIN_DURATION = float(os.environ.get("SMART_ROUTING_MIN_DURATION", "5.0"))

EXCLUSIONS_PATH = os.path.join(os.path.dirname(__file__), "dados", "exclusions.json")

def carregar_exclusoes():
    """Carrega a blacklist e padrões regex do arquivo JSON."""
    if not os.path.exists(EXCLUSIONS_PATH):
        return {"exact_match_exclusions": [], "regex_patterns": []}
    try:
        with open(EXCLUSIONS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Erro ao carregar exclusões: {e}")
        return {"exact_match_exclusions": [], "regex_patterns": []}

def limpar_texto_transcricao(texto: str) -> str:
    """
    Sanitiza a transcrição:
    1. Remove conteúdo entre parênteses (ex: som de fundo).
    2. Aplica blacklist de termos exatos.
    """
    if not texto:
        return ""
    
    exclusoes = carregar_exclusoes()
    
    # 1. Remover conteúdo entre parênteses (ex: anotações do ElevenLabs)
    texto_limpo = re.sub(r'\(.*?\)', '', texto)
    
    # 2. Aplicar outros padrões Regex do JSON
    for pattern in exclusoes.get("regex_patterns", []):
        if pattern != r'\(.*?\)':  # Já limpamos acima
            try:
                texto_limpo = re.sub(pattern, '', texto_limpo)
            except Exception as e:
                print(f"Erro no padrão regex {pattern}: {e}")
    
    # Normalizar espaços
    texto_limpo = " ".join(texto_limpo.split()).strip()
    
    # 3. Check Exact Match Blacklist (case insensitive opcional, aqui exato)
    # Se sobrar apenas um termo da blacklist, limpamos tudo.
    if texto_limpo in exclusoes.get("exact_match_exclusions", []):
        return ""
    
    return texto_limpo

def transcrever_deepgram(audio_bytes: bytes) -> str:
    """Modelo Rápido (Deepgram)."""
    if not DEEPGRAM_API_KEY:
        print("[Deepgram] API Key não configurada.")
        return ""
    
    url = "https://api.deepgram.com/v1/listen?model=nova-2&language=pt&smart_format=true"
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "audio/wav"
    }
    
    try:
        # Wrap PCM in WAV
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio_bytes)
        
        response = requests.post(url, headers=headers, data=wav_buffer.getvalue(), timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            # Deepgram return format: results.channels[0].alternatives[0].transcript
            return data.get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0].get('transcript', "")
        else:
            print(f"[Deepgram] Erro: {response.status_code} - {response.text}")
            return f"[ERROR {response.status_code}]"
            
    except Exception as e:
        print(f"[Deepgram] Exceção: {e}")
        return f"[EXCEPTION] {e}"

def transcrever_gladia(audio_bytes: bytes) -> str:
    """Modelo Gladia (Multilingual)."""
    if not GLADIA_API_KEY:
        print("[Gladia] API Key não configurada.")
        return ""

    # Usando V2 API (Upload -> Transcribe) ou Audio Intelligence?
    # Vamos tentar o endpoint de upload direto se existir, ou multipart
    # Docs v2 sugerem upload primeiro.
    
    headers = {
        "x-gladia-key": GLADIA_API_KEY
    }
    
    try:
        # Wrap in WAV
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio_bytes)
        wav_buffer.name = "audio.wav"
        
        # 1. Upload
        files = {
            'audio': ('audio.wav', wav_buffer.getvalue(), 'audio/wav')
        }
        
        upload_response = requests.post(
            "https://api.gladia.io/v2/upload/",
            headers=headers,
            files=files,
            timeout=60
        )
        
        if upload_response.status_code != 200:
            print(f"[Gladia] Erro Upload: {upload_response.text}")
            return f"[ERROR Upload {upload_response.status_code}]"
            
        audio_url = upload_response.json().get("audio_url")
        
        # 2. Transcription
        data = {
            "audio_url": audio_url,
            "language": "pt"
        }
        
        transcribe_response = requests.post(
            "https://api.gladia.io/v2/transcription/",
            headers=headers,
            json=data,
            timeout=60
        )
        
        if transcribe_response.status_code == 201:
            result_url = transcribe_response.json().get("result_url")
            # Polling needed
            
            while True:
                res = requests.get(result_url, headers=headers)
                status = res.json().get("status")
                
                if status == "done":
                    return res.json().get("result", {}).get("transcription", {}).get("full_transcript", "")
                elif status == "error":
                    return f"[ERROR Gladia Processing]"
                
                time.sleep(1)
        else:
             print(f"[Gladia] Erro Transcribe: {transcribe_response.text}")
             return f"[ERROR Transcribe {transcribe_response.status_code}]"

    except Exception as e:
         print(f"[Gladia] Exceção: {e}")
         return f"[EXCEPTION] {e}"

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

def transcrever_elevenlabs(audio_bytes: bytes) -> tuple:
    """Modelo Caro e Robusto (ElevenLabs Scribe).
    Retorna (texto, words_data) onde words_data é lista de dicts com timestamps.
    """
    client = key_manager.get_client()
    if not client: return "[Erro: Nenhuma chave ElevenLabs configurada]", []
    
    # Duração em segundos para tracking
    duration = len(audio_bytes) / 32000.0 # 16k * 2 bytes
    
    try:
        # Enviar PCM direto (sem WAV wrapper) — menor latência
        pcm_buffer = io.BytesIO(audio_bytes)
        pcm_buffer.name = "audio.pcm"
        
        result = client.speech_to_text.convert(
            file=pcm_buffer,
            model_id="scribe_v1",
            language_code="pt",
            timestamps_granularity="word",
            file_format="pcm_s16le_16",
        )
        
        # Se sucesso, registra uso
        key_manager.register_usage(duration)
        
        # Extrair word timestamps
        words_data = []
        if hasattr(result, 'words') and result.words:
            words_data = [
                {"text": w.text, "start": w.start, "end": w.end, "type": str(w.type)}
                for w in result.words
                if w.start is not None and w.end is not None
            ]
        
        return result.text, words_data
    except Exception as e:
        print(f"Erro ElevenLabs: {e}")
        return f"[ERROR] {e}", []

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
            f"{config.ASSEMBLYAI_BASE_URL}/v2/upload",
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
            f"{config.ASSEMBLYAI_BASE_URL}/v2/transcript",
            headers=headers,
            json=json_data
        )
        transcript_response.raise_for_status()
        transcript_id = transcript_response.json()["id"]
        
        # 3. Polling
        polling_endpoint = f"{config.ASSEMBLYAI_BASE_URL}/v2/transcript/{transcript_id}"
        
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

def _extrair_speech_ranges(words_data: list, chunk_duration: float) -> dict | None:
    """
    A partir dos word timestamps, extrai faixas contíguas de fala.
    Funde faixas com gap < 0.3s. Retorna dict compacto para armazenamento.
    """
    if not words_data:
        return None
    
    # Filtra apenas words (não audio_events)
    speech_words = [
        w for w in words_data 
        if w.get("type") in ("word", "SpeechToTextWordResponseModelType.WORD")
        and w.get("start") is not None 
        and w.get("end") is not None
    ]
    
    if not speech_words:
        return {"ranges": [], "speech_pct": 0.0, "silence_pct": 100.0, "word_count": 0}
    
    # Ordenar por start
    speech_words.sort(key=lambda w: w["start"])
    
    # Fundir faixas adjacentes (gap < 0.3s)
    MERGE_GAP = 0.3
    ranges = []
    cur_start = speech_words[0]["start"]
    cur_end = speech_words[0]["end"]
    
    for w in speech_words[1:]:
        if w["start"] - cur_end <= MERGE_GAP:
            cur_end = max(cur_end, w["end"])
        else:
            ranges.append([round(cur_start, 2), round(cur_end, 2)])
            cur_start = w["start"]
            cur_end = w["end"]
    ranges.append([round(cur_start, 2), round(cur_end, 2)])
    
    # Calcular percentuais
    total_speech = sum(r[1] - r[0] for r in ranges)
    speech_pct = round((total_speech / chunk_duration) * 100, 1) if chunk_duration > 0 else 0.0
    silence_pct = round(100.0 - speech_pct, 1)
    
    return {
        "ranges": ranges,
        "speech_pct": speech_pct,
        "silence_pct": silence_pct,
        "word_count": len(speech_words)
    }


def transcrever_inteligente(audio_bytes: bytes) -> dict:
    """
    Smart Routing: Decide qual modelo usar baseado na qualidade do áudio.
    """
    snr = calcular_snr(audio_bytes)
    duration_sec = len(audio_bytes) / 32000.0
    
    # Lógica de Decisão (Controlada por Env):
    
    usar_economico = False
    words_data = []
    
    if SMART_ROUTING_ENABLE:
        # - Áudios Curtos (< MIN_DURATION): AssemblyAI tende a falhar. Vai para ElevenLabs.
        # - Áudios Médios/Longos (>= MIN_DURATION) e Limpos (> SNR_THRESHOLD): Vai para AssemblyAI (Economia).
        # - Áudios Ruidosos: ElevenLabs (Robustez).
        usar_economico = (snr > SMART_ROUTING_SNR_THRESHOLD) and (duration_sec >= SMART_ROUTING_MIN_DURATION)
    else:
        # Se desligado, usa sempre ElevenLabs (Robustez)
        usar_economico = False
    
    if usar_economico:
        texto = transcrever_assemblyai(audio_bytes)
        modelo = "assemblyai"
        custo = 0.005 # Estimativa AssemblyAI
        # AssemblyAI não retorna word timestamps no nosso flow
        words_data = []
    else:
        texto, words_data = transcrever_elevenlabs(audio_bytes)
        modelo = "elevenlabs"
        custo = 0.05 # Estimativa ElevenLabs
        
    # Aplicar limpeza de texto antes de retornar
    texto_final = limpar_texto_transcricao(texto)
    if texto and not texto_final:
        print(f"[Transcription] Texto original '{texto}' foi totalmente limpo/descartado.")

    # Extrair speech_ranges dos word timestamps
    speech_ranges = _extrair_speech_ranges(words_data, duration_sec)

    return {
        "texto": texto_final,
        "modelo": modelo,
        "custo": custo,
        "snr": snr,
        "speech_ranges": speech_ranges
    }