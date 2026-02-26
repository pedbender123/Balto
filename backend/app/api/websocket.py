import asyncio
import json
import re
import unicodedata
import imageio_ffmpeg
import difflib

from datetime import datetime
from aiohttp import web, WSMsgType
from app import db, vad, transcription, speaker_id, audio_processor
from app.core import config, audio_utils, ai_client, buffer, audio_analysis, capacity_guard, audio_archiver
from app.core.cestas import resolve_basket_from_classification
from app.core.cestas_produtos_sintomas_doencas import parse_prompt1, lookup_cesta

try:
    import psutil
except ImportError:
    psutil = None
import random

def _norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    # remove acentos
    s = "".join(
        ch for ch in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(ch)
    )
    # normaliza espaços
    s = re.sub(r"\s+", " ", s)
    return s

def _is_excluded_suggestion(sugestao: str, anchors: list[str]) -> bool:
    """
    Remove a sugestão se ela "for" a âncora ou contiver a âncora (match bem tolerante).
    Ex: sugestao="Losartana 50mg" e anchors=["losartana"] -> True
    """
    sug_n = _norm_text(sugestao)
    if not sug_n:
        return True

    for a in anchors or []:
        a_n = _norm_text(a)
        if not a_n:
            continue
        # match por substring (simples e eficaz pro teu caso)
        if a_n in sug_n:
            return True
    return False

def build_recommendation_payload_from_classification(classification: dict, *, max_items: int = 3) -> dict | None:
    """
    classification: {"macros_top2":[...], "micro_categoria":..., "ancoras_para_excluir":[...]}
    Retorna payload no formato do renderer ou None se não houver itens válidos.
    """
    # resolve cesta (já vem com sugestao/explicacao/tag)
    items = resolve_basket_from_classification(classification, max_items=max_items)

    anchors = classification.get("ancoras_para_excluir") or []
    filtered = []
    for it in items:
        sugestao = (it.get("sugestao") or "").strip()
        if not sugestao:
            continue
        if _is_excluded_suggestion(sugestao, anchors):
            continue
        filtered.append({
            "sugestao": sugestao,
            "explicacao": (it.get("explicacao") or "").strip(),
            # opcional: manda tag também
            "tag": it.get("tag"),
        })

    if not filtered:
        return None

    return {
        "comando": "recomendar",
        "itens": filtered
    }

def build_recommendation_payload_from_lookup(items: list[dict], *, max_items: int = 3) -> dict | None:
    """
    items: [{"produto": "...", "explicacao": "..."}, ...]
    Converte pro payload padrão do frontend: {"comando":"recomendar","itens":[{"sugestao":...,"explicacao":...}]}
    """
    out = []
    for it in items[:max_items]:
        prod = (it.get("produto") or "").strip()
        exp  = (it.get("explicacao") or "").strip()
        if not prod:
            continue
        out.append({"sugestao": prod, "explicacao": exp})
    if not out:
        return None
    return {"comando": "recomendar", "itens": out}

def _tok(s: str) -> list[str]:
    s = _norm_text(s)
    # mantém só letras/números e espaço
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.split() if s else []

def dedupe_overlap_words(prev_text: str, cur_text: str,
                        max_window: int = 18,
                        min_overlap: int = 4,
                        min_ratio: float = 0.82) -> str:
    """
    Remove do começo do cur_text um overlap que parece repetição do final do prev_text,
    mesmo quando não é idêntico (ex.: token extra, pequenas variações).
    """
    if not prev_text or not cur_text:
        return cur_text

    prev_t = _tok(prev_text)
    cur_t  = _tok(cur_text)
    if not prev_t or not cur_t:
        return cur_text

    # só olha uma janela do final/início (pra não gastar muito e não apagar coisa demais)
    prev_tail = prev_t[-max_window:]
    cur_head  = cur_t[:max_window]

    best_k = 0

    # tenta do maior pro menor overlap
    for k in range(min(len(prev_tail), len(cur_head)), min_overlap - 1, -1):
        a = prev_tail[-k:]
        b = cur_head[:k]

        # comparação fuzzy: tokens -> string
        ra = " ".join(a)
        rb = " ".join(b)

        ratio = difflib.SequenceMatcher(a=ra, b=rb).ratio()

        # permite 1 token “extra” no começo do cur (“aqui”, “né”, etc.)
        if ratio < min_ratio and k >= (min_overlap + 1):
            b2 = cur_head[1:k+1]  # pula 1 token do começo
            rb2 = " ".join(b2)
            ratio2 = difflib.SequenceMatcher(a=ra, b=rb2).ratio()
            if ratio2 >= min_ratio:
                best_k = k  # mas vamos remover k+1 tokens do original (o extra + overlap)
                remove_tokens = k + 1
                break
        else:
            if ratio >= min_ratio:
                best_k = k
                remove_tokens = k
                break

    if best_k <= 0:
        return cur_text

    # Agora remove do cur_text ORIGINAL (não-normalizado) aproximadamente os primeiros N tokens
    # Estratégia: tokeniza “cur_text” bruto por espaços e remove N palavras iniciais.
    raw_tokens = cur_text.strip().split()
    if len(raw_tokens) <= remove_tokens:
        return ""  # virou só repetição
    return " ".join(raw_tokens[remove_tokens:]).lstrip()


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

    # --- SileroVAD (IA Filter) ---
    # Double check if this is really speech before expensive transcription
    svad = getattr(websocket, "_silero_vad", None)
    if svad:
        try:
            # SileroVAD.process_full_audio returns a list of timestamps
            timestamps = await asyncio.to_thread(svad.process_full_audio, speech_segment)
            if not timestamps:
                # Save interaction first to get ID
                interaction_id = await asyncio.to_thread(
                    db.registrar_interacao,
                    balcao_id=balcao_id,
                    transcricao="",
                    recomendacao="Recusado (IA Mask)",
                    resultado="discarded",
                    funcionario_id=funcionario_id,
                    modelo_stt="silero_filter",
                    custo=0.0,
                    snr=0.0,
                    ts_audio=ts_audio_received,
                    interaction_type="discarded_ia",
                    audio_file_path=None,
                    audio_classification=classification
                )
                
                # Save Audio with ID
                if interaction_id:
                    audio_path = await asyncio.to_thread(audio_archiver.archiver.save_interaction_audio, balcao_id, speech_segment, interaction_id)
                    await asyncio.to_thread(db.update_interaction_audio_path, interaction_id, audio_path)
                    
                return
        except Exception as e:
            print(f"[{balcao_id}] SileroVAD Error: {e}")
            # Keep going as fallback

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
    
    # Classify Audio Segment
    audio_classification = audio_analysis.classify_audio(features)
    
    # Save Raw WAV for this interaction is posponed for after DB register to get ID
    # audio_file_path = await asyncio.to_thread(audio_archiver.archiver.save_interaction_audio, balcao_id, speech_segment)

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
        interaction_id = await asyncio.to_thread(
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
            interaction_type="mock_voice",
            audio_file_path=None,
            audio_classification=audio_classification
        )
        
        # Save Audio with ID
        if interaction_id:
            audio_file_path = await asyncio.to_thread(audio_archiver.archiver.save_interaction_audio, balcao_id, speech_segment, interaction_id)
            await asyncio.to_thread(db.update_interaction_audio_path, interaction_id, audio_file_path)

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
        normalizacao_out = None
        classificacao_out = None
        analise_json = None
        ts_ai_request = None
        ts_ai_response = None
        ts_client_sent = None
        recomendacao_log = None
        envelope = None
        cesta_key = None
        cesta_origem = None
        cesta_itens_raw = None
        cesta_itens_pos = None
        used_lookup = False
        classif_obj = None


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
            
            interaction_id = await asyncio.to_thread(
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
                interaction_type=interaction_type,
                audio_file_path=None,
                audio_classification=audio_classification
            )
            
            # Save Audio with ID
            if interaction_id:
                audio_file_path = await asyncio.to_thread(audio_archiver.archiver.save_interaction_audio, balcao_id, speech_segment, interaction_id)
                await asyncio.to_thread(db.update_interaction_audio_path, interaction_id, audio_file_path)

            return


        ts_transcription_end = datetime.now()
        processing_time_so_far = (ts_transcription_end - ts_transcription_sent).total_seconds()
        capacity_guard.CapacityGuard.report_processing_metrics(segment_duration_ms / 1000.0, processing_time_so_far)

        print(f"[{balcao_id}] Transcrição ({modelo_usado}): {texto}")
        

        # --- DEDUPE por overlap (fuzzy) ---
        prev_last = getattr(transcript_buffer, "_last_text", "")
        texto = dedupe_overlap_words(prev_last, texto)
        setattr(transcript_buffer, "_last_text", texto)
        # ----------------------------------

        # Add to buffer
        transcript_buffer.add_text(texto)

        # Check if we should process via AI
        if transcript_buffer.should_process():

            # Se estiver suprimindo recomendações (modo de teste), não chama LLM
            if config.MOCK_RECOMMENDATION:
                print(f"[{balcao_id}] Normalização bloqueada (MOCK_RECOMMENDATION=True).")
                recomendacao_log = "🚫 NORMALIZE: bloqueado (MOCK_RECOMMENDATION=True)"
                
                buffer_content = transcript_buffer.get_context_and_clear()
                
                normalizacao_out = None
                classificacao_out = None
                
                ts_ai_request = None
                ts_ai_response = None

            else:
                # 1) pega o buffer consolidado UMA VEZ
                buffer_content = transcript_buffer.get_context_and_clear()

                if not buffer_content or not buffer_content.strip():
                    recomendacao_log = "NORM: vazio"
                    normalizacao_out = "NADA_RELEVANTE | OUTRO"
                    classificacao_out = None
                    ts_ai_request = None
                    ts_ai_response = None

                else:
                    print(f"[{balcao_id}] Enviando para NORMALIZE: {buffer_content[-200:]}...")

                    # -------------------------
                    # LLM #1: NORMALIZAR
                    # -------------------------
                    ts_ai_request = datetime.now()
                    norm_out = await asyncio.to_thread(
                        ai_client.ai_client.normalizar_texto,
                        buffer_content
                    )

                    normalizacao_out = (norm_out or "").strip()
                    if not normalizacao_out:
                        normalizacao_out = "NADA_RELEVANTE | OUTRO"

                    # =========================
                    # [NEW] Lookup (produto+sintoma+doenca) após Prompt 1
                    # =========================
                    med, sint, doenca = parse_prompt1(normalizacao_out)
                    lookup_items = lookup_cesta(med, sint, doenca)

                    if lookup_items:
                        used_lookup = True

                        # monta payload e envia (3 primeiros)
                        payload_out = build_recommendation_payload_from_lookup(lookup_items, max_items=3)

                        if payload_out and (not websocket.closed):
                            try:
                                ts_client_sent = datetime.now()
                                await websocket.send_json(payload_out)
                            except Exception as e:
                                print(f"[{balcao_id}] ❌ Falha ao enviar recomendação (lookup): {e}")
                                ts_client_sent = None

                        # log/telemetria
                        cesta_key = f"LOOKUP::{med}_{sint or 'default'}_{doenca or 'default'}"
                        recomendacao_log = cesta_key

                        # opcional: salvar no campo classificacao um json indicando origem
                        try:
                            classif_obj = {"source": "lookup", "med": med, "sint": sint or None, "doenca": doenca or None}
                            classificacao_out = json.dumps(classif_obj, ensure_ascii=False)
                        except Exception:
                            pass

                    # =========================
                    # Se NÃO achou no lookup, segue o fluxo atual (Prompt 2 -> cestas.json)
                    # =========================
                    if not used_lookup:
                        # -------------------------
                        # LLM #2: CLASSIFICAR
                        # -------------------------
                        classif = await asyncio.to_thread(
                            ai_client.ai_client.classificar_cesta,
                            normalizacao_out
                        )
                        ts_ai_response = datetime.now()

                        if isinstance(classif, dict):
                            classif_obj = classif
                        else:
                            try:
                                classif_obj = json.loads(classif)
                            except Exception:
                                classif_obj = {"_raw": str(classif), "_parse_error": True}

                        try:
                            classificacao_out = json.dumps(classif_obj, ensure_ascii=False)
                        except Exception:
                            classificacao_out = None

                        macro = None
                        micro = None
                        if isinstance(classif_obj, dict):
                            macros_top2 = classif_obj.get("macros_top2") or []
                            macro = macros_top2[0] if len(macros_top2) > 0 else None
                            micro = classif_obj.get("micro_categoria")

                        if macro and micro:
                            cesta_key = f"{macro}::{micro}"
                            cesta_origem = "macro_micro"
                        elif macro:
                            cesta_key = f"{macro}::fallback"
                            cesta_origem = "fallback_macro_default"
                        else:
                            cesta_key = "OUTRO::fallback"
                            cesta_origem = "fallback_macro_default"

                        envelope = {
                            "buffer_content": buffer_content,
                            "normalizacao_out": normalizacao_out,
                            "classificacao_out": classif_obj,
                            "cesta_key": cesta_key,
                            "cesta_origem": cesta_origem,
                            "meta": {
                                "balcao_id": balcao_id,
                                "funcionario_id": funcionario_id,
                                "nome_funcionario": nome_funcionario,
                            },
                            "timestamps": {
                                "ts_audio_received": ts_audio_received.isoformat(),
                                "ts_trans_sent": ts_transcription_sent.isoformat() if ts_transcription_sent else None,
                                "ts_trans_ready": ts_transcription_ready.isoformat() if ts_transcription_ready else None,
                                "ts_ai_req": ts_ai_request.isoformat() if ts_ai_request else None,
                                "ts_ai_res": ts_ai_response.isoformat() if ts_ai_response else None,
                            }
                        }

                        recomendacao_log = cesta_key

        # ================================
        # [ADD] Envio para o frontend ANTES de gravar no BD
        # ================================
        payload_out = None

        # Só tenta montar/enviar payload se houver classificação válida (dict)
        if (not used_lookup) and isinstance(classif_obj, dict) and classif_obj:
            payload_out = build_recommendation_payload_from_classification(classif_obj, max_items=3)

            if payload_out and (not websocket.closed):
                try:
                    ts_client_sent = datetime.now()
                    await websocket.send_json(payload_out)
                except Exception as e:
                    print(f"[{balcao_id}] ❌ Falha ao enviar recomendação: {e}")
                    ts_client_sent = None


        if recomendacao_log is None:
            recomendacao_log = ""

        interaction_id = await asyncio.to_thread(
            db.registrar_interacao,
            balcao_id=balcao_id,
            transcricao=buffer_content or texto,
            transcricao_normalizada=normalizacao_out,
            transcricao_classificacao=classificacao_out,
            recomendacao=cesta_key or recomendacao_log,
            resultado="processado",
            funcionario_id=funcionario_id,
            modelo_stt=modelo_usado,
            custo=custo_estimado,
            snr=snr_calculado,
            grok_raw=(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) if envelope else None),
            ts_audio=ts_audio_received,
            ts_trans_sent=ts_transcription_sent,
            ts_trans_ready=ts_transcription_ready,
            ts_ai_req=ts_ai_request,
            ts_ai_res=ts_ai_response,
            ts_client=ts_client_sent,
            speaker_data=json.dumps(speaker_data_list) if speaker_data_list else None,
            audio_metrics=audio_metrics,
            config_snapshot=json.dumps(config_snapshot) if config_snapshot else None,
            mock_status=None,
            cpu_usage=cpu_usage,
            ram_usage=ram_usage,
            audio_pitch_mean=audio_pitch_mean,
            audio_pitch_std=audio_pitch_std,
            spectral_centroid_mean=spectral_centroid_mean,
            interaction_type="valid",
            audio_file_path=None,
            audio_classification=audio_classification
        )
        
        # Save Audio with ID
        if interaction_id:
            audio_file_path = await asyncio.to_thread(audio_archiver.archiver.save_interaction_audio, balcao_id, speech_segment, interaction_id)
            await asyncio.to_thread(db.update_interaction_audio_path, interaction_id, audio_file_path)


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

        # 1. Load VAD Config from DB (Per-Counter Presets)
        db_vad_cfg = db.get_balcao_vad_config(balcao_id)
        
        # 2. Merge with Frontend (Frontend overrides DB? Or DB overrides Frontend? 
        # Requirement: "Preset aplicado automaticamente por balcão sem o frontend enviar nada"
        # Implies DB is source of truth. If frontend sends something, maybe ignore or merge.
        # Let's say DB overrides defaults, and Frontend is ignored (as requested).
        
        # But if msg has "vad_settings", user might want to debug from frontend?
        # Requirement: "Preenche com os valores no .env ... mas vai ter agora uma copia no banco"
        # Using DB config primarily.
        
        print(f"Conectado: {balcao_id} (DB VAD Preset: {db_vad_cfg})")
        
        # Instantiate VAD with merged config
        # Default < Env < DB
        
        vad_session = vad.VAD(
            threshold_multiplier=db_vad_cfg.get("threshold_multiplier"),
            min_energy_threshold=db_vad_cfg.get("min_energy_threshold")
        )
        
        # Apply extra params not in __init__ signatures sometimes or requiring custom logic
        if "alpha" in db_vad_cfg:
            vad_session.alpha = float(db_vad_cfg["alpha"])
            
        if "silence_frames_needed" in db_vad_cfg:
            vad_session.silence_frames_needed = int(db_vad_cfg["silence_frames_needed"])
            
        if "segment_limit_frames" in db_vad_cfg:
            vad_session.segment_limit_frames = int(db_vad_cfg["segment_limit_frames"])
            
        if "overlap_frames" in db_vad_cfg:
            from collections import deque
            new_overlap = int(db_vad_cfg["overlap_frames"])
            vad_session.overlap_frames = new_overlap
            vad_session.overlap_buffer = deque(maxlen=new_overlap)
        
        # [REMOVED] AudioCleaner — noise reduction was too aggressive, cutting speech
        
        # Configure Snapshot for this connection
        current_config_snapshot = {
            "MOCK_MODE": config.MOCK_MODE,
            "MOCK_VOICE": config.MOCK_VOICE,
            "SMART_ROUTING": config.SMART_ROUTING_ENABLE,
            "VAD_SOURCE": "DB_PRESET" if db_vad_cfg else "ENV_DEFAULT",
            "VAD_CONFIG": {
                "threshold_multiplier": vad_session.threshold_multiplier,
                "min_energy_threshold": vad_session.min_energy_threshold,
                "alpha": vad_session.alpha,
                "silence_frames_needed": vad_session.silence_frames_needed,
                "segment_limit_frames": vad_session.segment_limit_frames,
                "overlap_frames": vad_session.overlap_frames
            }
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

                # Archive RAW chunk (no noise reduction — raw goes straight to VAD)
                audio_archiver.archiver.archive_chunk(balcao_id, new_pcm, is_processed=False)

                vad_out = vad_session.process(new_pcm)
                if not vad_out:
                    continue

                speech, vad_meta = vad_out

                if vad_meta is None:
                    vad_meta = {}

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