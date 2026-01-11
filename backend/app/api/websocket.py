import asyncio
import json
from datetime import datetime
from aiohttp import web, WSMsgType
from app import db, vad, transcription, speaker_id, audio_processor
from app.core import config, audio_utils, ai_client, buffer


async def process_speech_pipeline(websocket, speech_segment: bytes, balcao_id: str, transcript_buffer: buffer.TranscriptionBuffer, conversation_history: list):
    ts_audio_received = datetime.now()
    print(f"[{balcao_id}] Processando segmento de fala ({len(speech_segment)} bytes)...")

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

        # Speaker ID (Optional)
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
            ts_ai_response = datetime.now()

            sugestoes_enviadas = []
            
            if analise_json:
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
                        
                        # Small delay not needed for batch, but keep minimal yield if needed
                        # await asyncio.sleep(0.1) 
                    
                except Exception as e:
                    print(f"[{balcao_id}] Erro Parse JSON AI: {e}")
                    recomendacao_log = "Erro Parse"

            # Prepare log string (Fallback if not set above)
            if 'recomendacao_log' not in locals():
                recomendacao_log = "Nenhuma"

            # Log interaction
            await asyncio.to_thread(
                db.registrar_interacao,
                balcao_id=balcao_id,
                transcricao=full_context_str, # Salva o contexto todo usado
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
                ts_client=ts_client_sent if 'ts_client_sent' in locals() else None
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
    
    webm_buffer = bytearray()
    pcm_offset = 0

    try:
        msg = await ws.receive_json(timeout=10.0)
        api_key = msg.get("api_key")
        balcao_id = db.validate_api_key(api_key)
        
        if not balcao_id:
            await ws.close(code=4001, message=b"API Key Invalida")
            return ws
            
        print(f"Conectado: {balcao_id}")
        vad_session = vad.VAD()
        audio_cleaner = audio_processor.AudioCleaner()
        
    except Exception as e:
        print(f"Erro Auth WS: {e}")
        await ws.close()
        return ws

    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                webm_buffer.extend(msg.data)
                pcm_full = audio_utils.decode_webm_to_pcm16le(bytes(webm_buffer))
                
                if not pcm_full: continue
                
                if len(pcm_full) > pcm_offset:
                    new_pcm = pcm_full[pcm_offset:]
                    pcm_offset = len(pcm_full)
                    
                    cleaned_pcm = audio_cleaner.process(new_pcm)
                    speech = vad_session.process(cleaned_pcm)
                    
                    if speech:
                        asyncio.create_task(
                            process_speech_pipeline(ws, speech, balcao_id, transcript_buffer, conversation_history)
                        )
            elif msg.type == WSMsgType.ERROR:
                print(f"WS Error: {ws.exception()}")
    except Exception as e:
        if "Cannot write to closing transport" not in str(e):
            print(f"WS Loop Error: {e}")

    print(f"Desconectado: {balcao_id}")
    return ws
