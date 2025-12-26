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

# --- Handlers WebSocket e HTTP ---

# --- Imports Debug ---
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