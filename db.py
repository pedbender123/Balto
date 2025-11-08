import sqlite3
import os
from datetime import datetime

# Pega o caminho do DB do .env, com um padrão
DB_FILE = os.environ.get("DB_FILE", "registro.db")

def inicializar_db():
    """
    Cria a tabela de interações se ela não existir.
    Baseado no schema da fonte 127.
    """
    # Garante que o diretório de dados exista
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Schema da tabela (fonte 127)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS interacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME NOT NULL,
        transcricao_completa TEXT,
        recomendacao_gerada TEXT,
        resultado_feedback TEXT 
    )
    """)
    conn.commit()
    conn.close()
    print(f"Banco de dados inicializado em {DB_FILE}")

def registrar_interacao(transcricao: str, recomendacao: str, resultado: str):
    """
    Insere um registro completo da interação.
    Baseado na fonte 128.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        timestamp = datetime.now()
        
        # Insere os dados (fonte 129)
        cursor.execute("""
        INSERT INTO interacoes (timestamp, transcricao_completa, recomendacao_gerada, resultado_feedback)
        VALUES (?, ?, ?, ?)
        """, (timestamp, transcricao, recomendacao, resultado))
        
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"Erro ao registrar interação no DB: {e}")