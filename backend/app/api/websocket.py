
import asyncio
import json
from aiohttp import web, WSMsgType
from app import db, vad, transcription, speaker_id, audio_processor
from app.core import config, audio_utils, ai_client, buffer

async def process_speech_pipeline(websocket, speech_segment: bytes, balcao_id: str, transcript_buffer: buffer.TranscriptionBuffer):
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
        transcricao_resultado = await asyncio.to_thread(
            transcription.transcrever_inteligente, speech_segment
        )
        
        texto = transcricao_resultado["texto"]
        modelo_usado = transcricao_resultado["modelo"]
        custo_estimado = transcricao_resultado["custo"]
        snr_calculado = transcricao_resultado.get("snr", 0.0)
        
        if not texto:
            return

        print(f"[{balcao_id}] Transcrição ({modelo_usado}): {texto}")
        
        # Add to buffer
        transcript_buffer.add_text(texto)

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
            full_context = transcript_buffer.get_context_and_clear()
            print(f"[{balcao_id}] Enviando Contexto para AI: {full_context}")

            analise_json = await asyncio.to_thread(
                ai_client.ai_client.analisar_texto, full_context
            )

            sugestao = None
            explicacao = None
            
            if analise_json:
                try:
                    dados = json.loads(analise_json)
                    # Handle new schema structure which has "itens" array
                    if "itens" in dados:
                        # For simplicity, take the first valid suggestion
                        for item in dados["itens"]:
                             if item.get("sugestao"):
                                 sugestao = item.get("sugestao")
                                 explicacao = item.get("explicacao")
                                 break
                    else:
                         sugestao = dados.get("sugestao")
                         explicacao = dados.get("explicacao")
                    
                    if sugestao:
                        payload = {
                            "comando": "recomendar",
                            "produto": sugestao,
                            "explicacao": explicacao,
                            "transcricao_base": full_context,
                            "atendente": nome_funcionario
                        }
                        await websocket.send_json(payload)
                except Exception as e:
                    print(f"[{balcao_id}] Erro Parse JSON AI: {e}")

            # Log interaction
            await asyncio.to_thread(
                db.registrar_interacao,
                balcao_id=balcao_id,
                transcricao=full_context,
                recomendacao=f"{sugestao} ({explicacao})" if sugestao else "Nenhuma",
                resultado="processado",
                funcionario_id=funcionario_id,
                modelo_stt=modelo_usado,
                custo=custo_estimado,
                snr=snr_calculado,
                grok_raw=analise_json
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
                            process_speech_pipeline(ws, speech, balcao_id, transcript_buffer)
                        )
            elif msg.type == WSMsgType.ERROR:
                print(f"WS Error: {ws.exception()}")
    except Exception as e:
        if "Cannot write to closing transport" not in str(e):
            print(f"WS Loop Error: {e}")

    print(f"Desconectado: {balcao_id}")
    return ws
