import sqlite3
import os
import uuid
import random
from datetime import datetime

# Pega o caminho do DB do .env, com um padrão
DB_FILE = os.environ.get("DB_FILE", "registro.db")

def _generate_6_digit_code(cursor):
    """
    Helper interno para gerar um código de 6 dígitos numérico único
    para um novo usuário.
    """
    while True:
        # Gera um código como string, ex: "123456"
        code = str(random.randint(100000, 999999))
        # Verifica se já existe na tabela de usuários
        cursor.execute("SELECT 1 FROM users WHERE codigo_6_digitos = ?", (code,))
        if cursor.fetchone() is None:
            # Se não existir, retorna o código
            return code

def inicializar_db():
    """
    Cria as tabelas (se não existirem) para usuários, balcões e interações.
    """
    # Garante que o diretório de dados exista
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Tabela 1: Usuários (Clientes, e.g., redes de farmácia)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        razao_social TEXT NOT NULL,
        telefone TEXT,
        codigo_6_digitos TEXT UNIQUE NOT NULL
    )
    """)
    
    # Tabela 2: Balcões (Pontos de Venda/Conexões)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS balcoes (
        balcao_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        nome_balcao TEXT NOT NULL,
        api_key TEXT UNIQUE NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """)

    # Tabela 3: Interações (Modificada para incluir balcao_id)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS interacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        balcao_id TEXT NOT NULL,
        timestamp DATETIME NOT NULL,
        transcricao_completa TEXT,
        recomendacao_gerada TEXT,
        resultado_feedback TEXT,
        FOREIGN KEY (balcao_id) REFERENCES balcoes (balcao_id)
    )
    """)
    
    # Bloco de migração: Adiciona a coluna 'balcao_id' se ela não existir
    # Isso evita que o banco de dados antigo quebre
    try:
        cursor.execute("SELECT balcao_id FROM interacoes LIMIT 1")
    except sqlite3.OperationalError:
        print("Migrando tabela 'interacoes', adicionando 'balcao_id'...")
        cursor.execute("ALTER TABLE interacoes ADD COLUMN balcao_id TEXT")
    
    conn.commit()
    conn.close()
    print(f"Banco de dados inicializado em {DB_FILE}")

def add_user(email: str, razao_social: str, telefone: str):
    """
    Cadastra um novo usuário (cliente).
    Retorna o código de 6 dígitos ou um erro.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        user_id = str(uuid.uuid4())
        code = _generate_6_digit_code(cursor)
        
        cursor.execute("""
        INSERT INTO users (user_id, email, razao_social, telefone, codigo_6_digitos)
        VALUES (?, ?, ?, ?, ?)
        """, (user_id, email, razao_social, telefone, code))
        
        conn.commit()
        conn.close()
        # Sucesso
        return {"success": True, "codigo": code}
    except sqlite3.IntegrityError as e:
        # Erro de 'UNIQUE' (email ou código já existe)
        conn.close()
        return {"success": False, "error": f"Email ou código já existe: {e}"}
    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}

def add_balcao(nome_balcao: str, user_codigo: str):
    """
    Cadastra um novo balcão, atrelando-o a um usuário
    pelo código de 6 dígitos.
    Retorna a API key do balcão ou um erro.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 1. Encontrar o user_id pelo código de 6 dígitos
        cursor.execute("SELECT user_id FROM users WHERE codigo_6_digitos = ?", (user_codigo,))
        result = cursor.fetchone()
        
        if result is None:
            conn.close()
            return {"success": False, "error": "Código de usuário inválido"}
            
        user_id = result[0]
        
        # 2. Gerar dados do balcão
        balcao_id = str(uuid.uuid4())
        api_key = str(uuid.uuid4()) # Chave para autenticação do WebSocket
        
        cursor.execute("""
        INSERT INTO balcoes (balcao_id, user_id, nome_balcao, api_key)
        VALUES (?, ?, ?, ?)
        """, (balcao_id, user_id, nome_balcao, api_key))
        
        conn.commit()
        conn.close()
        # Sucesso
        return {"success": True, "api_key": api_key}
        
    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}

def validate_api_key(api_key: str):
    """
    Valida uma API key e retorna o ID do balcão (balcao_id) se for válida.
    Retorna None se inválida.
    """
    if not api_key:
        return None
        
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT balcao_id FROM balcoes WHERE api_key = ?", (api_key,))
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            return result[0] # Retorna o balcao_id
        return None
        
    except Exception as e:
        print(f"Erro ao validar API key: {e}")
        return None

def registrar_interacao(balcao_id: str, transcricao: str, recomendacao: str, resultado: str):
    """
    Insere um registro completo da interação, agora com balcao_id.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        timestamp = datetime.now()
        
        # Insere os dados (fonte 129)
        cursor.execute("""
        INSERT INTO interacoes (balcao_id, timestamp, transcricao_completa, recomendacao_gerada, resultado_feedback)
        VALUES (?, ?, ?, ?, ?)
        """, (balcao_id, timestamp, transcricao, recomendacao, resultado))
        
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"Erro ao registrar interação no DB: {e}")