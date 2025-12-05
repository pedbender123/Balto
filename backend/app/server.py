import asyncio
import json
import os
import uuid
from dotenv import load_dotenv
from aiohttp import web, WSMsgType

# Ajuste de imports
from app import db, vad, transcription, analysis

load_dotenv()

# --- CONFIGURAÇÕES DE AMBIENTE ---
MOCK_MODE = os.environ.get("MOCK_MODE") == "1"
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "admin123")
VAD_THRESHOLD = os.environ.get("VAD_ENERGY_THRESHOLD", "300")

print(f"[BOOT] MOCK_MODE: {MOCK_MODE}")
print(f"[BOOT] VAD_ENERGY_THRESHOLD: {VAD_THRESHOLD}")

# --- PIPELINE PRINCIPAL ---
async def process_speech_pipeline(websocket, speech_segment: bytes, balcao_id: str):
    print(f"[{balcao_id}] Processando áudio...")
    
    # 1. MOCK MODE (Modo de Teste / Economia)
    if MOCK_MODE:
        print(f"[{balcao_id}] MOCK ATIVADO. Gerando resposta simulada.")
        await asyncio.sleep(1.5) # Simula delay da IA
        
        payload_mock = {
            "comando": "recomendar",
            "produto": "Dipirona (MOCK)",
            "explicacao": "Sugestão gerada pelo MOCK_MODE. Desative no .env para usar IA real.",
            "transcricao_base": "[Áudio ignorado no Mock]"
        }
        await websocket.send_json(payload_mock)
        return

    # 2. Pipeline Real
    try:
        # Transcrição (ElevenLabs)
        texto = await asyncio.to_thread(transcription.transcrever, speech_segment)
        print(f"[{balcao_id}] Transcrição: {texto}")

        if not texto or texto.startswith("[Erro"):
            return

        # Análise (Grok)
        json_analise = await asyncio.to_thread(analysis.analisar_texto, texto)

        if json_analise:
            try:
                dados_analise = json.loads(json_analise)
                produto = dados_analise.get("sugestao")
                explicacao = dados_analise.get("explicacao")
                
                if produto:
                    payload = {
                        "comando": "recomendar",
                        "produto": produto,
                        "explicacao": explicacao,
                        "transcricao_base": texto
                    }
                    await websocket.send_json(payload)
                    print(f"[{balcao_id}] Sugestão enviada: {produto}")
                    
                    # Opcional: Registrar interação simples
                    await asyncio.to_thread(
                        db.registrar_interacao, 
                        balcao_id, texto, f"{produto}: {explicacao}", "pendente"
                    )

            except json.JSONDecodeError:
                print(f"Erro ao decodificar JSON do Grok: {json_analise}")

    except Exception as e:
        print(f"[{balcao_id}] Erro pipeline: {e}")

# --- ADMIN API HANDLERS ---
async def admin_page_handler(request):
    """Serve o HTML do painel administrativo."""
    return web.FileResponse('./app/static/admin.html')

async def admin_login_handler(request):
    """Valida senha e cria cookie."""
    try:
        data = await request.json()
        if data.get("password") == ADMIN_SECRET:
            response = web.Response(text="OK")
            # Cookie simples para auth
            response.set_cookie("admin_token", "authorized", max_age=3600)
            return response
        return web.Response(status=401, text="Senha incorreta")
    except:
        return web.Response(status=400)

def check_auth(request):
    """Helper para verificar cookie."""
    return request.cookies.get("admin_token") == "authorized"

async def admin_get_data(request):
    """Retorna dados das tabelas em JSON (Protegido)."""
    if not check_auth(request):
        return web.Response(status=403, text="Não autorizado")
    
    table_name = request.match_info['table']
    allowed_tables = ['users', 'balcoes', 'interacoes']
    
    if table_name not in allowed_tables:
        return web.Response(status=404, text="Tabela não encontrada")
        
    try:
        # Conecta direto ao DB para ler tudo
        # Nota: Idealmente mover para db.py, mas aqui simplificamos para o admin
        import sqlite3
        conn = sqlite3.connect(db.DB_FILE)
        conn.row_factory = sqlite3.Row # Permite acessar colunas por nome
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        # Converte para lista de dicts
        result = [dict(row) for row in rows]
        conn.close()
        
        return web.json_response(result)
    except Exception as e:
        return web.Response(status=500, text=str(e))

# --- HANDLERS EXISTENTES (Cadastro & WS) ---
# ... (Reimplementando lógica anterior para garantir compatibilidade) ...

async def handle_cadastro_cliente(request):
    data = await request.json()
    res = db.add_user(data.get("email"), data.get("razao_social"), data.get("telefone"))
    status = 201 if res["success"] else 400
    return web.json_response(res, status=status)

async def handle_cadastro_balcao(request):
    data = await request.json()
    res = db.add_balcao(data.get("nome_balcao"), data.get("user_codigo"))
    status = 201 if res["success"] else 400
    return web.json_response(res, status=status)

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    # Auth inicial
    try:
        auth_msg = await ws.receive_json(timeout=10.0)
        api_key = auth_msg.get("api_key")
        balcao_id = db.validate_api_key(api_key)
        
        if not balcao_id:
            await ws.close(code=4001, message=b"API Key Invalida")
            return ws
            
        print(f"Balcão conectado: {balcao_id}")
        
        # Instancia VAD para essa conexão
        client_vad = vad.VAD()

    except Exception as e:
        print(f"Erro Auth: {e}")
        await ws.close()
        return ws

    # Loop Principal
    async for msg in ws:
        if msg.type == WSMsgType.BINARY:
            speech_segment = client_vad.process(msg.data)
            if speech_segment:
                asyncio.create_task(process_speech_pipeline(ws, speech_segment, balcao_id))
        
        elif msg.type == WSMsgType.ERROR:
            print(f'WS Error: {ws.exception()}')

    print("Websocket fechado")
    return ws

# --- MAIN ---
if __name__ == "__main__":
    db.inicializar_db()
    
    app = web.Application()
    
    # Rotas API Pública
    app.router.add_post('/cadastro/cliente', handle_cadastro_cliente)
    app.router.add_post('/cadastro/balcao', handle_cadastro_balcao)
    app.router.add_get('/ws', websocket_handler)
    
    # Rotas Admin
    app.router.add_get('/admin', admin_page_handler)
    app.router.add_post('/admin/login', admin_login_handler)
    app.router.add_get('/api/data/{table}', admin_get_data)
    
    print("Servidor rodando na porta 8765...")
    web.run_app(app, port=8765)