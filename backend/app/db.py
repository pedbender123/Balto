import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

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
        FOREIGN KEY (balcao_id) REFERENCES balcoes (balcao_id)
    )
    """)
    
    # Migração simples (adiciona colunas se faltarem) - Postgres requer verificação diferente
    # Simplificação: assumindo criação correta. Se precisar migrar colunas em pg, usamos alter table if not exists ou verificação de schema.
    # Por enquanto, mantendo simples para a criação inicial.
    
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

def registrar_interacao(balcao_id, transcricao, recomendacao, resultado, funcionario_id=None, modelo_stt=None, custo=0.0):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO interacoes (balcao_id, timestamp, transcricao_completa, recomendacao_gerada, resultado_feedback, funcionario_id, modelo_stt, custo_estimado)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (balcao_id, datetime.now(), transcricao, recomendacao, resultado, funcionario_id, modelo_stt, custo))
    conn.commit()
    conn.close()

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