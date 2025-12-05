import asyncio
import json
import os
import uuid
from dotenv import load_dotenv
from aiohttp import web, WSMsgType

# Ajuste de imports para a nova estrutura de pasta app/
from app import db, vad, transcription, analysis

load_dotenv()

async def process_speech_pipeline(websocket, speech_segment: bytes, balcao_id: str):
    print(f"[{balcao_id}] Processando áudio...")
    try:
        # 1. Transcrição (ElevenLabs)
        texto = await asyncio.to_thread(transcription.transcrever, speech_segment)
        print(f"[{balcao_id}] Transcrição: {texto}")

        if not texto or texto.startswith("[Erro"):
            return

        # 2. Análise (Grok) - Agora retorna um JSON string
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
                    
                    # Opcional: Salvar no banco apenas que houve uma sugestão (sem feedback)
                    # await asyncio.to_thread(db.registrar_interacao_simples, ...)
            except json.JSONDecodeError:
                print(f"Erro ao decodificar JSON do Grok: {json_analise}")

    except Exception as e:
        print(f"[{balcao_id}] Erro pipeline: {e}")

# ... (Mantenha as rotas HTTP de cadastro iguais) ...

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    # ... (Autenticação mantida igual) ...
    
    # Loop Principal simplificado (SEM FEEDBACK)
    async for msg in ws:
        if msg.type == WSMsgType.BINARY:
            speech_segment = client_vad.process(msg.data)
            if speech_segment:
                asyncio.create_task(process_speech_pipeline(ws, speech_segment, balcao_id))
        
        elif msg.type == WSMsgType.TEXT:
            # Ignoramos mensagens de texto pois não há mais feedback vindo do front
            pass
            
    return ws

# ... (Main mantido igual) ...