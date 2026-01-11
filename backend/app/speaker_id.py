# Módulo de identificação de balconista por voz.
# - Usa embeddings de speaker via Resemblyzer
# - Salva perfis de voz em uma tabela SQLite no mesmo DB do sistema
#
# Cada balconista tem um "perfil de voz" (embedding médio).
# Você cadastra a voz chamando registrar_cadastro_voz()
# e identifica chamando identificar_balconista().

import json
import sqlite3
from typing import Dict, List, Tuple, Optional

import numpy as np

import os
import uuid
import wave

from app import db  # para pegar o caminho do arquivo SQLite (db.DB_FILE)
from resemblyzer import VoiceEncoder

SAMPLE_RATE = 16000
DEFAULT_THRESHOLD = 0.75  # similaridade mínima para não ser "não sei"
SEGMENT_THRESHOLD_DEFAULT = 0.78  # corte mínimo para aceitar uma frase
SEGMENT_MARGIN_DEFAULT = 0.06     # gap mínimo entre top1 e top2

# Encoder global de speaker (carrega uma vez só)
_encoder: VoiceEncoder | None = None

def get_encoder() -> VoiceEncoder:
    global _encoder
    if _encoder is None:
        _encoder = VoiceEncoder()  # carrega o modelo pré-treinado
    return _encoder


# ============================================================
# 1) Gestão da tabela no SQLite
# ============================================================

def _get_conn():
    """Abre conexão com o mesmo DB usado em db.py."""
    conn = sqlite3.connect(db.DB_FILE)
    return conn


def inicializar_tabela_speaker_profiles():
    """
    Cria tabela de perfis de voz caso não exista.
    Estrutura:
      - balconista_id: string (pk)
      - embedding: texto (JSON com lista de floats)
      - n_samples: número de exemplos usados para o perfil (média incremental)
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS speaker_profiles (
            balconista_id TEXT PRIMARY KEY,
            embedding TEXT NOT NULL,
            n_samples INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.commit()
    conn.close()


def _embedding_to_str(emb: np.ndarray) -> str:
    return json.dumps(emb.tolist())


def _str_to_embedding(s: str) -> np.ndarray:
    return np.array(json.loads(s), dtype=np.float32)


def carregar_perfis_balconistas() -> Dict[str, np.ndarray]:
    """
    Carrega todos os perfis de voz cadastrados.
    Retorna dict[balconista_id] = embedding (np.ndarray)
    """
    inicializar_tabela_speaker_profiles()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT balconista_id, embedding FROM speaker_profiles")
    rows = cur.fetchall()
    conn.close()

    perfis = {}
    for balconista_id, emb_str in rows:
        perfis[balconista_id] = _str_to_embedding(emb_str)
    return perfis


def _atualizar_centroide(balconista_id: str, novo_emb: np.ndarray):
    """
    Atualiza o perfil médio de um balconista com um novo embedding.
    Usa média incremental.
    """
    inicializar_tabela_speaker_profiles()
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT embedding, n_samples FROM speaker_profiles WHERE balconista_id = ?",
        (balconista_id,),
    )
    row = cur.fetchone()

    if row is None:
        # Primeiro exemplo desse balconista
        emb_str = _embedding_to_str(novo_emb)
        cur.execute(
            "INSERT INTO speaker_profiles (balconista_id, embedding, n_samples) VALUES (?, ?, ?)",
            (balconista_id, emb_str, 1),
        )
    else:
        emb_str_db, n_samples = row
        emb_antigo = _str_to_embedding(emb_str_db)
        n = int(n_samples)

        # média incremental
        emb_novo = (emb_antigo * n + novo_emb) / (n + 1)
        emb_str_novo = _embedding_to_str(emb_novo)
        cur.execute(
            "UPDATE speaker_profiles SET embedding = ?, n_samples = ? WHERE balconista_id = ?",
            (emb_str_novo, n + 1, balconista_id),
        )

    conn.commit()
    conn.close()


# ============================================================
# 2) Embeddings de áudio (simples com MFCC)
# ============================================================

def extrair_embedding(audio_pcm16: bytes, sample_rate: int = SAMPLE_RATE) -> Optional[np.ndarray]:
    """
    Gera embedding de speaker usando Resemblyzer.
    - Entrada: áudio PCM16 mono (16kHz), qualquer duração >= ~1s de fala.
    - Saída: vetor float32 (dimensão ~256) representando a voz.
    """
    if not audio_pcm16:
        return None

    # PCM16 -> float32 [-1, 1]
    audio_np = np.frombuffer(audio_pcm16, dtype=np.int16).astype(np.float32)
    if audio_np.size == 0:
        return None

    audio_np = audio_np / 32768.0

    # Se o audio estiver em outro sample_rate, aqui poderíamos resamplear,
    # mas no teu fluxo já é 16k, então vamos assumir isso.
    encoder = get_encoder()
    emb = encoder.embed_utterance(audio_np)
    # Garantir float32 numpy
    emb = np.array(emb, dtype=np.float32)
    return emb


def similaridade_coseno(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Similaridade de cosseno entre dois vetores."""
    v1 = vec1 / (np.linalg.norm(vec1) + 1e-9)
    v2 = vec2 / (np.linalg.norm(vec2) + 1e-9)
    return float(np.dot(v1, v2))

def classificar_por_scores(
    emb_atendimento: np.ndarray,
    perfis: Dict[str, np.ndarray],
    threshold: float = SEGMENT_THRESHOLD_DEFAULT,
    margin: float = SEGMENT_MARGIN_DEFAULT,
):

    """
    Dado um embedding de atendimento e os perfis (balconista_id -> emb),
    retorna:
      - pred_id: balconista_id ou None (quando "não sei")
      - top_score: score do top1
      - ranking: lista [(balconista_id, score), ...] ordenada desc
    """
    if emb_atendimento is None or not perfis:
        return None, 0.0, []

    scores = []
    for balconista_id, emb_ref in perfis.items():
        sim = similaridade_coseno(emb_atendimento, emb_ref)
        scores.append((balconista_id, sim))

    scores.sort(key=lambda x: x[1], reverse=True)

    if not scores:
        return None, 0.0, []

    top1_id, top1_score = scores[0]
    top2_score = scores[1][1] if len(scores) > 1 else -1.0

    # Regra de "não sei"
    if top1_score < threshold or (top1_score - top2_score) < margin:
        return None, top1_score, scores

    return top1_id, top1_score, scores


# ============================================================
# 3) Diarização: utilitários para lidar com trechos de speaker
# ============================================================

def agrupar_segmentos_por_speaker(diarization: List[dict]):
    """
    diarization: lista de dicts com pelo menos:
      - "speaker": label (string)
      - "start": início em segundos
      - "end": fim em segundos

    Retorna dict[speaker_label] = {"duracao_total": float, "segmentos": [(start, end), ...]}
    """
    agrupado = {}
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
    """
    Heurística simples:
      - Escolhe o speaker com maior tempo total de fala.
    """
    agrupado = agrupar_segmentos_por_speaker(diarization)
    if not agrupado:
        return None

    # speaker com maior duração total
    best_spk, _info = max(agrupado.items(), key=lambda kv: kv[1]["duracao_total"])
    return best_spk


def extrair_audio_de_speaker(
    audio_pcm16: bytes,
    diarization: List[dict],
    speaker_label: str,
    sample_rate: int = SAMPLE_RATE,
) -> bytes:
    """
    Pega o áudio completo (PCM16) e recorta/concatena apenas os trechos
    pertencentes ao 'speaker_label', com base na diarização.
    """
    agrupado = agrupar_segmentos_por_speaker(diarization)
    if speaker_label not in agrupado:
        return b""

    segmentos = agrupado[speaker_label]["segmentos"]

    audio_np = np.frombuffer(audio_pcm16, dtype=np.int16)
    n_samples = len(audio_np)

    trechos = []
    for (start, end) in segmentos:
        start_idx = int(start * sample_rate)
        end_idx = int(end * sample_rate)
        start_idx = max(0, start_idx)
        end_idx = min(n_samples, end_idx)
        if end_idx > start_idx:
            trechos.append(audio_np[start_idx:end_idx])

    if not trechos:
        return b""

    audio_conc = np.concatenate(trechos)
    return audio_conc.astype(np.int16).tobytes()


# ============================================================
# 4) API pública do módulo
# ============================================================

def registrar_cadastro_voz(balconista_id: str, audio_pcm16: bytes, sample_rate: int = SAMPLE_RATE):
    """
    Usa um áudio de cadastro (sem cliente, só a voz do balconista) para atualizar
    o perfil de voz dele.
    """
    emb = extrair_embedding(audio_pcm16, sample_rate=sample_rate)
    if emb is None:
        raise ValueError("Áudio de cadastro vazio ou inválido.")
    _atualizar_centroide(balconista_id, emb)


def identificar_balconista(
    audio_pcm16: bytes,
    diarization: List[dict],
    threshold: float = DEFAULT_THRESHOLD,
    sample_rate: int = SAMPLE_RATE,
) -> Tuple[Optional[str], float]:
    """
    Identifica o balconista mais provável para o atendimento.

    Parâmetros:
      - audio_pcm16: áudio completo do atendimento (PCM16 s16le mono)
      - diarization: lista de segmentos da ElevenLabs
      - threshold: similaridade mínima para aceitar um balconista

    Retorna:
      (balconista_id_ou_None, similaridade_max)
    """
    # 1) qual speaker da diarização é o balconista? (heurística da maior duração)
    speaker_label = escolher_speaker_balconista(diarization)
    if not speaker_label:
        return None, 0.0

    # 2) extrair somente o áudio desse speaker
    audio_spk = extrair_audio_de_speaker(audio_pcm16, diarization, speaker_label, sample_rate)
    if not audio_spk:
        return None, 0.0

    # 3) gerar embedding desse atendimento
    emb_atendimento = extrair_embedding(audio_spk, sample_rate=sample_rate)
    if emb_atendimento is None:
        return None, 0.0

    # 4) carregar perfis
    perfis = carregar_perfis_balconistas()
    if not perfis:
        return None, 0.0

    # 5) usar a mesma regra de decisão (threshold + margin)
    pred_id, top_score, _ranking = classificar_por_scores(
        emb_atendimento,
        perfis,
        threshold=threshold,    # vem do parâmetro da função (DEFAULT_THRESHOLD ou override)
        # margin: usa o default SEGMENT_MARGIN_DEFAULT,
        # a menos que no futuro queira expor isso também como parâmetro/env
    )

    return pred_id, top_score


# Diretório padrão para salvar áudios de cadastro
CADASTRO_DIR = os.path.join(os.path.dirname(__file__), "audio_dumps", "cadastros_voz")

def salvar_arquivo_cadastro_e_registrar(
    balconista_id: str,
    audio_pcm16: bytes,
    sample_rate: int = SAMPLE_RATE,
) -> str:
    """
    Salva o áudio de cadastro em disco (.wav) e atualiza o perfil de voz
    do balconista no banco (speaker_profiles).

    Retorna o caminho do arquivo salvo.
    """
    if not audio_pcm16:
        raise ValueError("Áudio de cadastro vazio.")

    os.makedirs(CADASTRO_DIR, exist_ok=True)

    filename = f"{balconista_id}_{uuid.uuid4().hex}.wav"
    filepath = os.path.join(CADASTRO_DIR, filename)

    # Salva WAV em disco
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_pcm16)

    # Atualiza o perfil de voz no banco
    registrar_cadastro_voz(balconista_id, audio_pcm16, sample_rate=sample_rate)

    print(f"[CADASTRO_VOZ] Arquivo salvo em: {filepath}")
    print(f"[CADASTRO_VOZ] Perfil de voz atualizado para balconista_id='{balconista_id}'")

    return filepath



# ============================================================
# 5) Versão streaming: acumula segmentos de fala e identifica
# ============================================================

# Lê configs de ambiente COM valores padrão sensatos
SPEAKER_ID_ENABLED_DEFAULT = os.environ.get("SPEAKER_ID_ENABLED", "0") == "1"
SPEAKER_ID_THRESHOLD_DEFAULT = float(os.environ.get("SPEAKER_ID_THRESHOLD", str(DEFAULT_THRESHOLD)))
SPEAKER_ID_MIN_DURATION_DEFAULT = float(os.environ.get("SPEAKER_ID_MIN_DURATION", "10.0"))  # seg


class StreamVoiceIdentifier:
    """
    Classe para uso em streaming:
      - Você vai chamando add_segment() com cada speech_segment (PCM16 16k)
      - Ela acumula no buffer interno
      - Quando tiver duração suficiente, chama identificar_balconista()
      - Guarda o primeiro resultado (para não ficar reclassificando toda hora)

    Uso típico no server.py:
      
      voice_tracker = speaker_id.StreamVoiceIdentifier()
      ...
      if speech_segment:
          voice_tracker.add_segment(balcao_id, speech_segment)
    """

    def __init__(
        self,
        enabled: bool | None = None,
        threshold: float | None = None,
        min_duration: float | None = None,
    ):
        self.enabled = SPEAKER_ID_ENABLED_DEFAULT if enabled is None else enabled
        self.threshold = SPEAKER_ID_THRESHOLD_DEFAULT if threshold is None else threshold
        self.min_duration = SPEAKER_ID_MIN_DURATION_DEFAULT if min_duration is None else min_duration

        self._buffer = bytearray()      # PCM16 acumulado
        self.balconista_id = None       # resultado já identificado
        self.score = None               # score da identificação

    def add_segment(self, balcao_id: str, speech_segment: bytes):
        """
        Alimenta o tracker com mais um segmento de fala.
        Retorna (balconista_id, score) SOMENTE na primeira vez que conseguir identificar
        com a duração mínima. Nas chamadas seguintes, normalmente retorna (None, None).
        """
        if not self.enabled:
            return None, None

        if not speech_segment:
            return None, None

        # Se já identificou uma vez, não faz mais nada
        if self.balconista_id is not None:
            return None, None

        # Acumula no buffer
        self._buffer.extend(speech_segment)

        # Calcula duração total em segundos (len(bytes) / 2 = amostras; / SR = segundos)
        duracao_total_seg = len(self._buffer) / (2 * SAMPLE_RATE)

        if duracao_total_seg < self.min_duration:
            # ainda não tem áudio suficiente
            return None, None

        # Por enquanto usamos diarização "fake": um único speaker no áudio inteiro.
        diarization_fake = [
            {
                "speaker": "spk_0",
                "start": 0.0,
                "end": duracao_total_seg,
            }
        ]

        try:
            balconista_pred, score = identificar_balconista(
                audio_pcm16=bytes(self._buffer),
                diarization=diarization_fake,
                threshold=self.threshold,
                sample_rate=SAMPLE_RATE,
            )
            self.balconista_id = balconista_pred
            self.score = score

            print(f"[{balcao_id}] Voice-ID streaming -> {balconista_pred} (score={score:.3f})")
            return balconista_pred, score

        except Exception as e:
            print(f"[{balcao_id}] Erro em StreamVoiceIdentifier.add_segment: {e}")
            return None, None