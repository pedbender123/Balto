# backend/app/db.py

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import numpy as np
from psycopg2.extensions import register_adapter, AsIs

# =========================
# Adapters NumPy (evita "can't adapt type numpy.float32")
# =========================
def addapt_numpy_float(numpy_float):
    return AsIs(numpy_float)

def addapt_numpy_int(numpy_int):
    return AsIs(numpy_int)

register_adapter(np.float32, addapt_numpy_float)
register_adapter(np.float64, addapt_numpy_float)
register_adapter(np.int64, addapt_numpy_int)

# =========================
# Config via env
# =========================
DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
DB_PORT = os.environ.get("POSTGRES_PORT", "5432")
DB_NAME = os.environ.get("POSTGRES_DB", "balto_db")
DB_USER = os.environ.get("POSTGRES_USER", "balto_user")
DB_PASS = os.environ.get("POSTGRES_PASSWORD", "baltopassword123")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

# =========================
# Schema
# =========================
def inicializar_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1) Users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        razao_social TEXT,
        telefone TEXT,
        codigo_6_digitos TEXT UNIQUE
    )
    """)

    # 2) Balcões
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS balcoes (
        balcao_id TEXT PRIMARY KEY,
        user_id TEXT,
        nome_balcao TEXT,
        api_key TEXT UNIQUE,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """)

    # 3) Funcionários (Speaker ID)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS funcionarios (
        id SERIAL PRIMARY KEY,
        user_id TEXT,
        nome TEXT,
        audio_file_name TEXT,
        embedding BYTEA,
        criado_em TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """)
    # Migração segura (para bancos antigos que não tinham a coluna)
    cursor.execute("ALTER TABLE funcionarios ADD COLUMN IF NOT EXISTS audio_file_name TEXT")

    # 4) Interações
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS interacoes (
        id SERIAL PRIMARY KEY,
        balcao_id TEXT,
        timestamp TIMESTAMP,
        transcricao_completa TEXT,
        recomendacao_gerada TEXT,
        resultado_feedback TEXT,
        funcionario_id INTEGER,
        modelo_stt TEXT,
        custo_estimado REAL,
        snr REAL,
        grok_raw_response TEXT,
        ts_audio_received TIMESTAMP,
        ts_transcription_sent TIMESTAMP,
        ts_transcription_ready TIMESTAMP,
        ts_ai_request TIMESTAMP,
        ts_ai_response TIMESTAMP,
        ts_client_sent TIMESTAMP,
        FOREIGN KEY (balcao_id) REFERENCES balcoes (balcao_id)
    )
    """)

    # Migração segura das colunas de interacoes (sem duplicar ALTERs)
    try:
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS snr REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS grok_raw_response TEXT")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS ts_audio_received TIMESTAMP")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS ts_transcription_sent TIMESTAMP")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS ts_transcription_ready TIMESTAMP")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS ts_ai_request TIMESTAMP")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS ts_ai_response TIMESTAMP")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS ts_client_sent TIMESTAMP")
        # New: Speaker Data
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS speaker_data TEXT")

        # Colunas das características do trecho/áudio para análise de melhoria
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS segment_duration_ms INTEGER")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS segment_bytes INTEGER")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS frames_len INTEGER")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS cut_reason TEXT")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS silence_frames_count_at_cut INTEGER")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS noise_level_start REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS noise_level_end REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS dynamic_threshold_start REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS dynamic_threshold_end REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS energy_rms_mean REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS energy_rms_max REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS peak_dbfs REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS clipping_ratio REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS dc_offset REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS zcr REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS spectral_centroid REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS band_energy_low REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS band_energy_mid REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS band_energy_high REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS snr_estimate REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS audio_cleaner_gain_db REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS threshold_multiplier REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS min_energy_threshold REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS alpha REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS vad_aggressiveness INTEGER")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS silence_frames_needed INTEGER")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS pre_roll_len INTEGER")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS segment_limit_frames INTEGER")

        conn.commit()
    except Exception as e:
        print(f"[DB WARN] Erro ao migrar schema (interacoes): {e}")
        conn.rollback()

    conn.commit()
    conn.close()

# =========================
# Auxiliares
# =========================
def validate_api_key(api_key):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT balcao_id FROM balcoes WHERE api_key = %s", (api_key,))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else None
    except Exception as e:
        print(f"Erro ao validar API Key: {e}")
        return None

def get_user_id_by_balcao(balcao_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM balcoes WHERE balcao_id = %s", (balcao_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def get_user_by_code(code):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE codigo_6_digitos = %s", (code,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

def set_user_code(user_id, code):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET codigo_6_digitos = %s WHERE user_id = %s", (code, user_id))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

# =========================
# Clientes / balcões
# =========================
def get_user_by_email(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

def get_balcao_by_name(user_id, nome_balcao):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balcao_id, api_key FROM balcoes WHERE user_id = %s AND nome_balcao = %s", (user_id, nome_balcao))
    res = cursor.fetchone()
    conn.close()
    return res if res else None

def create_client(email, razao_social, telefone):
    import uuid
    import random

    conn = get_db_connection()
    cursor = conn.cursor()

    user_id = str(uuid.uuid4())
    codigo = str(random.randint(100000, 999999))

    try:
        cursor.execute("""
            INSERT INTO users (user_id, email, razao_social, telefone, codigo_6_digitos)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, email, razao_social, telefone, codigo))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

    conn.close()
    return codigo

def create_balcao(user_id, nome_balcao):
    import uuid
    conn = get_db_connection()
    cursor = conn.cursor()

    balcao_id = str(uuid.uuid4())
    api_key = f"bk_{uuid.uuid4().hex}"

    cursor.execute("""
        INSERT INTO balcoes (balcao_id, user_id, nome_balcao, api_key)
        VALUES (%s, %s, %s, %s)
    """, (balcao_id, user_id, nome_balcao, api_key))

    conn.commit()
    conn.close()
    return balcao_id, api_key

# =========================
# Funcionários (cadastro de voz)
# =========================
def upsert_funcionario_por_nome(
    user_id: str,
    nome: str,
    embedding_blob: bytes,
    audio_file_name: str | None = None,
):
    """
    Se já existe (user_id, nome), atualiza embedding e audio_file_name.
    Se não existe, cria.
    Retorna id (SERIAL).

    Obs: sem UNIQUE no banco por enquanto (você garantirá manualmente).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM funcionarios WHERE user_id = %s AND nome = %s",
        (user_id, nome)
    )
    row = cursor.fetchone()

    now = datetime.now()

    if row:
        func_id = row[0]
        cursor.execute(
            """
            UPDATE funcionarios
            SET embedding = %s,
                audio_file_name = COALESCE(%s, audio_file_name),
                criado_em = %s
            WHERE id = %s
            """,
            (embedding_blob, audio_file_name, now, func_id)
        )
    else:
        cursor.execute(
            """
            INSERT INTO funcionarios (user_id, nome, audio_file_name, embedding, criado_em)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, nome, audio_file_name, embedding_blob, now)
        )
        func_id = cursor.fetchone()[0]

    conn.commit()
    conn.close()
    return func_id

def listar_funcionarios_por_user(user_id: str):
    """
    Retorna lista de funcionarios do user:
      [{id, nome, audio_file_name, embedding}, ...]
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        "SELECT id, nome, audio_file_name, embedding FROM funcionarios WHERE user_id = %s",
        (user_id,)
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def listar_funcionarios_por_balcao(balcao_id: str):
    """
    Retorna lista de funcionarios do dono do balcão (via join balcoes -> user_id).
    Útil se algum ponto do sistema ainda identifica por balcao_id.
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    query = """
    SELECT f.id, f.nome, f.audio_file_name, f.embedding
    FROM funcionarios f
    JOIN balcoes b ON f.user_id = b.user_id
    WHERE b.balcao_id = %s
    """
    cursor.execute(query, (balcao_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

# =========================
# Interações / admin (VERSÃO COM TEMPOS EXTRAS)
# =========================
def registrar_interacao(
    balcao_id,
    transcricao,
    recomendacao,
    resultado,
    funcionario_id=None,
    modelo_stt=None,
    custo=0.0,
    snr=0.0,
    grok_raw=None,
    ts_audio=None,
    ts_trans_sent=None,
    ts_trans_ready=None,
    ts_ai_req=None,
    ts_ai_res=None,
    ts_client=None,
    speaker_data=None,
    audio_metrics=None
):
    audio_metrics = audio_metrics or {}
    print(f"[DB] Tentando registrar interação para balcao={balcao_id}, SNR={snr:.2f}")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO interacoes (
            balcao_id, timestamp, transcricao_completa, recomendacao_gerada, resultado_feedback,
            funcionario_id, modelo_stt, custo_estimado, snr, grok_raw_response,
            ts_audio_received, ts_transcription_sent, ts_transcription_ready,
            ts_ai_request, ts_ai_response, ts_client_sent, speaker_data,

            segment_duration_ms, segment_bytes, frames_len, cut_reason, silence_frames_count_at_cut,
            noise_level_start, noise_level_end, dynamic_threshold_start, dynamic_threshold_end,
            energy_rms_mean, energy_rms_max,
            peak_dbfs, clipping_ratio, dc_offset, zcr, spectral_centroid,
            band_energy_low, band_energy_mid, band_energy_high,
            snr_estimate, audio_cleaner_gain_db,
            threshold_multiplier, min_energy_threshold, alpha, vad_aggressiveness,
            silence_frames_needed, pre_roll_len, segment_limit_frames
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,

            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s
        )
        """, (
            balcao_id, datetime.now(), transcricao, recomendacao, resultado,
            funcionario_id, modelo_stt, float(custo), float(snr), grok_raw,
            ts_audio, ts_trans_sent, ts_trans_ready,
            ts_ai_req, ts_ai_res, ts_client, speaker_data,

            audio_metrics.get("segment_duration_ms"),
            audio_metrics.get("segment_bytes"),
            audio_metrics.get("frames_len"),
            audio_metrics.get("cut_reason"),
            audio_metrics.get("silence_frames_count_at_cut"),

            audio_metrics.get("noise_level_start"),
            audio_metrics.get("noise_level_end"),
            audio_metrics.get("dynamic_threshold_start"),
            audio_metrics.get("dynamic_threshold_end"),

            audio_metrics.get("energy_rms_mean"),
            audio_metrics.get("energy_rms_max"),

            audio_metrics.get("peak_dbfs"),
            audio_metrics.get("clipping_ratio"),
            audio_metrics.get("dc_offset"),
            audio_metrics.get("zcr"),
            audio_metrics.get("spectral_centroid"),

            audio_metrics.get("band_energy_low"),
            audio_metrics.get("band_energy_mid"),
            audio_metrics.get("band_energy_high"),

            audio_metrics.get("snr_estimate"),
            audio_metrics.get("audio_cleaner_gain_db"),

            audio_metrics.get("threshold_multiplier"),
            audio_metrics.get("min_energy_threshold"),
            audio_metrics.get("alpha"),
            audio_metrics.get("vad_aggressiveness"),

            audio_metrics.get("silence_frames_needed"),
            audio_metrics.get("pre_roll_len"),
            audio_metrics.get("segment_limit_frames"),
        ))
        conn.commit()
        conn.close()
        print("[DB] Interação registrada com sucesso.")
    except Exception as e:
        print(f"[DB] ERRO CRÍTICO ao salvar interação: {e}")
        import traceback
        traceback.print_exc()

def listar_interacoes(limit=50):
    """Retorna as últimas interações para o admin (com tempos extras)."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    query = """
    SELECT
        i.id,
        i.timestamp,
        b.nome_balcao,
        i.transcricao_completa,
        i.recomendacao_gerada,
        i.modelo_stt,
        i.ts_audio_received,
        i.ts_transcription_sent,
        i.ts_transcription_ready,
        i.ts_ai_request,
        i.ts_ai_response,
        i.ts_client_sent
    FROM interacoes i
    LEFT JOIN balcoes b ON i.balcao_id = b.balcao_id
    ORDER BY i.timestamp DESC
    LIMIT %s
    """
    cursor.execute(query, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Converter datetimes para strings amigáveis
    for row in rows:
        if row.get("timestamp"):
            row["timestamp"] = row["timestamp"].strftime("%d/%m/%Y %H:%M:%S")

        for field in [
            "ts_audio_received",
            "ts_transcription_sent",
            "ts_transcription_ready",
            "ts_ai_request",
            "ts_ai_response",
            "ts_client_sent",
        ]:
            if row.get(field):
                row[field] = row[field].strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm
            else:
                row[field] = "-"

    return rows
