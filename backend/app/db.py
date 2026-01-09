import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import numpy as np
from psycopg2.extensions import register_adapter, AsIs

# Adaptadores para NumPy (evita erro can't adapt type 'numpy.float32')
def addapt_numpy_float(numpy_float):
    return AsIs(numpy_float)

def addapt_numpy_int(numpy_int):
    return AsIs(numpy_int)

register_adapter(np.float32, addapt_numpy_float)
register_adapter(np.float64, addapt_numpy_float)
register_adapter(np.int64, addapt_numpy_int)


# Configuração via variáveis de ambiente
DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
DB_PORT = os.environ.get("POSTGRES_PORT", "5432")
DB_NAME = os.environ.get("POSTGRES_DB", "balto_db")
DB_USER = os.environ.get("POSTGRES_USER", "balto_user")
DB_PASS = os.environ.get("POSTGRES_PASSWORD", "baltopassword123")

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )
    return conn

def inicializar_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Tabela Users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        razao_social TEXT,
        telefone TEXT,
        codigo_6_digitos TEXT UNIQUE
    )
    """)
    
    # 2. Tabela Balcões
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS balcoes (
        balcao_id TEXT PRIMARY KEY,
        user_id TEXT,
        nome_balcao TEXT,
        api_key TEXT UNIQUE,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """)

    # 3. Tabela Funcionários (Fase 3 - Speaker ID)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS funcionarios (
        id SERIAL PRIMARY KEY,
        user_id TEXT,
        nome TEXT,
        embedding BYTEA,
        criado_em TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """)

    # 4. Tabela Interações (Analytics Expandido)
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
        ts_transcription_ready TIMESTAMP,
        ts_ai_request TIMESTAMP,
        ts_ai_response TIMESTAMP,
        FOREIGN KEY (balcao_id) REFERENCES balcoes (balcao_id)
    )
    """)

    # Migração segura para adicionar colunas novas se não existirem
    try:
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS snr REAL")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS grok_raw_response TEXT")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS ts_audio_received TIMESTAMP")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS ts_transcription_ready TIMESTAMP")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS ts_ai_request TIMESTAMP")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN IF NOT EXISTS ts_ai_response TIMESTAMP")
        conn.commit()
    except Exception as e:
        print(f"[DB WARN] Erro ao migrar schema (colunas): {e}")
        conn.rollback()
    
    conn.commit()
    conn.close()

# --- Funções Auxiliares ---

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

def registrar_interacao(balcao_id, transcricao, recomendacao, resultado, funcionario_id=None, modelo_stt=None, custo=0.0, snr=0.0, grok_raw=None,
                       ts_audio=None, ts_trans_ready=None, ts_ai_req=None, ts_ai_res=None):
    print(f"[DB] Tentando registrar interação para balcao={balcao_id}, SNR={snr:.2f}")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO interacoes (
            balcao_id, timestamp, transcricao_completa, recomendacao_gerada, resultado_feedback, 
            funcionario_id, modelo_stt, custo_estimado, snr, grok_raw_response,
            ts_audio_received, ts_transcription_ready, ts_ai_request, ts_ai_response
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            balcao_id, datetime.now(), transcricao, recomendacao, resultado, 
            funcionario_id, modelo_stt, float(custo), float(snr), grok_raw,
            ts_audio, ts_trans_ready, ts_ai_req, ts_ai_res
        ))
        conn.commit()
        conn.close()
        print(f"[DB] Interação registrada com sucesso (ID gerado implicitamente).")
    except Exception as e:
        print(f"[DB] ERRO CRÍTICO ao salvar interação: {e}")
        import traceback
        traceback.print_exc()

def listar_interacoes(limit=50):
    """Retorna as ultimas interacoes para o admin."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    query = """
    SELECT 
        i.id,
        i.timestamp,
        b.nome_balcao,
        i.transcricao_completa,
        i.recomendacao_gerada,
        i.modelo_stt
    FROM interacoes i
    LEFT JOIN balcoes b ON i.balcao_id = b.balcao_id
    ORDER BY i.timestamp DESC
    LIMIT %s
    """
    cursor.execute(query, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Converter datetime para string
    for row in rows:
        if row['timestamp']:
            row['timestamp'] = row['timestamp'].strftime("%d/%m/%Y %H:%M:%S")
            
    return rows

def adicionar_funcionario(user_id, nome, embedding_blob):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO funcionarios (user_id, nome, embedding, criado_em) VALUES (%s, %s, %s, %s)",
                   (user_id, nome, embedding_blob, datetime.now()))
    conn.commit()
    conn.close()

def listar_funcionarios_por_balcao(balcao_id):
    """Retorna lista de funcionarios do dono do balcão."""
    conn = get_db_connection()
    # Usando RealDictCursor para retornar dicionários compatíveis com o código anterior
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Join para achar o user_id através do balcao_id
    query = """
    SELECT f.id, f.nome, f.embedding 
    FROM funcionarios f
    JOIN balcoes b ON f.user_id = b.user_id
    WHERE b.balcao_id = %s
    """
    cursor.execute(query, (balcao_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_user_by_code(code):
    """Retorna user_id pelo código de 6 dígitos."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE codigo_6_digitos = %s", (code,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

def set_user_code(user_id, code):
    """Define o código de 6 dígitos para um usuário."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET codigo_6_digitos = %s WHERE user_id = %s", (code, user_id))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

def create_client(email, razao_social, telefone):
    """Cria um novo cliente (user) e gera código de 6 dígitos."""
    import uuid
    import random
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    user_id = str(uuid.uuid4())
    # Gera código unico (tentativa simples, em prod faria loop de colisao)
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
    """Cria um novo balcão e retorna (balcao_id, api_key)."""
    import uuid
    conn = get_db_connection()
    cursor = conn.cursor()
    
    balcao_id = str(uuid.uuid4())
    api_key = f"bk_{uuid.uuid4().hex}"
    
    # Verifica se já existe um balcão com esse nome para esse user (opcional, mas bom pra evitar duplicata)
    # Por simplificação, vamos permitir múltiplos por enquanto ou deixar o banco chiar se fosse unique.
    # Mas api_key é unique.
    
    cursor.execute("""
        INSERT INTO balcoes (balcao_id, user_id, nome_balcao, api_key)
        VALUES (%s, %s, %s, %s)
    """, (balcao_id, user_id, nome_balcao, api_key))
    
    conn.commit()
    conn.close()
    return balcao_id, api_key