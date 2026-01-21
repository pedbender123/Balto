import asyncio
import json
from datetime import datetime
from aiohttp import web, WSMsgType
from app import db, vad, transcription, speaker_id, audio_processor
from app import db, vad, transcription, speaker_id, audio_processor
from app.core import config, audio_utils, ai_client, buffer, audio_analysis, capacity_guard
import imageio_ffmpeg
try:
    import psutil
except ImportError:
    psutil = None
import random

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
    funcionario_id: int | None,
    nome_funcionario: str,
    speaker_data_list: list | None = None,
    vad_meta: dict | None = None,
    config_snapshot: dict | None = None
):

    ts_audio_received = datetime.now()
    # print(f"[{balcao_id}] Processando segmento de fala ({len(speech_segment)} bytes)...")

    # Resource Snapshot
    # Resource Snapshot (From Global Cache to avoid Too Many Open Files)
    # if psutil:
    #     cpu_usage = psutil.cpu_percent()
    #     ram_usage = psutil.Process().memory_info().rss / (1024 * 1024) # MB
    # else:
    
    # [FIX] Read from background update
    from app.core import system_monitor
    cpu_usage = system_monitor.SYSTEM_METRICS["cpu"]
    ram_usage = system_monitor.SYSTEM_METRICS["ram"]

    # Audio Analysis (Feature Extraction)
    try:
        # [MODIFIED] Use Advanced Features
        features = await asyncio.to_thread(audio_analysis.extract_advanced_features, speech_segment)
    except Exception as e:
        print(f"[{balcao_id}] Audio Analysis Failed: {e}")
        features = {}



    # Initialize audio_metrics with all features from analysis
    # This ensures ZCR, BandEnergy, Peak, etc are stored even in mock mode
    audio_metrics = dict(features)  # Copy all metrics
    
    # Also store vad_meta if available
    if vad_meta:
        audio_metrics.update(vad_meta)

    audio_pitch_mean = features.get("pitch_mean", 0.0)
    audio_pitch_std = features.get("pitch_std", 0.0)
    spectral_centroid_mean = features.get("spectral_centroid_mean", 0.0)


    # MOCK VOICE MODE (The "Polite" Mock)
    if config.MOCK_VOICE:
        latency = random.uniform(config.MOCK_LATENCY_MIN, config.MOCK_LATENCY_MAX)
        print(f"[{balcao_id}] MOCK VOICE: Sleeping for {latency:.2f}s...")
        await asyncio.sleep(latency)
        
        mock_resp = {
            "comando": "recomendar",
            "produto": "Produto MOCK Voice",
            "explicacao": f"Resposta simulada (Latency: {latency:.2f}s)",
            "transcricao_base": "Audio Simulado (Feature Extraction Active)"
        }
        
        rec_log = mock_resp["explicacao"]
        
        # [FIX] Check if we should suppress recommendations
        if config.MOCK_RECOMMENDATION:
             rec_log = "🚫 MOCK REC: Desativado (Simulação Bloqueada)"
             print(f"[{balcao_id}] Recomendação MOCK VOICE bloqueada por configuração.")
        else:
            try:
                if not websocket.closed:
                    await websocket.send_json(mock_resp)
            except Exception as e:
                print(f"[{balcao_id}] Warning: Connection closed during Mock Latency. Response skipped.")

        # Log Interaction even in Mock Mode
        await asyncio.to_thread(
            db.registrar_interacao,
            balcao_id=balcao_id,
            transcricao="[MOCK VOICE] Audio Processed",
            recomendacao=rec_log,
            resultado="mock_voice",
            funcionario_id=funcionario_id,
            modelo_stt="mock",
            custo=0.0,
            snr=0.0,
            grok_raw=None,
            ts_audio=ts_audio_received,
            ts_client=datetime.now(),
            speaker_data=json.dumps(speaker_data_list) if speaker_data_list else None,
            audio_metrics=audio_metrics,
            # Enhanced Metrics
            config_snapshot=json.dumps(config_snapshot) if config_snapshot else None,
            mock_status=json.dumps({"mode": "mock_voice", "latency": latency}),
            cpu_usage=cpu_usage,
            ram_usage=ram_usage,
            audio_pitch_mean=audio_pitch_mean,
            audio_pitch_std=audio_pitch_std,
            spectral_centroid_mean=spectral_centroid_mean,
            interaction_type="mock_voice"
        )
        return

    # Check Legacy Mock Mode (LLM only mock, usually immediate)
    if config.MOCK_MODE:
        await asyncio.to_thread(audio_utils.dump_audio_to_disk, speech_segment, balcao_id)
        await asyncio.sleep(1)
        
        if config.MOCK_RECOMMENDATION:
             print(f"[{balcao_id}] Recomendação MOCK MODE bloqueada por configuração.")
             # No log needed for legacy mock in this specific flow as it doesn't call registrar_interacao usually? 
             # Wait, the legacy flow returns immediately. The logic below handles real processing.
             # If MOCK_MODE is true, it returns here. 
             # We should probably log if we want visibility, but the legacy mock code block 
             # didn't have a DB call originally (lines 176-185 in original).
             # It just returned. 
             return

        await websocket.send_json({
            "comando": "recomendar",
            "produto": "Produto MOCK LLM",
            "explicacao": "Modo de Teste LLM Ativo",
            "transcricao_base": "Teste de áudio simulado"
        })
        return

    try:
        buffer_content = None
        analise_json = None
        ts_ai_request = None
        ts_ai_response = None
        ts_client_sent = None
        recomendacao_log = None

        ts_transcription_sent = datetime.now()
        transcricao_resultado = await asyncio.to_thread(
            transcription.transcrever_inteligente, speech_segment
        )
        ts_transcription_ready = datetime.now()
        
        texto = transcricao_resultado["texto"]
        modelo_usado = transcricao_resultado["modelo"]
        custo_estimado = transcricao_resultado["custo"]
        snr_calculado = transcricao_resultado.get("snr", 0.0)

        # ----------------------------
        # Audio metrics (telemetria)
        # ----------------------------
        vad_meta = vad_meta or {}

        segment_bytes = len(speech_segment)

        # speech_segment aqui é PCM16 mono 16kHz (s16le)
        # bytes por segundo = 16000 samples/s * 2 bytes
        segment_duration_ms = int((segment_bytes / (16000 * 2)) * 1000)

        # Add segment info to existing audio_metrics (already has features + vad_meta)
        audio_metrics["segment_bytes"] = int(segment_bytes)
        audio_metrics["segment_duration_ms"] = int(segment_duration_ms)

        interaction_type = "valid"

        if not texto:
            print(f"[{balcao_id}] Transcrição vazia (Noise/Silence). Salvando como 'discarded_empty'.")
            interaction_type = "discarded_empty"
            # We CONTINUE to log interaction, but skip AI/Buffer stuff
            
            await asyncio.to_thread(
                db.registrar_interacao,
                balcao_id=balcao_id,
                transcricao="",
                recomendacao="Recusado (Vazio)",
                resultado="discarded",
                funcionario_id=funcionario_id,
                modelo_stt=modelo_usado,
                custo=custo_estimado,
                snr=snr_calculado,
                grok_raw=None,
                ts_audio=ts_audio_received,
                ts_trans_sent=ts_transcription_sent,
                ts_trans_ready=ts_transcription_ready,
                ts_ai_req=None,
                ts_ai_res=None,
                ts_client=None,
                speaker_data=json.dumps(speaker_data_list) if speaker_data_list else None,
                audio_metrics=audio_metrics,
                # Enhanced Metrics
                config_snapshot=json.dumps(config_snapshot) if config_snapshot else None,
                mock_status=None,
                cpu_usage=cpu_usage,
                ram_usage=ram_usage,
                audio_pitch_mean=audio_pitch_mean,
                audio_pitch_std=audio_pitch_std,
                spectral_centroid_mean=spectral_centroid_mean,
                interaction_type=interaction_type
            )
            return


        ts_transcription_end = datetime.now()
        processing_time_so_far = (ts_transcription_end - ts_transcription_sent).total_seconds()
        capacity_guard.CapacityGuard.report_processing_metrics(segment_duration_ms / 1000.0, processing_time_so_far)

        print(f"[{balcao_id}] Transcrição ({modelo_usado}): {texto}")
        
        # Add to buffer
        transcript_buffer.add_text(texto)

        # Check if we should process via AI
        if transcript_buffer.should_process():
            # [FIX] Check suppression FIRST
            if config.MOCK_RECOMMENDATION:
                print(f"[{balcao_id}] Recomendação AI bloqueada por configuração (MOCK_RECOMMENDATION=True).")
                recomendacao_log = "🚫 MOCK REC: Desativado"
                # Skip the rest of the AI block
            
            else:
                # Pega o buffer atual (que triggerou a ação)
                buffer_content = transcript_buffer.get_context_and_clear()

                print(f"[{balcao_id}] Enviando para AI: {buffer_content[-200:]}...")

            ts_ai_request = datetime.now()

            analise_json = await asyncio.to_thread(
                ai_client.ai_client.analisar_texto, buffer_content
            )

            if analise_json:
                ts_ai_response = datetime.now()
                try:
                    dados = json.loads(analise_json)

                    # Define items_to_send UMA vez, sem loop
                    if "itens" in dados and isinstance(dados["itens"], list):
                        items_to_send = dados["itens"]
                    elif "sugestao" in dados:
                        items_to_send = [dados]
                    else:
                        items_to_send = []
                    
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

        # Log interaction
        await asyncio.to_thread(
            db.registrar_interacao,
            balcao_id=balcao_id,
            transcricao=buffer_content or texto,
            recomendacao=recomendacao_log,
            resultado="processado",
            funcionario_id=funcionario_id,
            modelo_stt=modelo_usado,
            custo=custo_estimado,
            snr=snr_calculado,
            grok_raw=analise_json,
            ts_audio=ts_audio_received,
            ts_trans_sent=ts_transcription_sent,
            ts_trans_ready=ts_transcription_ready,
            ts_ai_req=ts_ai_request,
            ts_ai_res=ts_ai_response,
            ts_client=ts_client_sent,
            speaker_data=json.dumps(speaker_data_list) if speaker_data_list else None,
            audio_metrics=audio_metrics,
            # Enhanced Metrics
            config_snapshot=json.dumps(config_snapshot) if config_snapshot else None,
            mock_status=None, # Real processing
            cpu_usage=cpu_usage,
            ram_usage=ram_usage,
            audio_pitch_mean=audio_pitch_mean,
            audio_pitch_std=audio_pitch_std,
            spectral_centroid_mean=spectral_centroid_mean,
            interaction_type="valid"
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
    
    try:
        msg = await ws.receive_json(timeout=10.0)
        api_key = msg.get("api_key")
        
        # New: Parse VAD settings
        vad_settings = msg.get("vad_settings", {})
        vad_threshold_mult = vad_settings.get("threshold_multiplier") # e.g 1.5
        vad_min_energy = vad_settings.get("min_energy_threshold") # e.g 50.0

        balcao_id = db.validate_api_key(api_key)
        
        if not balcao_id:
            await ws.close(code=4001, message=b"API Key Invalida")
            return ws
            
        # Capacity Check
        is_available, reason = capacity_guard.CapacityGuard.check_availability()
        if not is_available:
            print(f"[REJECT] Connection Rejected ({balcao_id}): {reason}")
            await ws.close(code=4002, message=f"Server Overload: {reason}".encode('utf-8'))
            return ws

        print(f"Conectado: {balcao_id} (Settings: {vad_settings})")
        
        # Pass settings to VAD
        vad_session = vad.VAD(
            threshold_multiplier=vad_threshold_mult,
            min_energy_threshold=vad_min_energy
        )
        audio_cleaner = audio_processor.AudioCleaner()
        
        # Configure Snapshot for this connection
        current_config_snapshot = {
            "MOCK_MODE": config.MOCK_MODE,
            "MOCK_VOICE": config.MOCK_VOICE,
            "VAD_THRESHOLD": vad_threshold_mult,
            "VAD_MIN_ENERGY": vad_min_energy,
            "SMART_ROUTING": config.SMART_ROUTING_ENABLE
        }

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

                vad_out = vad_session.process(cleaned_pcm)
                if not vad_out:
                    continue

                speech, vad_meta = vad_out

                # Add cleaner gain to meta (if your AudioCleaner exposes it)
                cleaner_gain_db = getattr(audio_cleaner, "last_gain_db", None)
                if vad_meta is None:
                    vad_meta = {}
                vad_meta["audio_cleaner_gain_db"] = cleaner_gain_db

                pred_func_id, score, speaker_data_list = voice_tracker.add_segment(balcao_id, speech)

                pred_nome = None
                if speaker_data_list:
                    pred_nome = speaker_data_list[0].get("name")

                if pred_func_id is not None and funcionario_id_atual is None:
                    funcionario_id_atual = pred_func_id
                    nome_funcionario_atual = pred_nome or "Desconhecido"
                    print(f"[{balcao_id}] Voice-ID identificado: id={funcionario_id_atual} nome={nome_funcionario_atual} (score={score:.3f})")

                asyncio.create_task(
                    process_speech_pipeline(
                        ws, speech, balcao_id, transcript_buffer,
                        funcionario_id_atual, nome_funcionario_atual, speaker_data_list,
                        vad_meta=vad_meta,
                        config_snapshot=current_config_snapshot
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