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
        # Passo 2 & 3: Transcrição (Hardcoded ElevenLabs para Produção)
        # Em produção, não usamos mais o roteamento econômico para garantir qualidade máxima.
        texto = await asyncio.to_thread(
            transcription.transcrever_elevenlabs, speech_segment
        )
        # Mock values para manter compatibilidade com DB
        modelo_usado = "elevenlabs"
        custo_estimado = 0.05 
        
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

# --- Handler WebSocket de Produção ---
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

# --- Imports Debug ---
import base64

# Cache de componentes de Debug (Lazy Load)
DEBUG_ENGINE = None

async def get_debug_engine():
    """Carrega dependências pesadas (Torch/Silero/NoiseReduce) em thread separada."""
    global DEBUG_ENGINE
    if DEBUG_ENGINE:
        return DEBUG_ENGINE
    
    print("[DEBUG] Inicializando engine de debug (Torch/Silero)... Pode demorar.")
    
    def _load():
        # Importação pesada aqui dentro
        from app import silero_vad
        
        # Carrega Modelo VAD
        vad_inst = silero_vad.SileroVAD(threshold=0.4) # Threshold ajustado para ser mais sensível
        
        # Carrega Cleaner (Opcional, pode desativar se der gargalo)
        cleaner = audio_processor.AudioCleaner(stationary=True)
        
        return vad_inst, cleaner

    # Executa no Executor Padrão (Thread Pool) para não travar o loop
    try:
        DEBUG_ENGINE = await asyncio.to_thread(_load)
        print("[DEBUG] Engine carregada com sucesso.")
        return DEBUG_ENGINE
    except Exception as e:
        print(f"[DEBUG] Falha ao carregar engine: {e}")
        return None, None

# --- Debug Pipeline (Instrumentado) ---
async def debug_process_speech_pipeline(websocket, speech_segment: bytes, segment_id: str):
    """Pipeline instrumentado que envia eventos JSON de volta para o cliente."""
    print(f"[DEBUG] Processando segmento {segment_id} ({len(speech_segment)} bytes)")

    # 1. Evento: Segmento Criado (+ AUDIO BASE64)
    duration = len(speech_segment) / 32000.0
    audio_base64 = base64.b64encode(speech_segment).decode('utf-8')
    
    await websocket.send_json({
        "event": "segment_created",
        "data": {
            "segment_id": segment_id,
            "duration_seconds": round(duration, 3),
            "timestamp": datetime.now().isoformat(),
            "audio_base64": audio_base64 # Produto Bruto do VAD
        }
    })

    try:
        # Importação Local para Roteamento (evita ciclo/erro start)
        from app import transcription as debug_transcription
        
        # 2. Roteamento (SIMULAÇÃO)
        # Descobrimos qual modelo o sistema "inteligente" escolheria, apenas para log.
        routing = await asyncio.to_thread(
            debug_transcription.decidir_roteamento, speech_segment
        )
        
        # 3. Transcrição DUPLA (Comparação)
        # Executando ambos para análise de qualidade
        t_eleven = await asyncio.to_thread(
            debug_transcription.transcrever_elevenlabs, speech_segment
        )
        t_assembly = await asyncio.to_thread(
            debug_transcription.transcrever_assemblyai, speech_segment
        )

        # 4. Evento: Decisão de Roteamento (Simulada)
        await websocket.send_json({
            "event": "routing_decision",
            "data": {
                "segment_id": segment_id,
                "snr_db": round(routing["snr"], 2),
                "duration": round(duration, 3),
                "suggested_model": routing["modelo_sugerido"],
                "reason": routing["reason"]
            }
        })

        # 5. Evento: Resultado Transcrição (DUPLO)
        await websocket.send_json({
            "event": "transcription_result",
            "data": {
                "segment_id": segment_id,
                "transcriptions": {
                    "elevenlabs": t_eleven,
                    "assemblyai": t_assembly
                },
                "chosen_for_analysis": "elevenlabs" # Sempre usamos o melhor para análise
            }
        })

        if not t_eleven: return

        # 6. Análise (Mock ou Real)
        # Usando o texto do ElevenLabs (melhor qualidade) para a IA analisar
        analise_json = await asyncio.to_thread(
            analysis.analisar_texto, t_eleven, "Funcionario_Teste"
        )
        
        analysis_data = {}
        if analise_json:
            try:
                analysis_data = json.loads(analise_json)
            except:
                analysis_data = {"raw": analise_json}

        # 7. Evento: Resultado Análise
        await websocket.send_json({
            "event": "analysis_result",
            "data": {
                "segment_id": segment_id,
                "analysis": analysis_data
            }
        })

    except Exception as e:
        error_msg = str(e)
        print(f"[DEBUG] Erro Pipeline: {error_msg}")
        await websocket.send_json({
            "event": "error",
            "data": {"segment_id": segment_id, "message": error_msg}
        })

# --- Handler WebSocket de Debug ---
async def debug_websocket_handler(request):
    """
    Endpoint para testes: /ws/debug_audio
    Requer autenticação via 'key' na query string ou header 'X-Adm-Key'.
    Usa Silero VAD e reporta tudo via JSON events.
    """
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # 1. Autenticação
    auth_key = request.headers.get("X-Adm-Key") or request.query.get("key")
    
    if auth_key != ADMIN_SECRET:
        print(f"[DEBUG] Tentativa de acesso negado. Key: {auth_key}")
        await ws.close(code=4003, message=b"Forbidden: Invalid ADM Key")
        return ws

    print("[DEBUG] Cliente conectado e autenticado (ADM Bypass). Inicializando Engine...")
    
    # 2. Setup Pipeline de Teste (Async/Lazy)
    vad_inst, cleaner = await get_debug_engine()
    
    if not vad_inst:
        await ws.send_json({"event": "fatal_error", "data": "Falha no motor de teste."})
        await ws.close(code=4500)
        return ws
    
    vad_iterator = vad_inst.get_iterator()
    
    # Buffers
    process_buffer = bytearray()
    vad_buffer = [] 
    is_speaking = False
    
    # Configuração Chunks
    VAD_CHUNK_SIZE_BYTES = 1024 # 512 samples * 2 bytes
    
    # IMPORTANTE: Em debug queremos VER o que acontece, então vamos logar o tamanho dos buffers
    
    # Buffer de decodificação global
    webm_buffer = bytearray()
    pcm_offset = 0

    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                
                # Recebe Chunk
                chunk_len = len(msg.data)
                webm_buffer.extend(msg.data)
                
                # Decodifica incremental (AGORA EM THREAD PARA NAO BLOQUEAR O LOOP)
                # Isso resolve o Timeout de Keepalive
                full_pcm = await asyncio.to_thread(
                    decode_webm_to_pcm16le, bytes(webm_buffer), 16000
                )
                
                if not full_pcm: 
                    # Se ffmpeg falhar, pode ser porque o buffer ainda é header imcompleto
                    if len(webm_buffer) > 50000: # Se acumulou 50kb e nao decodificou, estranho
                         print(f"[WARN] FFMPEG retornou vazio com buffer {len(webm_buffer)}")
                    continue
                
                # Pega só o novo
                if len(full_pcm) > pcm_offset:
                    new_pcm = full_pcm[pcm_offset:]
                    pcm_len = len(new_pcm)
                    pcm_offset = len(full_pcm)
                    
                    # 1. Cleaning API
                    # ATENCAO: Desativando cleaner temporariamente se for muito agressivo?
                    # cleaned_chunk = await asyncio.to_thread(cleaner.process, new_pcm)
                    # Não, vamos usar direto, mas cuidado com delay. O Cleaner é numpy, rápido.
                    
                    cleaned_chunk = cleaner.process(new_pcm) # Processamento síncrono rápido (Numpy)
                    process_buffer.extend(cleaned_chunk)
                    
                    # Log de fluxo
                    # print(f"[FLOW] In: {chunk_len}b -> PCM New: {pcm_len}b -> Buff: {len(process_buffer)}")

                    # 2. VAD Loop (Consome o buffer em blocos de 1024 bytes)
                    # Precisa importar silero_vad para usar np dentro do loop? 
                    # O 'vad_inst' encapsula lógica, mas aqui estamos fazendo manual o tensor.
                    # Vamos pegar as deps do engine.
                    from app import silero_vad
                    
                    while len(process_buffer) >= VAD_CHUNK_SIZE_BYTES:
                        sub_chunk = process_buffer[:VAD_CHUNK_SIZE_BYTES]
                        del process_buffer[:VAD_CHUNK_SIZE_BYTES]
                        
                        # Prepare Tensor
                        audio_int16 = silero_vad.np.frombuffer(sub_chunk, dtype=silero_vad.np.int16)
                        audio_float32 = audio_int16.astype(silero_vad.np.float32) / 32768.0
                        tensor = silero_vad.torch.Tensor(audio_float32)
                        
                        # VAD Check
                        speech_dict = vad_iterator(tensor, return_seconds=False)
                        
                        if speech_dict:
                            if 'start' in speech_dict:
                                is_speaking = True
                                print("[DEBUG] >>> Fala INICIOU")
                                vad_buffer.append(sub_chunk)
                            elif 'end' in speech_dict:
                                is_speaking = False
                                print("[DEBUG] <<< Fala ENCERROU")
                                vad_buffer.append(sub_chunk)
                                
                                # Dispara processamento
                                full_segment = b''.join(vad_buffer)
                                vad_buffer = []
                                
                                # Filtro min duracao (0.5s)
                                if len(full_segment) > 16000:
                                    seg_id = uuid.uuid4().hex[:8]
                                    asyncio.create_task(
                                        debug_process_speech_pipeline(ws, full_segment, seg_id)
                                    )
                                else:
                                    print("[DEBUG] Segmento muito curto descartado.")
                        else:
                            if is_speaking:
                                vad_buffer.append(sub_chunk)

            elif msg.type == WSMsgType.ERROR:
                print(f"[DEBUG] WS Error: {ws.exception()}")

    except Exception as e:
        print(f"[DEBUG] Exception no Handler: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("[DEBUG] Cliente desconectado.")
        return ws


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
    app.router.add_get('/ws/debug_audio', debug_websocket_handler) # Rota de Debug
    app.router.add_get('/admin', admin_page)
    app.router.add_post('/admin/login', admin_login)
    app.router.add_post('/api/enroll', api_enroll_voice)
    app.router.add_get('/api/batch_status', api_batch_status)
    
    print("Balto Server 2.0 Rodando na porta 8765")
    web.run_app(app, port=8765)
import base64
# from app import silero_vad (Movido para escopo local para evitar crash no startup se torch falhar)

# --- Debug Pipeline (Instrumentado) ---
async def debug_process_speech_pipeline(websocket, speech_segment: bytes, segment_id: str):
    """Pipeline instrumentado que envia eventos JSON de volta para o cliente."""
    print(f"[DEBUG] Processando segmento {segment_id} ({len(speech_segment)} bytes)")

    # 1. Evento: Segmento Criado (+ AUDIO BASE64)
    duration = len(speech_segment) / 32000.0
    audio_base64 = base64.b64encode(speech_segment).decode('utf-8')
    
    await websocket.send_json({
        "event": "segment_created",
        "data": {
            "segment_id": segment_id,
            "duration_seconds": round(duration, 3),
            "timestamp": datetime.now().isoformat(),
            "audio_base64": audio_base64 # Produto Bruto do VAD
        }
    })

    try:
        # Importação Local para Roteamento (evita ciclo/erro start)
        from app import transcription as debug_transcription
        
        # 2. Roteamento (SIMULAÇÃO)
        # Descobrimos qual modelo o sistema "inteligente" escolheria, apenas para log.
        routing = await asyncio.to_thread(
            debug_transcription.decidir_roteamento, speech_segment
        )
        
        # 3. Transcrição DUPLA (Comparação)
        # Executando ambos para análise de qualidade
        t_eleven = await asyncio.to_thread(
            debug_transcription.transcrever_elevenlabs, speech_segment
        )
        t_assembly = await asyncio.to_thread(
            debug_transcription.transcrever_assemblyai, speech_segment
        )

        # 4. Evento: Decisão de Roteamento (Simulada)
        await websocket.send_json({
            "event": "routing_decision",
            "data": {
                "segment_id": segment_id,
                "snr_db": round(routing["snr"], 2),
                "duration": round(duration, 3),
                "suggested_model": routing["modelo_sugerido"],
                "reason": routing["reason"]
            }
        })

        # 5. Evento: Resultado Transcrição (DUPLO)
        await websocket.send_json({
            "event": "transcription_result",
            "data": {
                "segment_id": segment_id,
                "transcriptions": {
                    "elevenlabs": t_eleven,
                    "assemblyai": t_assembly
                },
                "chosen_for_analysis": "elevenlabs" # Sempre usamos o melhor para análise
            }
        })

        if not t_eleven: return

        # 6. Análise (Mock ou Real)
        # Usando o texto do ElevenLabs (melhor qualidade) para a IA analisar
        analise_json = await asyncio.to_thread(
            analysis.analisar_texto, t_eleven, "Funcionario_Teste"
        )
        
        analysis_data = {}
        if analise_json:
            try:
                analysis_data = json.loads(analise_json)
            except:
                analysis_data = {"raw": analise_json}

        # 7. Evento: Resultado Análise
        await websocket.send_json({
            "event": "analysis_result",
            "data": {
                "segment_id": segment_id,
                "analysis": analysis_data
            }
        })

    except Exception as e:
        error_msg = str(e)
        print(f"[DEBUG] Erro: {error_msg}")
        await websocket.send_json({
            "event": "error",
            "data": {"segment_id": segment_id, "message": error_msg}
        })

# --- Handler WebSocket de Debug ---
async def debug_websocket_handler(request):
    """
    Endpoint para testes: /ws/debug_audio
    Requer autenticação via 'key' na query string ou header 'X-Adm-Key'.
    Usa Silero VAD e reporta tudo via JSON events.
    """
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # 1. Autenticação
    # Tenta Header depois Query Param
    auth_key = request.headers.get("X-Adm-Key") or request.query.get("key")
    
    if auth_key != ADMIN_SECRET:
        print(f"[DEBUG] Tentativa de acesso negado. Key: {auth_key}")
        await ws.close(code=4003, message=b"Forbidden: Invalid ADM Key")
        return ws

    print("[DEBUG] Cliente conectado e autenticado (ADM Bypass).")
    
    try:
        # Importação Local do Silero (Risky Dependency)
        from app import silero_vad
        
        # Setup Pipeline de Teste (Silero para melhor qualidade)
        vad_inst = silero_vad.SileroVAD(threshold=0.5)
        vad_iterator = vad_inst.get_iterator()
        cleaner = audio_processor.AudioCleaner()
    except Exception as e:
        print(f"[DEBUG] Erro ao carregar dependencias de teste (Silero): {e}")
        await ws.send_json({"event": "fatal_error", "data": "Falha ao carregar motor de teste. Verifique logs do servidor."})
        await ws.close(code=4500)
        return ws
    
    # Buffers
    # O Silero precisa de chunks de 512 samples. O FFmpeg gera chunks arbitrários.
    # Vamos usar um buffer circular ou acumulador.
    process_buffer = bytearray()
    vad_buffer = [] # Lista de chunks de fala
    is_speaking = False
    
    # Configuração Chunks
    VAD_CHUNK_SIZE_BYTES = 1024 # 512 samples * 2 bytes

    # Buffer de decodificação global
    webm_buffer = bytearray()
    pcm_offset = 0

    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                # Recebe chunk Opus/WebM ou PCM (vamos assumir stream continuo PCM se o cliente mandar PCM, 
                # mas o encoded webm se for browser. O protocolo diz "Audio Binario".
                # Para ser compatível com o cliente de teste simples, vamos suportar WebM stream igual prod)
                
                webm_buffer.extend(msg.data)
                
                # Decodifica incremental
                full_pcm = decode_webm_to_pcm16le(bytes(webm_buffer))
                if not full_pcm: continue
                
                # Pega só o novo
                if len(full_pcm) > pcm_offset:
                    new_pcm = full_pcm[pcm_offset:]
                    pcm_offset = len(full_pcm)
                    
                    # 1. Cleaning
                    cleaned_chunk = cleaner.process(new_pcm)
                    process_buffer.extend(cleaned_chunk)
                    
                    # 2. VAD Loop (Consome o buffer em blocos de 1024 bytes)
                    while len(process_buffer) >= VAD_CHUNK_SIZE_BYTES:
                        sub_chunk = process_buffer[:VAD_CHUNK_SIZE_BYTES]
                        del process_buffer[:VAD_CHUNK_SIZE_BYTES]
                        
                        # Prepare Tensor
                        audio_int16 = silero_vad.np.frombuffer(sub_chunk, dtype=silero_vad.np.int16)
                        audio_float32 = audio_int16.astype(silero_vad.np.float32) / 32768.0
                        tensor = silero_vad.torch.Tensor(audio_float32)
                        
                        # VAD Check
                        speech_dict = vad_iterator(tensor, return_seconds=False)
                        
                        if speech_dict:
                            if 'start' in speech_dict:
                                is_speaking = True
                                print("[DEBUG] Fala iniciada")
                                vad_buffer.append(sub_chunk)
                            elif 'end' in speech_dict:
                                is_speaking = False
                                print("[DEBUG] Fala encerrada")
                                vad_buffer.append(sub_chunk)
                                
                                # Dispara processamento
                                full_segment = b''.join(vad_buffer)
                                vad_buffer = []
                                
                                # Filtro min duracao (0.5s)
                                if len(full_segment) > 16000:
                                    seg_id = uuid.uuid4().hex[:8]
                                    asyncio.create_task(
                                        debug_process_speech_pipeline(ws, full_segment, seg_id)
                                    )
                        else:
                            if is_speaking:
                                vad_buffer.append(sub_chunk)

            elif msg.type == WSMsgType.ERROR:
                print(f"[DEBUG] WS Error: {ws.exception()}")

    except Exception as e:
        print(f"[DEBUG] Exception no Handler: {e}")
    finally:
        print("[DEBUG] Cliente desconectado.")
        return ws


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
    app.router.add_get('/ws/debug_audio', debug_websocket_handler) # Rota de Debug
    app.router.add_get('/admin', admin_page)
    # ... (restante igual)
    app.router.add_post('/admin/login', admin_login)
    app.router.add_post('/api/enroll', api_enroll_voice)
    app.router.add_get('/api/batch_status', api_batch_status)
    
    print("Balto Server 2.0 Rodando na porta 8765")
    web.run_app(app, port=8765)