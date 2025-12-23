import asyncio
import json
import os
import uuid
import subprocess
import wave
from datetime import datetime
from dotenv import load_dotenv
from aiohttp import web, WSMsgType

# Imports internos
from app import db, vad, transcription, analysis, speaker_id, audio_processor

load_dotenv()

# --- Configurações ---
MOCK_MODE = os.environ.get("MOCK_MODE") == "1"
SAVE_AUDIO = os.environ.get("SAVE_AUDIO_DUMPS") == "1" # Feature Fase 1.2
AUDIO_DUMP_DIR = os.environ.get("AUDIO_DUMP_DIR", "./audio_dumps")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "admin123")

print(f"[BOOT] MOCK_MODE: {MOCK_MODE}")
print(f"[BOOT] SAVE_AUDIO_DUMPS: {SAVE_AUDIO}")

# --- Utilitários ---
def decode_webm_to_pcm16le(webm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Decodifica WebM/Opus para PCM 16-bit 16kHz usando FFmpeg."""
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-i", "pipe:0", "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
                "pipe:1", "-loglevel", "error"
            ],
            input=webm_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0:
            print(f"[FFMPEG] Erro: {proc.stderr.decode('utf-8')}")
            return b""
        return proc.stdout
    except Exception as e:
        print(f"[FFMPEG] Exception: {e}")
        return b""

def dump_audio_to_disk(audio_bytes: bytes, balcao_id: str):
    """Salva o áudio bruto para análise (Fase 1.2)."""
    if not os.path.exists(AUDIO_DUMP_DIR):
        os.makedirs(AUDIO_DUMP_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{balcao_id}_{timestamp}_{uuid.uuid4().hex[:6]}.wav"
    filepath = os.path.join(AUDIO_DUMP_DIR, filename)
    
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_bytes)
    print(f"[DUMP] Áudio salvo: {filepath}")

# --- Pipeline Principal (Core Logic) ---
async def process_speech_pipeline(websocket, speech_segment: bytes, balcao_id: str):
    print(f"[{balcao_id}] Processando segmento de fala ({len(speech_segment)} bytes)...")

    # Passo 1: Infraestrutura de Teste
    if SAVE_AUDIO or MOCK_MODE:
        await asyncio.to_thread(dump_audio_to_disk, speech_segment, balcao_id)

    if MOCK_MODE:
        await asyncio.sleep(1)
        await websocket.send_json({
            "comando": "recomendar",
            "produto": "Produto MOCK",
            "explicacao": "Modo de Teste Ativo",
            "transcricao_base": "Teste de áudio simulado"
        })
        return

    try:
        # Passo 2 & 3: Roteamento de Custo e Transcrição (Smart Routing)
        # O transcription.py decide se usa modelo caro ou barato
        transcricao_resultado = await asyncio.to_thread(
            transcription.transcrever_inteligente, speech_segment
        )
        
        texto = transcricao_resultado["texto"]
        modelo_usado = transcricao_resultado["modelo"]
        custo_estimado = transcricao_resultado["custo"]
        
        if not texto:
            return

        print(f"[{balcao_id}] Transcrição ({modelo_usado}): {texto}")

        # Passo 4: Identificação Biométrica (Speaker ID)
        nome_funcionario = "Desconhecido"
        funcionario_id = None
        
        # Só tenta identificar se tiver áudio suficiente (>1s) para evitar falso positivo
        if len(speech_segment) > 32000: # ~1 segundo em 16k 16bit
            identificacao = await asyncio.to_thread(
                speaker_id.identificar_funcionario, speech_segment, balcao_id
            )
            if identificacao:
                nome_funcionario = identificacao["nome"]
                funcionario_id = identificacao["id"]
                print(f"[{balcao_id}] Funcionário Identificado: {nome_funcionario}")

        # Passo 5: Inteligência (LLM) com Contexto
        analise_json = await asyncio.to_thread(
            analysis.analisar_texto, texto, nome_funcionario
        )

        sugestao = None
        explicacao = None
        
        if analise_json:
            try:
                dados = json.loads(analise_json)
                sugestao = dados.get("sugestao")
                explicacao = dados.get("explicacao")
                
                if sugestao:
                    # Passo 6: Resposta ao Cliente
                    await websocket.send_json({
                        "comando": "recomendar",
                        "produto": sugestao,
                        "explicacao": explicacao,
                        "transcricao_base": texto,
                        "atendente": nome_funcionario
                    })
            except:
                pass

        # Passo 7: Analytics e Logs
        await asyncio.to_thread(
            db.registrar_interacao,
            balcao_id=balcao_id,
            transcricao=texto,
            recomendacao=f"{sugestao} ({explicacao})" if sugestao else "Nenhuma",
            resultado="processado",
            funcionario_id=funcionario_id,
            modelo_stt=modelo_usado,
            custo=custo_estimado
        )

    except Exception as e:
        print(f"[{balcao_id}] Erro no Pipeline: {e}")
        import traceback
        traceback.print_exc()

# --- Handlers WebSocket e HTTP ---

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    balcao_id = None
    vad_session = None
    
    # Buffers de decodificação
    webm_buffer = bytearray()
    pcm_offset = 0

    try:
        # Auth Handshake
        msg = await ws.receive_json(timeout=10.0)
        api_key = msg.get("api_key")
        balcao_id = db.validate_api_key(api_key)
        
        if not balcao_id:
            await ws.close(code=4001, message=b"API Key Invalida")
            return ws
            
        print(f"Conectado: {balcao_id}")
        vad_session = vad.VAD() # Instância dedicada do VAD
        audio_cleaner = audio_processor.AudioCleaner() # Instância dedicada do Cleaner
        
    except Exception as e:
        print(f"Erro Auth WS: {e}")
        await ws.close()
        return ws

    async for msg in ws:
        if msg.type == WSMsgType.BINARY:
            # Fluxo de Áudio
            webm_buffer.extend(msg.data)
            
            # Decodifica tudo que tem no buffer
            pcm_full = decode_webm_to_pcm16le(bytes(webm_buffer))
            
            if not pcm_full: continue
            
            # Pega apenas os bytes novos
            if len(pcm_full) > pcm_offset:
                new_pcm = pcm_full[pcm_offset:]
                pcm_offset = len(pcm_full)
                
                # Processa no VAD
                # 1. Limpeza de Áudio (Fase 1)
                cleaned_pcm = audio_cleaner.process(new_pcm)
                
                # 2. VAD Adaptativo com áudio limpo
                speech = vad_session.process(cleaned_pcm)
                
                if speech:
                    asyncio.create_task(
                        process_speech_pipeline(ws, speech, balcao_id)
                    )
        elif msg.type == WSMsgType.ERROR:
            print(f"WS Error: {ws.exception()}")

    print(f"Desconectado: {balcao_id}")
    return ws

# --- API e Admin ---
async def admin_page(request):
    return web.FileResponse('./app/static/admin.html')

async def admin_login(request):
    try:
        data = await request.json()
        if data.get("password") == ADMIN_SECRET:
            resp = web.Response(text="OK")
            resp.set_cookie("admin_token", "auth_ok", max_age=3600)
            return resp
        return web.Response(status=401)
    except:
        return web.Response(status=400)

async def api_enroll_voice(request):
    """Endpoint para cadastrar voz de funcionário (Fase 3)."""
    # Exige Auth (simplificado check de cookie)
    if request.cookies.get("admin_token") != "auth_ok":
        return web.Response(status=403)
        
    reader = await request.multipart()
    field = await reader.next()
    
    nome = "Funcionario"
    balcao_id = "default" # Em prod, pegar do form
    
    # Lógica simplificada de leitura de multipart
    # Na prática, precisaria parsear os campos 'nome', 'balcao_id' e o arquivo 'audio'
    # Deixando esqueleto funcional
    return web.Response(text="Enrollment endpoint ready")

async def api_batch_status(request):
    """Endpoint para checar status do processamento em lote."""
    try:
        status_path = './app/static/batch_status.json'
        if os.path.exists(status_path):
            with open(status_path, 'r') as f:
                data = json.load(f)
            return web.json_response(data)
        else:
            return web.json_response({"percent": 0, "status": "idle"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# --- Setup ---
@web.middleware
async def cors_middleware(request, handler):
    if request.method == 'OPTIONS':
        resp = web.Response()
    else:
        resp = await handler(request)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = '*'
    return resp

if __name__ == "__main__":
    db.inicializar_db()
    
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/admin', admin_page)
    app.router.add_post('/admin/login', admin_login)
    app.router.add_post('/admin/login', admin_login)
    app.router.add_post('/api/enroll', api_enroll_voice)
    app.router.add_get('/api/batch_status', api_batch_status)
    
    print("Balto Server 2.0 Rodando na porta 8765")
    web.run_app(app, port=8765)