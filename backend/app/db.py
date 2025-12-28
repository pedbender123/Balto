import sqlite3
import os
import uuid
from datetime import datetime

DB_FILE = os.environ.get("DB_FILE", "registro.db")

def inicializar_db():
    db_dir = os.path.dirname(DB_FILE)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
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
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        nome TEXT,
        embedding BLOB,
        criado_em DATETIME,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """)

    # 4. Tabela Interações (Analytics Expandido)
    # Verifica colunas novas para migração
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS interacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        balcao_id TEXT,
        timestamp DATETIME,
        transcricao_completa TEXT,
        recomendacao_gerada TEXT,
        resultado_feedback TEXT,
        funcionario_id INTEGER,
        modelo_stt TEXT,
        custo_estimado REAL,
        FOREIGN KEY (balcao_id) REFERENCES balcoes (balcao_id)
    )
    """)
    
    # Migração simples (adiciona colunas se faltarem)
    try:
        cursor.execute("SELECT modelo_stt FROM interacoes LIMIT 1")
    except sqlite3.OperationalError:
        print("[DB] Migrando tabela interacoes...")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN funcionario_id INTEGER")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN modelo_stt TEXT")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN custo_estimado REAL")
    
    conn.commit()
    conn.close()

# --- Funções Auxiliares ---

def validate_api_key(api_key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balcao_id FROM balcoes WHERE api_key = ?", (api_key,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

def registrar_interacao(balcao_id, transcricao, recomendacao, resultado, funcionario_id=None, modelo_stt=None, custo=0.0):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO interacoes (balcao_id, timestamp, transcricao_completa, recomendacao_gerada, resultado_feedback, funcionario_id, modelo_stt, custo_estimado)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (balcao_id, datetime.now(), transcricao, recomendacao, resultado, funcionario_id, modelo_stt, custo))
    conn.commit()
    conn.close()

def adicionar_funcionario(user_id, nome, embedding_blob):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO funcionarios (user_id, nome, embedding, criado_em) VALUES (?, ?, ?, ?)",
                   (user_id, nome, embedding_blob, datetime.now()))
    conn.commit()
    conn.close()

def listar_funcionarios_por_balcao(balcao_id):
    """Retorna lista de funcionarios do dono do balcão."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Join para achar o user_id através do balcao_id
    query = """
    SELECT f.id, f.nome, f.embedding 
    FROM funcionarios f
    JOIN balcoes b ON f.user_id = b.user_id
    WHERE b.balcao_id = ?
    """
    cursor.execute(query, (balcao_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows