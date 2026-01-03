import asyncio
import base64
import json
import os
import uuid
import subprocess
import wave
import pandas as pd
import io
import imageio_ffmpeg # NOVA DEPENDENCIA LOCAL

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
        ffmpeg_cmd = imageio_ffmpeg.get_ffmpeg_exe()
        proc = subprocess.run(
            [
                ffmpeg_cmd, "-i", "pipe:0", "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
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

# --- Rotas de Teste (Hybrid Testing) ---

async def api_test_segmentar(request):
    """
    Simula o streaming WebSocket via HTTP.
    Fatia o áudio em chunks e passa pelo VAD estado-a-estado.
    """
    try:
        reader = await request.multipart()
        field = await reader.next()
        if not field or field.name != 'audio':
            return web.json_response({"error": "Campo 'audio' obrigatório"}, status=400)
        
        filename = field.filename or "audio_upload.wav"
        audio_bytes = await field.read()
        
        # 1. Converter para PCM 16le 16kHz
        pcm_bytes = decode_webm_to_pcm16le(audio_bytes)
        if not pcm_bytes:
            return web.json_response({"error": "Falha na decodificação de áudio"}, status=400)
            
        # 2. Instanciar VAD Novo
        vad_session = vad.VAD()
        # Instanciar Cleaner tbm se quisermos fidelidade total
        cleaner = audio_processor.AudioCleaner()
        
        # OTIMIZAÇÃO: Limpar o áudio inteiro de uma vez para melhor perfil de ruído
        # Em vez de limpar chunk por chunk (que é ruim para noisereduce), limpamos tudo.
        print(f"[TEST] Limpando áudio completo ({len(pcm_bytes)} bytes)...")
        cleaned_pcm_full = cleaner.process(pcm_bytes)
        print("[TEST] Limpeza concluída.")
        
        segments_found = []
        
        # 3. Simular Streaming (Chunking)
        # O cliente envia chunks pequenos. Vamos simular chunks de 30ms (480 samples * 2 bytes = 960 bytes)
        CHUNK_SIZE = 960 
        
        total_len = len(cleaned_pcm_full)
        offset = 0
        
        while offset < total_len:
            end = min(offset + CHUNK_SIZE, total_len)
            # Pegar do áudio JÁ LIMPO
            chunk = cleaned_pcm_full[offset:end]
            offset = end
            
            # Pipeline identico ao WS (exceto que o chunk já está limpo)
            speech = vad_session.process(chunk) # Passa direto pro VAD
            
            if speech:
                # Segmento detectado!
                # Codificar em base64 para retornar no JSON
                b64_seg = base64.b64encode(speech).decode('utf-8')
                segments_found.append({
                    "size_bytes": len(speech),
                    "duration_sec": len(speech) / 32000.0,
                    "audio_base64": b64_seg
                })
        
        return web.json_response({"segments": segments_found, "total_segments": len(segments_found)})
        
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def api_test_transcrever(request):
    try:
        reader = await request.multipart()
        
        data = {}
        while True:
            field = await reader.next()
            if field is None: break
            
            if field.name == 'audio':
                data['audio'] = await field.read()
            elif field.name == 'provider':
                data['provider'] = await field.read(decode=True)
                data['provider'] = data['provider'].decode('utf-8')
        
        if 'audio' not in data:
            return web.json_response({"error": "Audio required"}, status=400)
            
        provider = data.get('provider', 'elevenlabs')
        audio_bytes = data['audio']
        
        text = ""
        if provider == 'assemblyai':
            text = transcription.transcrever_assemblyai(audio_bytes)
        elif provider == 'deepgram':
            text = transcription.transcrever_deepgram(audio_bytes)
        elif provider == 'gladia':
            text = transcription.transcrever_gladia(audio_bytes)
        else:
            text = transcription.transcrever_elevenlabs(audio_bytes)
            
        return web.json_response({"texto": text})
        
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def api_test_analisar(request):
    try:
        data = await request.json()
        texto = data.get("texto")
        if not texto: return web.json_response({"error": "Texto empty"}, status=400)
        
        res_json_str = analysis.analisar_texto(texto, "TesteHTTP")
        
        if res_json_str:
            try:
                res = json.loads(res_json_str)
            except:
                res = {"raw": res_json_str}
            return web.json_response(res)
        else:
            return web.json_response({"error": "No analysis result"}, status=500)
            
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


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
        
        if len(speech_segment) > 32000:
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

        return web.json_response({"error": str(e)}, status=500)

async def api_export_xlsx(request):
    """Gera e baixa relatorio Excel das interacoes."""
    try:
        # Auth Simples (Cookie)
        if request.cookies.get("admin_token") != "auth_ok":
            return web.Response(status=403, text="Forbidden")

        # Busca dados com Pandas direto do Postgres
        conn = db.get_db_connection()
        query = """
        SELECT 
            i.id,
            i.timestamp,
            b.nome_balcao,
            f.nome as funcionario,
            i.transcricao_completa,
            i.recomendacao_gerada,
            i.resultado_feedback,
            i.modelo_stt,
            i.custo_estimado
        FROM interacoes i
        LEFT JOIN balcoes b ON i.balcao_id = b.balcao_id
        LEFT JOIN funcionarios f ON i.funcionario_id = f.id
        ORDER BY i.timestamp DESC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        # Tratamento basico
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%d/%m/%Y %H:%M:%S')
        
        # Gera Excel em memoria
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Interacoes')
            # Auto-adjust columns width (basic)
            worksheet = writer.sheets['Interacoes']
            for column_cells in worksheet.columns:
                length = max(len(str(cell.value)) for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(length + 2, 50)
        
        output.seek(0)
        
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"relatorio_balto_{timestamp_str}.xlsx"
        
        return web.Response(
            body=output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        print(f"Erro Export Excel: {e}")
        return web.Response(status=500, text=str(e))

async def api_cadastro_cliente(request):
    """Endpoint para cadastrar um novo cliente (Rede/Dono)."""
    try:
        data = await request.json()
        email = data.get("email")
        razao = data.get("razao_social")
        tel = data.get("telefone")
        
        if not email or not razao:
             return web.json_response({"error": "Campos email e razao_social origatorios"}, status=400)
             
        try:
            codigo = db.create_client(email, razao, tel)
            return web.json_response({"codigo": codigo}, status=201)
        except Exception as e:
             return web.json_response({"error": f"Erro ao criar cliente: {str(e)}"}, status=500)
            
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def api_cadastro_balcao(request):
    """Endpoint para cadastrar um balcão usando código do cliente."""
    try:
        data = await request.json()
        nome_balcao = data.get("nome_balcao")
        user_codigo = data.get("user_codigo")
        
        if not nome_balcao or not user_codigo:
            return web.json_response({"error": "Campos nome_balcao e user_codigo obrigatorios"}, status=400)
            
        user_id = db.get_user_by_code(user_codigo)
        
        if user_id:
            balcao_id, api_key = db.create_balcao(user_id, nome_balcao)
            return web.json_response({
                "api_key": api_key,
                "balcao_id": balcao_id,
                "status": "registered"
            })
        else:
            return web.json_response({"error": "Codigo invalido ou expirado"}, status=404)
            
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
    app.router.add_post('/cadastro/cliente', api_cadastro_cliente)
    app.router.add_post('/cadastro/balcao', api_cadastro_balcao)
    
    # Novas Rotas de Teste
    app.router.add_post('/api/test/segmentar', api_test_segmentar)
    app.router.add_post('/api/test/transcrever', api_test_transcrever)
    app.router.add_post('/api/test/analisar', api_test_analisar)

    # Rota Exportacao
    app.router.add_get('/api/export/xlsx', api_export_xlsx)
    
    print("Balto Server 2.0 Rodando na porta 8765")
    port = int(os.environ.get("PORT", 8765))
    web.run_app(app, port=port)