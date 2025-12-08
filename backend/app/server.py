import asyncio
import json
import os
import uuid
from dotenv import load_dotenv
from aiohttp import web, WSMsgType
import subprocess
import wave


# --- CORS MIDDLEWARE ---
@web.middleware
async def cors_middleware(request, handler):
    # Trata o preflight (OPTIONS) antes de chegar no handler
    if request.method == 'OPTIONS':
        resp = web.Response()
    else:
        resp = await handler(request)

    # Em dev você pode liberar o origin que estiver chamando
    origin = request.headers.get("Origin")
    if origin:
        resp.headers['Access-Control-Allow-Origin'] = origin
    # Se preferir fixo em dev:
    # resp.headers['Access-Control-Allow-Origin'] = 'http://localhost:8000'

    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    resp.headers['Access-Control-Allow-Credentials'] = 'true'
    return resp


# Ajuste de imports
from app import db, vad, transcription, analysis

load_dotenv()

# --- CONFIGURAÇÕES DE AMBIENTE ---
MOCK_MODE = os.environ.get("MOCK_MODE") == "1"
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "admin123")
VAD_THRESHOLD = os.environ.get("VAD_ENERGY_THRESHOLD", "300")

# Diretório para dumps de áudio quando estivermos em MOCK_MODE
AUDIO_DUMP_DIR = os.environ.get("AUDIO_DUMP_DIR", "./audio_dumps")

print(f"[BOOT] MOCK_MODE: {MOCK_MODE}")
print(f"[BOOT] VAD_ENERGY_THRESHOLD: {VAD_THRESHOLD}")
print(f"[BOOT] AUDIO_DUMP_DIR: {AUDIO_DUMP_DIR}")

def decode_webm_to_pcm16le(webm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """
    Decodifica um chunk audio/webm (Opus) para PCM 16-bit mono (s16le) em sample_rate.
    Usa ffmpeg via subprocess.
    """
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-i", "pipe:0",          # deixa o ffmpeg auto-detectar o formato
                "-f", "s16le",
                "-ar", str(sample_rate),
                "-ac", "1",
                "pipe:1",
                "-loglevel", "error",
            ],
            input=webm_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="ignore")
            print(f"[FFMPEG] erro (code {proc.returncode}): {err[:300]}")
            return b""

        pcm = proc.stdout
        print(f"[FFMPEG] decodificado {len(webm_bytes)} bytes WebM -> {len(pcm)} bytes PCM")
        return pcm

    except Exception as e:
        print(f"[VAD] Erro ao decodificar WebM para PCM: {e}")
        return b""




# --- PARA SALVAR ARQUIVO DE TESTE ENQUANTO FOR TESTE ---
def save_audio_segment(speech_segment: bytes, balcao_id: str):
    """
    Salva o áudio PCM 16k mono em um arquivo .wav para análise posterior.
    """
    os.makedirs(AUDIO_DUMP_DIR, exist_ok=True)
    filename = f"{balcao_id}_{uuid.uuid4().hex}.wav"
    filepath = os.path.join(AUDIO_DUMP_DIR, filename)

    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(16000)
        wf.writeframes(speech_segment)

    print(f"[{balcao_id}] Áudio salvo em: {filepath}")



# --- PIPELINE PRINCIPAL ---
async def process_speech_pipeline(websocket, speech_segment: bytes, balcao_id: str):
    print(f"[{balcao_id}] Processando áudio...")

    # 1. Se estivermos em MOCK_MODE:
    #    - salvar áudio em WAV para análise
    #    - NÃO chamar ElevenLabs / LLM
    if MOCK_MODE:
        await asyncio.to_thread(save_audio_segment, speech_segment, balcao_id)
        print(f"[{balcao_id}] MOCK_MODE ativo. Áudio salvo, pulando IA real.")

        await asyncio.sleep(1.5)  # simula latência

        payload_mock = {
            "comando": "recomendar",
            "produto": "Dipirona (MOCK)",
            "explicacao": "Sugestão gerada pelo MOCK_MODE. Desative no .env para usar IA real.",
            "transcricao_base": "[Áudio ignorado no Mock]"
        }
        await websocket.send_json(payload_mock)
        return

    # 2. Fluxo real (MOCK_MODE = 0):
    #    - NÃO salva áudio
    #    - envia direto para ElevenLabs + LLM
    try:
        # Transcrição (ElevenLabs)
        texto = await asyncio.to_thread(transcription.transcrever, speech_segment)
        print(f"[{balcao_id}] Transcrição: {texto}")

        if not texto or texto.startswith("[Erro"):
            return

        # Análise (LLM / Grok)
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
        
        # Instancia VAD para essa conexão (espera PCM 16k)
        client_vad = vad.VAD(sample_rate=16000)

    except Exception as e:
        print(f"Erro Auth: {e}")
        await ws.close()
        return ws

    # --- NOVO: buffers por conexão ---
    webm_buffer = bytearray()   # acumula todos os bytes WebM recebidos
    pcm_offset = 0              # quantos bytes PCM já foram entregues ao VAD

    # Loop Principal
    async for msg in ws:
        if msg.type == WSMsgType.BINARY:
            print(f"[{balcao_id}] Chunk binário recebido: {len(msg.data)} bytes")

            # 1) Acumula o stream WebM inteiro
            webm_buffer.extend(msg.data)

            # 2) Decodifica TODO o buffer WebM -> PCM
            pcm_all = decode_webm_to_pcm16le(bytes(webm_buffer), sample_rate=16000)
            if not pcm_all:
                print(f"[{balcao_id}] pcm_all vazio (ffmpeg falhou no buffer inteiro)")
                continue

            # 3) Pega só a parte nova de PCM desde a última chamada
            if len(pcm_all) <= pcm_offset:
                # nada novo
                continue

            pcm_new = pcm_all[pcm_offset:]
            pcm_offset = len(pcm_all)

            print(f"[{balcao_id}] pcm_new decodificado: {len(pcm_new)} bytes")

            # 4) Alimenta o VAD com esse PCM novo
            speech_segment = client_vad.process(pcm_new)
            if speech_segment:
                print(f"[{balcao_id}] Segmento de fala detectado: {len(speech_segment)} bytes")
                asyncio.create_task(
                    process_speech_pipeline(ws, speech_segment, balcao_id)
                )
        
        elif msg.type == WSMsgType.ERROR:
            print(f'WS Error: {ws.exception()}')

    print("Websocket fechado")
    return ws

async def root_handler(request):
    """Redireciona a raiz '/' para '/admin'"""
    raise web.HTTPFound('/admin')

# --- MAIN ---
if __name__ == "__main__":
    db.inicializar_db()
    
    app = web.Application(middlewares=[cors_middleware])
    
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