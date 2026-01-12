# backend/app/speaker_id.py
#
# Identificação/cadastro de voz (Speaker ID) usando Resemblyzer + Postgres.
#
# - Recebe áudio PCM16 mono 16k
# - Salva um WAV em disco (CADASTRO_DIR)
# - Extrai embedding (float32)
# - Salva no Postgres em funcionarios (user_id, nome, audio_file_name, embedding)

from __future__ import annotations

import os
import uuid
import wave
import threading
from typing import Dict, List, Tuple, Optional

import numpy as np
from resemblyzer import VoiceEncoder

from app import db  # usa db.get_db_connection() e db.upsert_funcionario_por_nome()

# =========================
# Configs
# =========================
SAMPLE_RATE = 16000

DEFAULT_THRESHOLD = 0.75          # threshold padrão (batch)
SEGMENT_THRESHOLD_DEFAULT = 0.78  # threshold por segmento
SEGMENT_MARGIN_DEFAULT = 0.06     # gap mínimo top1 - top2

# Onde salvar cadastros de voz (WAV)
# Em Docker, você monta ./audio_dumps -> /backend/app/audio_dumps
CADASTRO_DIR = os.environ.get(
    "SPEAKER_CADASTRO_DIR",
    os.path.join(os.path.dirname(__file__), "audio_dumps", "cadastros_voz"),
)

# =========================
# Encoder (carregado 1x)
# =========================
_encoder: VoiceEncoder | None = None
_encoder_lock = threading.Lock()

def get_encoder() -> VoiceEncoder:
    global _encoder
    if _encoder is None:
        with _encoder_lock:
            if _encoder is None:
                _encoder = VoiceEncoder()
    return _encoder

# =========================
# Áudio -> embedding
# =========================
def extrair_embedding(audio_pcm16: bytes, sample_rate: int = SAMPLE_RATE) -> Optional[np.ndarray]:
    """
    Entrada: PCM16 mono (idealmente 16kHz), bytes.
    Saída: embedding float32 (np.ndarray).
    """
    if not audio_pcm16:
        return None

    audio_np = np.frombuffer(audio_pcm16, dtype=np.int16).astype(np.float32)
    if audio_np.size == 0:
        return None

    # PCM16 -> float32 [-1, 1]
    audio_np = audio_np / 32768.0

    # Seu pipeline já garante 16k. Se quiser resample no futuro, faria aqui.
    _ = sample_rate

    enc = get_encoder()
    emb = enc.embed_utterance(audio_np)
    return np.asarray(emb, dtype=np.float32)

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def _save_wav_pcm16(path: str, pcm16: bytes, sr: int = SAMPLE_RATE) -> None:
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sr)
        wf.writeframes(pcm16)

def _emb_to_bytes(emb: np.ndarray) -> bytes:
    return np.asarray(emb, dtype=np.float32).tobytes()

# =========================
# CADASTRO DE VOZ (API pública)
# =========================
def cadastrar_voz_funcionario(
    user_id: str,
    nome: str,
    audio_pcm16: bytes,
    sample_rate: int = SAMPLE_RATE,
) -> Tuple[str, int, str]:
    """
    1) salva WAV em disco
    2) extrai embedding
    3) salva no Postgres (funcionarios): embedding + audio_file_name

    Retorna:
      (filepath, funcionario_id, audio_file_name)
    """
    if not user_id:
        raise ValueError("user_id é obrigatório no cadastro de voz.")
    if not nome:
        raise ValueError("nome (balconista_id) é obrigatório no cadastro de voz.")
    if not audio_pcm16:
        raise ValueError("Áudio de cadastro vazio.")

    _ensure_dir(CADASTRO_DIR)

    audio_file_name = f"{nome}_{uuid.uuid4().hex}.wav"
    filepath = os.path.join(CADASTRO_DIR, audio_file_name)

    # Salva WAV
    _save_wav_pcm16(filepath, audio_pcm16, sr=sample_rate)

    # Extrai embedding
    emb = extrair_embedding(audio_pcm16, sample_rate=sample_rate)
    if emb is None:
        raise RuntimeError("Falha ao extrair embedding do áudio.")

    embedding_blob = _emb_to_bytes(emb)

    # Salva no Postgres + armazena audio_file_name
    funcionario_id = db.upsert_funcionario_por_nome(
        user_id=user_id,
        nome=nome,
        embedding_blob=embedding_blob,
        audio_file_name=audio_file_name,
    )

    print(f"[CADASTRO_VOZ] OK user_id={user_id} nome={nome} -> funcionario_id={funcionario_id} file={audio_file_name}")
    return filepath, int(funcionario_id), audio_file_name


def similaridade_coseno(vec1: np.ndarray, vec2: np.ndarray) -> float:
    v1 = vec1 / (np.linalg.norm(vec1) + 1e-9)
    v2 = vec2 / (np.linalg.norm(vec2) + 1e-9)
    return float(np.dot(v1, v2))

def classificar_por_scores(
    emb_atendimento: np.ndarray,
    perfis: Dict[str, np.ndarray],
    threshold: float = SEGMENT_THRESHOLD_DEFAULT,
    margin: float = SEGMENT_MARGIN_DEFAULT,
) -> Tuple[Optional[str], float, List[Tuple[str, float]]]:
    if emb_atendimento is None or not perfis:
        return None, 0.0, []

    scores: List[Tuple[str, float]] = []
    for key, emb_ref in perfis.items():
        scores.append((key, similaridade_coseno(emb_atendimento, emb_ref)))

    scores.sort(key=lambda x: x[1], reverse=True)
    top1_id, top1_score = scores[0]
    top2_score = scores[1][1] if len(scores) > 1 else -1.0

    if top1_score < threshold or (top1_score - top2_score) < margin:
        return None, top1_score, scores

    return top1_id, top1_score, scores

def agrupar_segmentos_por_speaker(diarization: List[dict]) -> Dict[str, dict]:
    agrupado: Dict[str, dict] = {}
    for seg in diarization:
        spk = seg["speaker"]
        start = float(seg["start"])
        end = float(seg["end"])
        dur = max(0.0, end - start)
        if dur <= 0:
            continue
        if spk not in agrupado:
            agrupado[spk] = {"duracao_total": 0.0, "segmentos": []}
        agrupado[spk]["duracao_total"] += dur
        agrupado[spk]["segmentos"].append((start, end))
    return agrupado

def escolher_speaker_balconista(diarization: List[dict]) -> Optional[str]:
    agrupado = agrupar_segmentos_por_speaker(diarization)
    if not agrupado:
        return None
    best_spk, _info = max(agrupado.items(), key=lambda kv: kv[1]["duracao_total"])
    return best_spk

def extrair_audio_de_speaker(
    audio_pcm16: bytes,
    diarization: List[dict],
    speaker_label: str,
    sample_rate: int = SAMPLE_RATE,
) -> bytes:
    agrupado = agrupar_segmentos_por_speaker(diarization)
    if speaker_label not in agrupado:
        return b""

    audio_np = np.frombuffer(audio_pcm16, dtype=np.int16)
    n_samples = len(audio_np)
    trechos = []

    for (start, end) in agrupado[speaker_label]["segmentos"]:
        start_idx = max(0, int(start * sample_rate))
        end_idx = min(n_samples, int(end * sample_rate))
        if end_idx > start_idx:
            trechos.append(audio_np[start_idx:end_idx])

    if not trechos:
        return b""

    return np.concatenate(trechos).astype(np.int16).tobytes()

# =========================
# Streaming Voice Identity (Restored/Implemented)
# =========================
class StreamVoiceIdentifier:
    """
    Mantém estado ou cache de perfis para identificar locutor em tempo real
    conforme chegam chunks de áudio (segmentos do VAD).
    """
    def __init__(self):
        # Cache simples de perfis carregados: {balcao_id: {nome: embedding, ...}}
        # Em prod, teria expiração/LRU.
        self.profiles_cache: Dict[str, Dict[str, np.ndarray]] = {}
        self.cache_lock = threading.Lock()

    def _load_profiles(self, balcao_id: str):
        """Carrega do banco se não tiver no cache."""
        # Se quiser forçar reload sempre, comente o if
        if balcao_id in self.profiles_cache:
            return self.profiles_cache[balcao_id]

        rows = db.listar_funcionarios_por_balcao(balcao_id)
        profiles = {}
        for r in rows:
            nome = r['nome']
            emb_blob = r['embedding']
             # converter bytes do banco (bytea) para numpy
            if emb_blob:
                 emb_arr = np.frombuffer(emb_blob, dtype=np.float32)
                 profiles[nome] = emb_arr
        
        with self.cache_lock:
            self.profiles_cache[balcao_id] = profiles
        return profiles

    def add_segment(self, balcao_id: str, speech_chunk: bytes) -> Tuple[Optional[str], float]:
        """
        Processa um chunk de fala (VAD True) e tenta identificar.
        Retorna (nome_funcionario, score).
        """
        # 1. Extrair embedding do chunk atual
        emb_test = extrair_embedding(speech_chunk)
        if emb_test is None:
            return None, 0.0

        # 2. Carregar perfis do balcão
        profiles = self._load_profiles(balcao_id)
        if not profiles:
            return None, 0.0

        # 3. Comparar
        # classificar_por_scores retorna (top1_id, top1_score, list_scores)
        top_id, top_score, _ = classificar_por_scores(emb_test, profiles)

        return top_id, top_score
