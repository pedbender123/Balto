import asyncio
import json
from datetime import datetime
from aiohttp import web, WSMsgType
from app import db, vad, transcription, speaker_id, audio_processor
from app.core import config, audio_utils, ai_client, buffer
import imageio_ffmpeg

class FFmpegWebMToPCMStream:
    """
    Mantém um ffmpeg vivo por conexão:
      stdin  <- chunks webm/opus do websocket
      stdout -> pcm16le 16k mono em stream
    """
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.proc = None
        self._reader_task = None
        self.pcm_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._closed = False

    async def start(self):
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        self.proc = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-loglevel", "error",
            "-i", "pipe:0",
            "-f", "s16le",
            "-ar", str(self.sample_rate),
            "-ac", "1",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())

    async def _read_stdout(self):
        try:
            while not self._closed:
                chunk = await self.proc.stdout.read(4096)
                if not chunk:
                    break
                await self.pcm_queue.put(chunk)
        except Exception:
            pass

    async def write_webm(self, data: bytes):
        if self._closed or not self.proc or not self.proc.stdin:
            return
        self.proc.stdin.write(data)
        await self.proc.stdin.drain()

    async def read_pcm(self) -> bytes:
        return await self.pcm_queue.get()

    async def close(self):
        self._closed = True

        # destrava o consumer (sentinela)
        try:
            await self.pcm_queue.put(b"")
        except:
            pass

        if self.proc and self.proc.stdin:
            try:
                self.proc.stdin.close()
            except:
                pass

        if self._reader_task:
            self._reader_task.cancel()

        if self.proc:
            try:
                self.proc.kill()
            except:
                pass

async def process_speech_pipeline(
    websocket,
    speech_segment: bytes,
    balcao_id: str,
    transcript_buffer: buffer.TranscriptionBuffer,
    conversation_history: list,
    funcionario_id: int | None,
    nome_funcionario: str,
    speaker_data_list: list | None = None
):

    ts_audio_received = datetime.now()
    # print(f"[{balcao_id}] Processando segmento de fala ({len(speech_segment)} bytes)...")

    if config.SAVE_AUDIO or config.MOCK_MODE:
        await asyncio.to_thread(audio_utils.dump_audio_to_disk, speech_segment, balcao_id)

    if config.MOCK_MODE:
        await asyncio.sleep(1)
        await websocket.send_json({
            "comando": "recomendar",
            "produto": "Produto MOCK",
            "explicacao": "Modo de Teste Ativo",
            "transcricao_base": "Teste de áudio simulado"
        })
        return

    try:
        ts_transcription_sent = datetime.now()
        transcricao_resultado = await asyncio.to_thread(
            transcription.transcrever_inteligente, speech_segment
        )
        ts_transcription_ready = datetime.now()
        
        texto = transcricao_resultado["texto"]
        modelo_usado = transcricao_resultado["modelo"]
        custo_estimado = transcricao_resultado["custo"]
        snr_calculado = transcricao_resultado.get("snr", 0.0)
        
        if not texto:
            return

        print(f"[{balcao_id}] Transcrição ({modelo_usado}): {texto}")
        
        # Add to buffer
        transcript_buffer.add_text(texto)
        # Add to global history for context
        conversation_history.append(texto)
        # Keep history manageable (last 20 turns)
        if len(conversation_history) > 20: 
            conversation_history.pop(0)

            # Check if we should process via AI
            # Check if we should process via AI
        if transcript_buffer.should_process():
            # Pega o buffer atual (que triggerou a ação)
            buffer_content = transcript_buffer.get_context_and_clear()
            
            # Constrói o contexto histórico completo para envio
            full_context_str = " ... ".join(conversation_history)
            
            print(f"[{balcao_id}] Enviando Contexto para AI (Histórico: {len(conversation_history)} itens): {full_context_str[-200:]}...")
            
            ts_ai_request = datetime.now()
            analise_json = await asyncio.to_thread(
                ai_client.ai_client.analisar_texto, full_context_str
            )
            
            if analise_json:
                ts_ai_response = datetime.now()
                try:
                    dados = json.loads(analise_json)
                    items_to_send = []

                    # Handle new schema structure which has "itens" array
                    if "itens" in dados and isinstance(dados["itens"], list):
                        for item in dados["itens"]:
                             if item.get("sugestao"):
                                 items_to_send.append(item)
                    elif dados.get("sugestao"):
                        items_to_send.append(dados)
                    
                    
                    # Collect ALL valid suggestions for logging/DB
                    all_suggestions_list = []
                    for item in items_to_send:
                         sug = item.get("sugestao")
                         expl = item.get("explicacao")
                         if sug and sug.lower() not in ["null", "nenhuma", "none"]:
                             all_suggestions_list.append({"sugestao": sug, "explicacao": expl})
                    
                    # Prepare log string with ALL suggestions
                    sugestoes_log_str = [f"{s['sugestao']} ({s['explicacao']})" for s in all_suggestions_list]
                    recomendacao_log = " | ".join(sugestoes_log_str) if all_suggestions_list else "Nenhuma"

                    # Prepare Payload for Frontend (Max 3)
                    frontend_items = all_suggestions_list[:3]
                    
                    if frontend_items:
                        payload = {
                            "comando": "recomendar",
                            "itens": frontend_items,
                            "transcricao_base": buffer_content,
                            "atendente": nome_funcionario
                        }
                        await websocket.send_json(payload)
                        ts_client_sent = datetime.now() # Capture time sent to client (batch)
                    
                except Exception as e:
                    print(f"[{balcao_id}] Erro Parse JSON AI: {e}")
                    recomendacao_log = "Erro Parse"
            else:
                 # AI retornou None/Vazio (erro no request ou timeout interno)
                 recomendacao_log = "Nenhuma"

        # Prepare log string (Fallback to NULL if not triggered)
        if 'recomendacao_log' not in locals():
            recomendacao_log = None # Explicitly NULL if logic didn't run

        # Log interaction
        await asyncio.to_thread(
            db.registrar_interacao,
            balcao_id=balcao_id,
            transcricao=full_context_str if 'full_context_str' in locals() else texto,
            recomendacao=recomendacao_log,
            resultado="processado",
            funcionario_id=funcionario_id,
            modelo_stt=modelo_usado,
            custo=custo_estimado,
            snr=snr_calculado,
            grok_raw=analise_json if 'analise_json' in locals() else None,
            ts_audio=ts_audio_received,
            ts_trans_sent=ts_transcription_sent,
            ts_trans_ready=ts_transcription_ready,
            ts_ai_req=ts_ai_request if 'ts_ai_request' in locals() else None,
            ts_ai_res=ts_ai_response if 'ts_ai_response' in locals() else None,
            ts_client=ts_client_sent if 'ts_client_sent' in locals() else None,
            speaker_data=json.dumps(speaker_data_list) if speaker_data_list else None # New: Pass speaker data
        )

    except Exception as e:
        print(f"[{balcao_id}] Erro no Pipeline: {e}")
        import traceback
        traceback.print_exc()

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    balcao_id = None
    vad_session = None
    transcript_buffer = buffer.TranscriptionBuffer()
    conversation_history = [] # Local history for this connection
    
    try:
        msg = await ws.receive_json(timeout=10.0)
        api_key = msg.get("api_key")
        
        # New: Parse VAD settings
        vad_settings = msg.get("vad_settings", {})
        vad_threshold_mult = vad_settings.get("threshold_multiplier") # e.g 1.5
        vad_min_energy = vad_settings.get("min_energy") # e.g 50.0

        balcao_id = db.validate_api_key(api_key)
        
        if not balcao_id:
            await ws.close(code=4001, message=b"API Key Invalida")
            return ws
            
        print(f"Conectado: {balcao_id} (Settings: {vad_settings})")
        
        # Pass settings to VAD
        vad_session = vad.VAD(
            threshold_multiplier=vad_threshold_mult,
            min_energy_threshold=vad_min_energy
        )
        audio_cleaner = audio_processor.AudioCleaner()

        decoder = FFmpegWebMToPCMStream(sample_rate=16000)
        await decoder.start()

        pcm_acc = bytearray()

        voice_tracker = speaker_id.StreamVoiceIdentifier()
        funcionario_id_atual = None
        nome_funcionario_atual = "Desconhecido"
        
    except Exception as e:
        print(f"Erro Auth WS: {e}")
        await ws.close()
        return ws

    async def pcm_consumer_loop():
        nonlocal pcm_acc, funcionario_id_atual, nome_funcionario_atual

        while True:
            pcm_chunk = await decoder.read_pcm()

            # sentinela de shutdown
            if pcm_chunk == b"":
                break

            pcm_acc.extend(pcm_chunk)

            while len(pcm_acc) >= 1920:
                new_pcm = bytes(pcm_acc[:1920])
                del pcm_acc[:1920]

                cleaned_pcm = audio_cleaner.process(new_pcm)
                speech = vad_session.process(cleaned_pcm)

                if speech:
                    pred_func_id, score, speaker_data_list = voice_tracker.add_segment(balcao_id, speech)
                    
                    # Nome vem dos dados se existir
                    pred_nome = None
                    if speaker_data_list:
                         # speaker_data_list[0] é o top 1
                         pred_nome = speaker_data_list[0].get("name")

                    if pred_func_id is not None and funcionario_id_atual is None:
                        funcionario_id_atual = pred_func_id
                        nome_funcionario_atual = pred_nome or "Desconhecido"
                        print(f"[{balcao_id}] Voice-ID identificado: id={funcionario_id_atual} nome={nome_funcionario_atual} (score={score:.3f})")

                    asyncio.create_task(
                        process_speech_pipeline(
                            ws, speech, balcao_id, transcript_buffer, conversation_history,
                            funcionario_id_atual, nome_funcionario_atual, speaker_data_list
                        )
                    )

    consumer_task = asyncio.create_task(pcm_consumer_loop())

    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                await decoder.write_webm(msg.data)
            elif msg.type == WSMsgType.ERROR:
                print(f"WS Error: {ws.exception()}")

    except Exception as e:
        if "Cannot write to closing transport" not in str(e):
            print(f"WS Loop Error: {e}")

    finally:
        print(f"Desconectado: {balcao_id}")

        # fecha decoder (isso solta o consumer via sentinela)
        try:
            await decoder.close()
        except:
            pass

        # encerra consumer task
        try:
            consumer_task.cancel()
        except:
            pass

    return ws